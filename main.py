import os
import pandas as pd
from shapely.geometry import Point
import cv2
import numpy as np
from tqdm import tqdm 

from landuse_utils import read_landuse_gdb
from streetview_utils import read_streetview_points, wgs84_to_bd09mc, get_streetview_metadata, download_panorama_image
from image_utils import equirectangular_to_perspective
from spatial_analysis import judge_left_right
from topology_utils import (read_road_gdb, build_streetview_road_mapping, 
                           build_landuse_topology, build_multi_landuse_mapping,
                           generate_traversal_config, generate_multi_landuse_mapping)

def rename_images_by_topology(config_df, img_dir):
    """根据拓扑关系重命名图片文件"""
    print(f"开始重命名图片文件，共 {len(config_df)} 条配置...")
    
    # 创建旧文件名到新文件名的映射
    rename_mapping = {}
    
    # 按街景点ID分组，确保左右图对应正确的地块
    streetview_groups = {}
    for _, row in config_df.iterrows():
        streetview_id = str(row['streetview_id'])  # 转换为字符串确保类型一致
        landuse_id = row['landuse_id']
        road_id = row['road_id']
        filename = row['filename']
        
        if streetview_id not in streetview_groups:
            streetview_groups[streetview_id] = {}
        
        # 根据文件名中的L/R判断左右
        if '_L.jpg' in filename:
            streetview_groups[streetview_id]['left'] = {
                'landuse_id': landuse_id,
                'road_id': road_id,
                'filename': filename
            }
        elif '_R.jpg' in filename:
            streetview_groups[streetview_id]['right'] = {
                'landuse_id': landuse_id,
                'road_id': road_id,
                'filename': filename
            }
    
    # 为每个街景点创建正确的重命名映射
    for streetview_id, sides in streetview_groups.items():
        # 旧文件名格式：{streetview_id}_L.jpg, {streetview_id}_R.jpg
        old_filename_L = f"{streetview_id}_L.jpg"
        old_filename_R = f"{streetview_id}_R.jpg"
        
        # 左图重命名
        if 'left' in sides:
            new_filename_L = sides['left']['filename']
            rename_mapping[old_filename_L] = new_filename_L
        
        # 右图重命名
        if 'right' in sides:
            new_filename_R = sides['right']['filename']
            rename_mapping[old_filename_R] = new_filename_R
    
    # 执行重命名
    renamed_count = 0
    for old_name, new_name in rename_mapping.items():
        old_path = os.path.join(img_dir, old_name)
        new_path = os.path.join(img_dir, new_name)
        
        if os.path.exists(old_path):
            try:
                # 如果新文件名已存在，先删除
                if os.path.exists(new_path):
                    os.remove(new_path)
                    print(f"删除已存在的文件: {new_name}")
                
                # 重命名文件
                os.rename(old_path, new_path)
                renamed_count += 1
                print(f"重命名成功: {old_name} -> {new_name}")
            except Exception as e:
                print(f"重命名失败 {old_name} -> {new_name}: {e}")
        else:
            print(f"文件不存在: {old_path}")
    
    print(f"重命名完成，共重命名 {renamed_count} 个文件")

def update_streetview_mapping_filenames(mapping_df, config_df, output_dir):
    """更新streetview_landuse_mapping.csv中的filename字段"""
    print("开始更新streetview_landuse_mapping.csv中的filename字段...")
    
    # 创建一个字典，用于查找每个街景点在特定地块中的新文件名
    filename_mapping = {}
    for _, row in config_df.iterrows():
        landuse_id = row['landuse_id']
        streetview_id = str(row['streetview_id'])  # 转换为字符串确保类型一致
        filename = row['filename']
        
        # 根据文件名中的L/R判断左右
        if '_L.jpg' in filename:
            side = 'L'
        elif '_R.jpg' in filename:
            side = 'R'
        else:
            continue  # 跳过不符合命名规则的文件
        
        # 使用(landuse_id, streetview_id, side)作为键
        filename_mapping[(landuse_id, streetview_id, side)] = filename
    
    # 更新mapping_df中的filename字段
    updated_count = 0
    for idx, row in mapping_df.iterrows():
        landuse_id = row['landuse_id']
        streetview_id = str(row['streetview_id'])  # 转换为字符串确保类型一致
        side = row['side']
        
        key = (landuse_id, streetview_id, side)
        if key in filename_mapping:
            mapping_df.at[idx, 'filename'] = filename_mapping[key]
            updated_count += 1
    
    # 保存更新后的文件
    mapping_csv = os.path.join(output_dir, 'streetview_landuse_mapping.csv')
    mapping_df.to_csv(mapping_csv, index=False, encoding='utf-8')
    mapping_df.to_json(os.path.join(output_dir, 'streetview_landuse_mapping.json'), orient='records', force_ascii=False)
    
    print(f"成功更新 {updated_count} 个文件名。")

def main(
    landuse_gdb_path,
    landuse_layer='landuse',
    landuse_id_col='OBJECTID',
    road_layer='road_街景测试范围_0712',
    road_id_col='OBJECTID',
    streetview_csv_path='resources/example.csv',
    baidu_ak='',
    output_dir='output',
    zoom=3,
    save_front_back=False,
    save_every=50,
    build_topology=True,
    traversal_direction='clockwise'
):
    os.makedirs(output_dir, exist_ok=True)
    img_dir = os.path.join(output_dir, 'images')
    os.makedirs(img_dir, exist_ok=True)
    mapping = []
    # 断点续存：读取已处理的id或(x, y)
    processed_keys = set()
    mapping_csv = os.path.join(output_dir, 'streetview_landuse_mapping.csv')
    if os.path.exists(mapping_csv):
        try:
            old_df = pd.read_csv(mapping_csv)
            if 'id' in old_df.columns:
                processed_keys = set(old_df['id'].astype(str))
            else:
                processed_keys = set(zip(old_df['x'], old_df['y']))
            # 断点续存时，先加载已有内容
            mapping = old_df.to_dict('records')
            print(f"[断点续存] 已检测到 {len(processed_keys)} 个已处理点，将跳过这些点。")
        except Exception as e:
            print(f"[断点续存] 读取已有 mapping 文件失败：{e}")
    # 读取数据
    print("正在读取数据...")
    landuse_gdf = read_landuse_gdb(landuse_gdb_path, landuse_layer, landuse_id_col)
    road_gdf = read_road_gdb(landuse_gdb_path, road_layer, road_id_col)
    sv_points = read_streetview_points(streetview_csv_path)
    
    print(f"读取完成：地块 {len(landuse_gdf)} 个，道路 {len(road_gdf)} 条，街景点 {len(sv_points)} 个")
    
    # 建立街景点-道路映射
    print("正在建立街景点-道路映射...")
    streetview_road_mapping = build_streetview_road_mapping(sv_points, road_gdf, road_id_col)
    # 过滤未处理点
    filtered_points = []
    for pt_info in sv_points:
        if len(pt_info) == 3:
            id_val, x, y = pt_info
            key = str(id_val)
        else:
            id_val = None
            x, y = pt_info
            key = (x, y)
        if key not in processed_keys:
            filtered_points.append(pt_info)
    print(f"共 {len(sv_points)} 个点，未处理 {len(filtered_points)} 个点。")
    for idx, pt_info in enumerate(tqdm(filtered_points, desc='Processing streetview points')):
        if len(pt_info) == 3:
            id_val, x, y = pt_info
        else:
            id_val = None
            x, y = pt_info
        try:
            x_bd, y_bd = wgs84_to_bd09mc(x, y, baidu_ak)
            sid, meta = get_streetview_metadata(x_bd, y_bd)
            if not sid or not meta:
                print(f"No streetview at {x},{y}")
                continue
            heading = float(meta.get('Heading', 0))
            # 使用heading作为基准，不使用movedir
            capture_time = meta.get('Time', '')
            pano_img = download_panorama_image(sid, zoom=zoom)
            if pano_img is None:
                print(f"Failed to download panorama for {sid}")
                continue
            pano_np = cv2.cvtColor(np.array(pano_img), cv2.COLOR_RGB2BGR)
            out_size = (1024, 683)
            fov_h = 120
            fov_v = 90
            left_view = equirectangular_to_perspective(pano_np, fov_h, fov_v, 0, 0, out_size)
            right_view = equirectangular_to_perspective(pano_np, fov_h, fov_v, 180, 0, out_size)
            
            # 获取街景点对应的道路ID
            road_id = None
            for sv_mapping in streetview_road_mapping:
                if sv_mapping['original_id'] == id_val:
                    road_id = sv_mapping['road_id']
                    break
            
            # 使用新的命名规则：P{landuse_id}_R{道路ID}_S{街景点ID}_{L/R}.jpg
            # 暂时使用街景点ID，后续会根据landuse关联更新
            base_name = str(id_val) if id_val is not None else str(sid)
            fname_L = f"{base_name}_L.jpg"  # 临时命名，后续会重命名
            fname_R = f"{base_name}_R.jpg"  # 临时命名，后续会重命名
            
            cv2.imwrite(os.path.join(img_dir, fname_L), left_view)
            cv2.imwrite(os.path.join(img_dir, fname_R), right_view)
            if save_front_back:
                front_view = equirectangular_to_perspective(pano_np, fov_h, fov_v, 90, 0, out_size)
                back_view = equirectangular_to_perspective(pano_np, fov_h, fov_v, 270, 0, out_size)
                fname_F = f"{base_name}_front.jpg"
                fname_B = f"{base_name}_back.jpg"
                cv2.imwrite(os.path.join(img_dir, fname_F), front_view)
                cv2.imwrite(os.path.join(img_dir, fname_B), back_view)
            pt = Point(x, y)
            # 先找到最近的两个地块（不考虑左右）
            landuse_distances = []
            for _, row in landuse_gdf.iterrows():
                if 'GH_LAYOUT' in row and row['GH_LAYOUT'] in ['S1']:
                    continue
                dist = pt.distance(row['geometry'])
                landuse_distances.append({
                    'row': row,
                    'distance': dist
                })
            
            # 按距离排序，取最近的两个地块
            landuse_distances.sort(key=lambda x: x['distance'])
            nearest_two = landuse_distances[:2]
            
            # 在最近的两个地块中判断左右
            left_row = None
            right_row = None
            
            if len(nearest_two) >= 2:
                # 对最近的两个地块进行左右判断
                for item in nearest_two:
                    row = item['row']
                    centroid = (row['centroid_x'], row['centroid_y'])
                    side = judge_left_right((x, y), heading, centroid)
                    
                    if side == 'L' and left_row is None:
                        left_row = row
                    elif side == 'R' and right_row is None:
                        right_row = row
                    elif side == 'L' and left_row is not None:
                        # 如果左侧已有地块，选择距离更近的
                        if item['distance'] < pt.distance(left_row['geometry']):
                            right_row = left_row  # 原来的左侧地块变成右侧
                            left_row = row
                        else:
                            right_row = row
                    elif side == 'R' and right_row is not None:
                        # 如果右侧已有地块，选择距离更近的
                        if item['distance'] < pt.distance(right_row['geometry']):
                            left_row = right_row  # 原来的右侧地块变成左侧
                            right_row = row
                        else:
                            left_row = row
            if left_row is not None:
                mapping.append({
                    'streetview_id': sid,
                    'filename': fname_L,
                    'landuse_id': left_row[landuse_id_col],
                    'side': 'L',
                    'heading': heading,
                    'capture_time': capture_time,
                    'x': x,
                    'y': y,
                    'id': id_val
                })
            if right_row is not None:
                mapping.append({
                    'streetview_id': sid,
                    'filename': fname_R,
                    'landuse_id': right_row[landuse_id_col],
                    'side': 'R',
                    'heading': heading,
                    'capture_time': capture_time,
                    'x': x,
                    'y': y,
                    'id': id_val
                })
            print(f"Processed streetview {sid} at {x},{y}")
        except Exception as e:
            print(f"Error processing point {x},{y}: {e}")
        # 定期保存
        if ((idx + 1) % save_every == 0) or (idx == len(filtered_points) - 1):
            df = pd.DataFrame(mapping)
            df.to_csv(os.path.join(output_dir, 'streetview_landuse_mapping.csv'), index=False, encoding='utf-8')
            df.to_json(os.path.join(output_dir, 'streetview_landuse_mapping.json'), orient='records', force_ascii=False)
            print(f"[进度保存] 已保存 {len(mapping)} 条记录。")
    # 构建拓扑关系
    if build_topology:
        print("正在构建拓扑关系...")
        
        # 读取当前的streetview_landuse_mapping.csv
        mapping_csv = os.path.join(output_dir, 'streetview_landuse_mapping.csv')
        if os.path.exists(mapping_csv):
            streetview_landuse_mapping = pd.read_csv(mapping_csv)
        else:
            streetview_landuse_mapping = pd.DataFrame(mapping)
        
        # 获取所有地块ID（排除S1地块）
        filtered_landuse_gdf = landuse_gdf[~((landuse_gdf['GH_LAYOUT'] == 'S1') & (landuse_gdf['GH_LAYOUT'].notna()))]
        landuse_ids = filtered_landuse_gdf[landuse_id_col].unique()
        
        # 为每个地块建立拓扑
        topology_data = []
        for landuse_id in tqdm(landuse_ids, desc='Building topology'):
            try:
                topology = build_landuse_topology(landuse_id, streetview_road_mapping, landuse_gdf, landuse_id_col, streetview_landuse_mapping, traversal_direction=traversal_direction)
                if topology['road_sequence']:  # 只保存有关联道路的地块
                    topology_data.append(topology)
            except Exception as e:
                print(f"Error building topology for landuse {landuse_id}: {e}")
        
        # 生成遍历配置表
        print("正在生成遍历配置表...")
        config_df = generate_traversal_config(topology_data, streetview_landuse_mapping, output_dir)
        
        # 建立多地块关联
        print("正在建立多地块关联...")
        multi_mapping_data = build_multi_landuse_mapping(streetview_road_mapping, landuse_gdf, landuse_id_col, streetview_landuse_mapping, traversal_direction)
        mapping_df = generate_multi_landuse_mapping(multi_mapping_data, output_dir)
        
        print(f"拓扑关系构建完成：")
        print(f"- 遍历配置表：{len(config_df)} 条记录")
        print(f"- 多地块关联表：{len(mapping_df)} 条记录")
        
        # 更新streetview_landuse_mapping.csv中的filename字段
        print("正在更新streetview_landuse_mapping.csv中的filename字段...")
        update_streetview_mapping_filenames(streetview_landuse_mapping, config_df, output_dir)
        
        # 重命名图片文件以符合拓扑关系命名规则
        print("正在重命名图片文件...")
        rename_images_by_topology(config_df, img_dir)
    
    print(f"Done! All files saved to {output_dir}")

if __name__ == '__main__':
    main(
        landuse_gdb_path=r'D:/卫星图测试.gdb',# 地块gdb文件
        landuse_layer='landuse',# 地块图层
        landuse_id_col='GH_ZXC_2_I',# 地块id列
        road_layer='road_街景测试范围_0712',# 道路图层
        road_id_col='OBJECTID',# 道路id列
        streetview_csv_path='example.csv',# 街景点csv文件
        baidu_ak='XXXXXXXX',# 百度地图API密钥
        output_dir='output',# 输出目录
        zoom=2,# 街景缩放级别
        save_every=50,# 保存间隔
        build_topology=False,# 构建拓扑关系  
        traversal_direction='clockwise' # clockwise, counterclockwise
    ) 