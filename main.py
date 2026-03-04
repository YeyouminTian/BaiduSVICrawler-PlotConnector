"""
主程序：百度街景爬取与地块关联分析
整合所有模块化的工具函数
"""
import os
import pandas as pd
import geopandas as gpd
import cv2
import numpy as np
from tqdm import tqdm
from shapely.geometry import Point

# 导入各模块
from geometry_utils import project_gdf
from landuse_utils import read_landuse_gdb
from streetview_utils import (
    read_streetview_points,
    wgs84_to_bd09mc,
    get_streetview_metadata,
    download_panorama_image
)
from image_utils import equirectangular_to_perspective
from spatial_analysis import determine_side_strict
from topology_utils import (
    read_road_gdb,
    build_landuse_topology,
    generate_final_config,
    execute_rename
)

# 屏蔽Pandas的SettingWithCopyWarning警告
pd.options.mode.chained_assignment = None


def main(
    # 数据路径
    landuse_gdb_path,
    landuse_layer,
    landuse_id_col,
    road_layer,
    road_id_col,
    streetview_csv_path,
    baidu_ak,

    # 输出配置
    output_dir='output',
    zoom=3,
    save_every=50,

    # 功能开关
    build_topology=True,
    traversal_direction='clockwise',

    # 空间匹配参数
    test_limit=None,
    distance_threshold=100,
    search_buffer=500,

    # 算法选择
    use_local_tangent=True,
    verbose_matching=False
):
    """
    主函数：执行街景爬取与地块关联分析

    Args:
        landuse_gdb_path: 地块GDB文件路径
        landuse_layer: 地块图层名
        landuse_id_col: 地块ID字段名
        road_layer: 道路图层名
        road_id_col: 道路ID字段名
        streetview_csv_path: 街景点CSV文件路径
        baidu_ak: 百度地图API密钥
        output_dir: 输出目录
        zoom: 街景缩放级别（1-4）
        save_every: 保存间隔
        build_topology: 是否构建拓扑关系
        traversal_direction: 遍历方向 ('clockwise' 或 'counterclockwise')
        test_limit: 测试模式限制（处理前N个点）
        distance_threshold: 距离阈值（米）
        search_buffer: 搜索缓冲区（米）
        use_local_tangent: 使用局部切线法
        verbose_matching: 详细匹配日志
    """
    # 1. 初始化
    os.makedirs(output_dir, exist_ok=True)
    img_dir = os.path.join(output_dir, 'images')
    os.makedirs(img_dir, exist_ok=True)

    print("=" * 60)
    print("读取数据中...")
    print("=" * 60)

    # 读取地块数据
    landuse_gdf = read_landuse_gdb(landuse_gdb_path, landuse_layer, landuse_id_col)
    print(f"读取地块 {len(landuse_gdf)} 个")

    # 读取道路数据
    road_gdf = read_road_gdb(landuse_gdb_path, road_layer, road_id_col)
    print(f"读取道路 {len(road_gdf)} 条")

    # 读取街景点
    sv_points = read_streetview_points(streetview_csv_path)
    print(f"读取街景点 {len(sv_points)} 个")

    # 断点续传
    processed_ids = set()
    mapping_csv_path = os.path.join(output_dir, 'streetview_landuse_mapping.csv')
    current_mapping = []
    if os.path.exists(mapping_csv_path):
        try:
            df_exist = pd.read_csv(mapping_csv_path)
            processed_ids = set(df_exist['id'].astype(str).unique())
            current_mapping = df_exist.to_dict('records')
            print(f"发现已有记录 {len(processed_ids)} 个街景点，将跳过。")
        except Exception as e:
            print(f"读取已有mapping失败: {e}")

    # 过滤待处理点
    points_to_process = []
    for p in sv_points:
        if len(p) >= 3:
            pid = str(p[0])
        else:
            pid = f"{p[-2]}_{p[-1]}"
        if pid not in processed_ids:
            points_to_process.append(p)

    if test_limit:
        points_to_process = points_to_process[:test_limit]
        print(f"测试模式: 仅处理 {len(points_to_process)} 个点")
    else:
        print(f"待处理: {len(points_to_process)} 个点")

    # 2. 准备空间分析环境
    print("=" * 60)
    print("构建空间索引与投影...")
    print("=" * 60)

    landuse_gdf_proj, utm_crs = project_gdf(landuse_gdf)
    landuse_sindex = landuse_gdf_proj.sindex

    road_gdf_proj = road_gdf.to_crs(utm_crs)
    road_sindex = road_gdf_proj.sindex

    print(f"使用{'局部切线法' if use_local_tangent else '纯Heading法'}进行左右判断")

    # 建立街景点-道路映射
    print("建立街景点-道路关联...")
    sv_road_map = []

    all_sv_points_normalized = []
    for pt in sv_points:
        if len(pt) >= 3:
            id_val, x, y = pt[0], pt[1], pt[2]
        else:
            x, y = pt[0], pt[1]
            id_val = f"{x}_{y}"
        all_sv_points_normalized.append({'original_id': id_val, 'x': x, 'y': y})

    # 为所有点分配最近道路
    road_search_buffer = 200
    no_road_count = 0

    for pt in tqdm(all_sv_points_normalized, desc="道路匹配"):
        p_geom_wgs = Point(pt['x'], pt['y'])
        p_geom_proj = gpd.GeoSeries([p_geom_wgs], crs="EPSG:4326").to_crs(utm_crs)[0]

        from spatial_analysis import find_nearest_road
        nearest_road, min_d, nearest_idx = find_nearest_road(
            p_geom_proj, road_gdf_proj, road_sindex, road_search_buffer
        )

        nearest_rid = None
        if nearest_idx is not None:
            nearest_rid = road_gdf_proj.iloc[nearest_idx][road_id_col]

        if nearest_rid is None:
            no_road_count += 1

        sv_road_map.append({
            **pt,
            'road_id': nearest_rid,
            'road_distance': min_d if min_d != float('inf') else None
        })

    if no_road_count > 0:
        print(f"警告: {no_road_count} 个点未找到匹配道路")

    # 3. 爬取与匹配主循环
    print("=" * 60)
    print("开始爬取街景...")
    print("=" * 60)

    new_records = []
    no_landuse_count = 0

    for i, pt_data in enumerate(tqdm(points_to_process, desc="爬取进度")):
        if len(pt_data) >= 3:
            id_val, x, y = pt_data[0], pt_data[1], pt_data[2]
        else:
            x, y = pt_data[0], pt_data[1]
            id_val = f"{x}_{y}"

        # A. 坐标转换与元数据
        x_bd, y_bd = wgs84_to_bd09mc(x, y, baidu_ak)
        if not x_bd:
            continue

        sid, meta = get_streetview_metadata(x_bd, y_bd)
        if not sid:
            continue

        heading = float(meta.get('Heading', 0))
        capture_time = meta.get('Time', '')

        # B. 下载与处理图像
        pano = download_panorama_image(sid, zoom)
        if not pano:
            print(f"下载失败: {sid}")
            continue

        pano_np = cv2.cvtColor(np.array(pano), cv2.COLOR_RGB2BGR)
        out_size = (1024, 683)

        # 左右视图
        left_view = equirectangular_to_perspective(pano_np, 120, 90, 0, 0, out_size)
        right_view = equirectangular_to_perspective(pano_np, 120, 90, 180, 0, out_size)

        # 临时保存
        fname_L = f"{id_val}_L.jpg"
        fname_R = f"{id_val}_R.jpg"
        cv2.imwrite(os.path.join(img_dir, fname_L), left_view)
        cv2.imwrite(os.path.join(img_dir, fname_R), right_view)

        # C. 空间匹配
        pt_wgs = Point(x, y)
        pt_proj = gpd.GeoSeries([pt_wgs], crs="EPSG:4326").to_crs(utm_crs)[0]

        buffer_bounds = pt_proj.buffer(search_buffer).bounds
        possible_idxs = list(landuse_sindex.intersection(buffer_bounds))

        matched_left = False
        matched_right = False

        if possible_idxs:
            candidates = landuse_gdf_proj.iloc[possible_idxs].copy()

            # 排除非实体地块
            if 'GH_LAYOUT' in candidates.columns:
                candidates = candidates[candidates['GH_LAYOUT'] != 'S1']

            if len(candidates) > 0:
                cand_geoms = candidates.geometry.tolist()
                cand_ids = candidates[landuse_id_col].tolist()

                # 使用局部切线法或纯Heading法
                l_id, l_dist, r_id, r_dist = determine_side_strict(
                    pt_proj, heading, cand_geoms, cand_ids,
                    road_gdf_proj=road_gdf_proj if use_local_tangent else None,
                    road_sindex=road_sindex if use_local_tangent else None,
                    landuse_id_col=landuse_id_col,
                    use_local_tangent=use_local_tangent
                )

                if verbose_matching:
                    print(f"\n点 {id_val}: heading={heading:.1f}°")
                    print(f"  左侧: {l_id} (距离: {l_dist:.1f}m)")
                    print(f"  右侧: {r_id} (距离: {r_dist:.1f}m)")

                if l_id is not None and l_dist < distance_threshold:
                    new_records.append({
                        'id': id_val,
                        'streetview_id': sid,
                        'filename': fname_L,
                        'landuse_id': l_id,
                        'side': 'L',
                        'x': x,
                        'y': y,
                        'heading': heading,
                        'capture_time': capture_time,
                        'distance': l_dist
                    })
                    matched_left = True

                if r_id is not None and r_dist < distance_threshold:
                    new_records.append({
                        'id': id_val,
                        'streetview_id': sid,
                        'filename': fname_R,
                        'landuse_id': r_id,
                        'side': 'R',
                        'x': x,
                        'y': y,
                        'heading': heading,
                        'capture_time': capture_time,
                        'distance': r_dist
                    })
                    matched_right = True

        if not matched_left and not matched_right:
            no_landuse_count += 1

        # 定期保存
        if (i + 1) % save_every == 0:
            temp_df = pd.DataFrame(current_mapping + new_records)
            temp_df.to_csv(mapping_csv_path, index=False, encoding='utf-8')
            print(f"[进度保存] 已保存 {len(current_mapping) + len(new_records)} 条记录")

    if no_landuse_count > 0:
        print(f"警告: {no_landuse_count} 个点未匹配到地块 (可能距离超过 {distance_threshold}m)")

    # 保存
    final_mapping = current_mapping + new_records
    mapping_df = pd.DataFrame(final_mapping)
    mapping_df.to_csv(mapping_csv_path, index=False, encoding='utf-8')
    mapping_df.to_json(os.path.join(output_dir, 'streetview_landuse_mapping.json'),
                       orient='records', force_ascii=False)
    print(f"保存映射表: {len(mapping_df)} 条记录")

    # 4. 构建拓扑与重命名
    if build_topology and not mapping_df.empty:
        print("=" * 60)
        print("构建拓扑结构...")
        print("=" * 60)

        topology_results = []
        all_lids = mapping_df['landuse_id'].unique()

        for lid in tqdm(all_lids, desc="拓扑构建"):
            topo = build_landuse_topology(lid, sv_road_map, landuse_gdf, landuse_id_col,
                                          mapping_df, traversal_direction)
            if topo:
                topology_results.append(topo)

        print(f"构建拓扑: {len(topology_results)} 个地块")

        config_df = generate_final_config(topology_results, mapping_df, output_dir)
        print(f"生成配置表: {len(config_df)} 条记录")

        execute_rename(config_df, img_dir)

        # 更新filename
        print("更新映射表文件名...")
        fname_map = {}
        for _, row in config_df.iterrows():
            key = (str(row['streetview_id']), row['side'])
            fname_map[key] = row['filename']

        def update_fname(row):
            key = (str(row['id']), row['side'])
            return fname_map.get(key, row['filename'])

        mapping_df['filename'] = mapping_df.apply(update_fname, axis=1)
        mapping_df.to_csv(mapping_csv_path, index=False, encoding='utf-8')
        mapping_df.to_json(os.path.join(output_dir, 'streetview_landuse_mapping.json'),
                           orient='records', force_ascii=False)

    print("=" * 60)
    print("处理完成！")
    print(f"输出目录: {output_dir}")
    print("=" * 60)


if __name__ == '__main__':
    main(
        landuse_gdb_path=r'D:\LifeOS\01Projects\GraduateThesis\251118街景+虹口测试\hongkou_test\hongkou_test.gdb',
        landuse_layer='blocks251206',
        landuse_id_col='Block_ID',
        road_layer='road_hongkou_251206',
        road_id_col='ID',
        streetview_csv_path=r'D:\LifeOS\01Projects\GraduateThesis\251118街景+虹口测试\251216 测试\251206svi.csv',
        baidu_ak='YOUR_API_KEY_HERE',
        output_dir='svi_251206',
        zoom=3,
        save_every=50,
        build_topology=True,
        traversal_direction='clockwise',
        test_limit=None,
        distance_threshold=100,
        search_buffer=500,
        use_local_tangent=True,
        verbose_matching=True
    )
