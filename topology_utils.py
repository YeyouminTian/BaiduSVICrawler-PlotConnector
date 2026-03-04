"""
拓扑关系处理模块
"""
import os
import math
import pandas as pd
import geopandas as gpd
import numpy as np
from collections import defaultdict
from shapely.geometry import Point


def read_road_gdb(gdb_path, road_layer='road', road_id_col='OBJECTID'):
    """
    读取道路数据

    Args:
        gdb_path: GDB文件路径
        road_layer: 道路图层名
        road_id_col: 道路ID字段名

    Returns:
        GeoDataFrame
    """
    print(f"正在读取道路图层: {road_layer} ...")
    gdf = gpd.read_file(gdb_path, layer=road_layer)
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    elif gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    return gdf


def calculate_angle(origin, point):
    """
    计算点相对于原点的角度

    Args:
        origin: 原点坐标 (x, y)
        point: 目标点坐标 (x, y)

    Returns:
        角度（0-2π，正北为0，顺时针）
    """
    dx = point[0] - origin[0]
    dy = point[1] - origin[1]
    angle = math.atan2(dx, dy)
    if angle < 0:
        angle += 2 * math.pi
    return angle


def build_landuse_topology(landuse_id, streetview_road_mapping, landuse_gdf, landuse_id_col,
                           streetview_landuse_mapping, traversal_direction='clockwise'):
    """
    为单个地块建立道路和街景点的拓扑顺序

    Args:
        landuse_id: 地块ID
        streetview_road_mapping: 街景点-道路映射列表
        landuse_gdf: 地块GeoDataFrame
        landuse_id_col: 地块ID列名
        streetview_landuse_mapping: 街景点-地块映射DataFrame
        traversal_direction: 遍历方向 ('clockwise' 或 'counterclockwise')

    Returns:
        拓扑字典或None
    """
    try:
        landuse_row = landuse_gdf[landuse_gdf[landuse_id_col] == landuse_id].iloc[0]
    except IndexError:
        return None

    landuse_centroid = (landuse_row['centroid_x'], landuse_row['centroid_y'])

    # 筛选关联的街景点
    related_records = streetview_landuse_mapping[streetview_landuse_mapping['landuse_id'] == landuse_id]
    related_sv_ids = related_records['id'].unique()

    # 将街景点按道路归类
    road_groups = defaultdict(list)
    sv_lookup = {item['original_id']: item for item in streetview_road_mapping}

    # 同时尝试字符串和数字类型的匹配
    sv_lookup_str = {str(k): v for k, v in sv_lookup.items()}

    for sv_id in related_sv_ids:
        sv_info = None
        # 尝试原始类型匹配
        if sv_id in sv_lookup:
            sv_info = sv_lookup[sv_id]
        # 尝试字符串匹配
        elif str(sv_id) in sv_lookup_str:
            sv_info = sv_lookup_str[str(sv_id)]
        # 尝试数字匹配
        elif isinstance(sv_id, str) and sv_id.isdigit():
            if int(sv_id) in sv_lookup:
                sv_info = sv_lookup[int(sv_id)]

        if sv_info and sv_info['road_id'] is not None:
            road_groups[sv_info['road_id']].append(sv_info)

    if not road_groups:
        return None

    # 道路排序：计算每条道路的质心，然后按角度排序
    road_centroids = {}
    for rid, points in road_groups.items():
        cx = np.mean([p['x'] for p in points])
        cy = np.mean([p['y'] for p in points])
        road_centroids[rid] = (cx, cy)

    road_angles = []
    for rid, rc in road_centroids.items():
        ang = calculate_angle(landuse_centroid, rc)
        road_angles.append((rid, ang))

    is_clockwise = (traversal_direction == 'clockwise')
    road_angles.sort(key=lambda x: x[1], reverse=not is_clockwise)

    topology = {
        'landuse_id': landuse_id,
        'road_sequence': []
    }

    # 对每条道路内的街景点排序
    for seq_idx, (road_id, _) in enumerate(road_angles, 1):
        points = road_groups[road_id]
        points_with_angle = []
        for p in points:
            ang = calculate_angle(landuse_centroid, (p['x'], p['y']))
            points_with_angle.append((p, ang))

        points_with_angle.sort(key=lambda x: x[1], reverse=not is_clockwise)
        sorted_points = [p[0] for p in points_with_angle]

        road_topo = {
            'road_id': road_id,
            'sequence': seq_idx,
            'streetview_points': []
        }

        for pt_seq, sv in enumerate(sorted_points, 1):
            road_topo['streetview_points'].append({
                'streetview_id': sv['original_id'],
                'sequence': pt_seq,
                'x': sv['x'],
                'y': sv['y']
            })

        topology['road_sequence'].append(road_topo)

    return topology


def generate_final_config(topology_list, mapping_df, output_dir):
    """
    生成最终的遍历配置表

    Args:
        topology_list: 拓扑结构列表
        mapping_df: 街景点-地块映射DataFrame
        output_dir: 输出目录

    Returns:
        配置表DataFrame
    """
    config_rows = []

    # 建立mapping的快速查找
    mapping_dict = {}
    for _, row in mapping_df.iterrows():
        key = (str(row['id']), row['landuse_id'])
        mapping_dict[key] = row['side']

    for topo in topology_list:
        lid = topo['landuse_id']
        for road in topo['road_sequence']:
            rid = road['road_id']
            r_seq = road['sequence']
            for pt in road['streetview_points']:
                sid = str(pt['streetview_id'])
                pt_seq = pt['sequence']

                side = mapping_dict.get((sid, lid))
                if not side:
                    continue

                new_filename = f"P{lid}_R{rid}_S{sid}_{side}.jpg"

                config_rows.append({
                    'landuse_id': lid,
                    'road_id': rid,
                    'road_sequence': r_seq,
                    'streetview_id': sid,
                    'streetview_sequence': pt_seq,
                    'side': side,
                    'filename': new_filename
                })

    df = pd.DataFrame(config_rows)
    df.to_csv(os.path.join(output_dir, 'landuse_traversal_config.csv'), index=False, encoding='utf-8')
    return df


def execute_rename(config_df, img_dir):
    """
    根据配置表重命名图片

    Args:
        config_df: 配置表DataFrame
        img_dir: 图片目录
    """
    from tqdm import tqdm

    print("开始重命名图片...")

    if not os.path.exists(img_dir):
        print(f"图片目录不存在: {img_dir}")
        return

    current_files = set(os.listdir(img_dir))

    count = 0
    skipped = 0

    for _, row in tqdm(config_df.iterrows(), total=len(config_df), desc="重命名"):
        sid = str(row['streetview_id'])
        side = row['side']
        target_name = row['filename']

        src_name = f"{sid}_{side}.jpg"

        src_path = os.path.join(img_dir, src_name)
        target_path = os.path.join(img_dir, target_name)

        if src_name in current_files and src_name != target_name:
            try:
                if os.path.exists(target_path):
                    os.remove(target_path)
                os.rename(src_path, target_path)
                current_files.discard(src_name)
                current_files.add(target_name)
                count += 1
            except Exception as e:
                print(f"重命名失败 {src_name}: {e}")
        elif target_name in current_files:
            skipped += 1

    print(f"重命名完成: 成功 {count} 个, 跳过 {skipped} 个")
