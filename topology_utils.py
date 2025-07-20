import pandas as pd
import geopandas as gpd
import numpy as np
from shapely.geometry import Point
import math
import os
from collections import defaultdict

def read_road_gdb(gdb_path, road_layer='road_街景测试范围_0712', road_id_col='OBJECTID'):
    """读取道路数据"""
    gdf = gpd.read_file(gdb_path, layer=road_layer)
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    return gdf

def find_nearest_road(streetview_point, road_gdf, road_id_col='OBJECTID'):
    """为街景点找到最近的道路"""
    point = Point(streetview_point[0], streetview_point[1])
    min_distance = float('inf')
    nearest_road_id = None
    
    for _, road_row in road_gdf.iterrows():
        distance = point.distance(road_row.geometry)
        if distance < min_distance:
            min_distance = distance
            nearest_road_id = road_row[road_id_col]
    
    return nearest_road_id

def calculate_angle(centroid, point):
    """计算点相对于质心的角度"""
    dx = point[0] - centroid[0]
    dy = point[1] - centroid[1]
    return math.atan2(dy, dx)

def sort_roads_by_angle(landuse_centroid, road_centroids, clockwise=True):
    """按角度对道路排序"""
    road_angles = []
    for road_id, centroid in road_centroids.items():
        angle = calculate_angle(landuse_centroid, centroid)
        road_angles.append((road_id, angle))
    
    # 按角度排序
    road_angles.sort(key=lambda x: x[1], reverse=clockwise)
    return [road_id for road_id, _ in road_angles]

def sort_streetview_in_road(road_id, streetview_points, clockwise=True):
    """对单条道路内的街景点排序 - 使用沿着道路方向的线性排序"""
    if not streetview_points:
        return []
    
    # 计算道路的方向向量
    # 使用所有街景点的坐标来计算道路的主方向
    x_coords = [pt['x'] for pt in streetview_points]
    y_coords = [pt['y'] for pt in streetview_points]
    
    # 计算道路的主方向（使用PCA或简单的线性拟合）
    # 这里使用简单的线性拟合方法
    n = len(x_coords)
    if n < 2:
        return streetview_points
    
    # 计算道路的主方向向量
    x_mean = np.mean(x_coords)
    y_mean = np.mean(y_coords)
    
    # 计算协方差矩阵
    cov_xx = np.sum((np.array(x_coords) - x_mean) ** 2)
    cov_xy = np.sum((np.array(x_coords) - x_mean) * (np.array(y_coords) - y_mean))
    cov_yy = np.sum((np.array(y_coords) - y_mean) ** 2)
    
    # 计算主方向角度
    if cov_xx != cov_yy:
        angle = 0.5 * np.arctan2(2 * cov_xy, cov_xx - cov_yy)
    else:
        angle = np.pi / 4  # 如果协方差相等，使用45度
    
    # 计算每个点沿道路方向的投影
    projections = []
    for pt in streetview_points:
        # 计算点相对于道路中心的偏移
        dx = pt['x'] - x_mean
        dy = pt['y'] - y_mean
        
        # 计算沿道路方向的投影
        projection = dx * np.cos(angle) + dy * np.sin(angle)
        projections.append((pt, projection))
    
    # 按投影值排序
    projections.sort(key=lambda x: x[1], reverse=not clockwise)
    return [pt for pt, _ in projections]

def build_streetview_road_mapping(streetview_points, road_gdf, road_id_col='OBJECTID'):
    """建立街景点-道路映射关系"""
    mapping = []
    
    for pt_info in streetview_points:
        if len(pt_info) == 3:
            id_val, x, y = pt_info
        else:
            id_val = None
            x, y = pt_info
        
        road_id = find_nearest_road((x, y), road_gdf, road_id_col)
        
        mapping.append({
            'streetview_id': str(id_val) if id_val is not None else f"SV_{x}_{y}",
            'x': x,
            'y': y,
            'road_id': road_id,
            'original_id': id_val
        })
    
    return mapping

def build_landuse_topology(landuse_id, streetview_road_mapping, landuse_gdf, landuse_id_col, streetview_landuse_mapping, traversal_direction='clockwise'):
    """为单个地块建立道路和街景点的拓扑顺序"""
    # 获取地块信息
    landuse_row = landuse_gdf[landuse_gdf[landuse_id_col] == landuse_id].iloc[0]
    landuse_centroid = (landuse_row['centroid_x'], landuse_row['centroid_y'])
    
    # 从streetview_landuse_mapping中获取该地块关联的街景点
    landuse_streetviews = []
    for _, row in streetview_landuse_mapping.iterrows():
        if row['landuse_id'] == landuse_id:
            original_id = row['id']
            # 在streetview_road_mapping中找到对应的街景点
            for sv_mapping in streetview_road_mapping:
                if sv_mapping.get('original_id') == original_id:
                    landuse_streetviews.append(sv_mapping)
                    break
    
    # 按道路分组
    road_groups = defaultdict(list)
    for sv in landuse_streetviews:
        road_groups[sv['road_id']].append(sv)
    
    # 计算每条道路的质心
    road_centroids = {}
    for road_id, sv_list in road_groups.items():
        if sv_list:
            centroid_x = np.mean([sv['x'] for sv in sv_list])
            centroid_y = np.mean([sv['y'] for sv in sv_list])
            road_centroids[road_id] = (centroid_x, centroid_y)
    
    # 确定遍历方向
    clockwise = (traversal_direction.lower() == 'clockwise')
    
    # 按角度对道路排序
    road_sequence = sort_roads_by_angle(landuse_centroid, road_centroids, clockwise=clockwise)
    
    # 构建拓扑结构
    topology = {
        'landuse_id': landuse_id,
        'road_sequence': []
    }
    
    for road_seq, road_id in enumerate(road_sequence, 1):
        if road_id in road_groups:
            # 对道路内的街景点排序
            sorted_streetviews = sort_streetview_in_road(road_id, road_groups[road_id], clockwise=clockwise)
            
            road_topology = {
                'road_id': road_id,
                'sequence': road_seq,
                'streetview_points': []
            }
            
            for pt_seq, sv in enumerate(sorted_streetviews, 1):
                road_topology['streetview_points'].append({
                    'streetview_id': sv['streetview_id'],
                    'sequence': pt_seq,
                    'x': sv['x'],
                    'y': sv['y']
                })
            
            topology['road_sequence'].append(road_topology)
    
    return topology

def build_multi_landuse_mapping(streetview_road_mapping, landuse_gdf, landuse_id_col, streetview_landuse_mapping, traversal_direction='clockwise'):
    """建立街景点在多地块中的位置关系 - 只对应左右视图的两个地块"""
    multi_mapping = []
    
    # 从streetview_landuse_mapping中获取每个街景点的左右地块映射
    sv_landuse_map = {}
    for _, row in streetview_landuse_mapping.iterrows():
        sv_id = row['streetview_id']
        landuse_id = row['landuse_id']
        side = row['side']
        original_id = row['id']  # 使用原始ID进行匹配
        
        if original_id not in sv_landuse_map:
            sv_landuse_map[original_id] = {}
        
        if side == 'L':
            sv_landuse_map[original_id]['left'] = landuse_id
        elif side == 'R':
            sv_landuse_map[original_id]['right'] = landuse_id
    
    for sv_mapping in streetview_road_mapping:
        sv_id = sv_mapping['streetview_id']
        original_id = sv_mapping.get('original_id')
        x, y = sv_mapping['x'], sv_mapping['y']
        road_id = sv_mapping['road_id']
        
        # 使用original_id进行匹配
        if original_id is None or original_id not in sv_landuse_map:
            continue
        
        # 获取该街景点的左右地块
        left_landuse_id = sv_landuse_map[original_id].get('left')
        right_landuse_id = sv_landuse_map[original_id].get('right')
        
        landuse_relations = []
        
        # 只为左右视图对应的地块建立拓扑关系
        for landuse_id in [left_landuse_id, right_landuse_id]:
            if landuse_id is None:
                continue
                
            # 为每个地块建立拓扑
            topology = build_landuse_topology(landuse_id, streetview_road_mapping, landuse_gdf, landuse_id_col, streetview_landuse_mapping, traversal_direction)
            
            # 找到该街景点在该地块中的位置
            for road_info in topology['road_sequence']:
                if road_info['road_id'] == road_id:
                    for pt_info in road_info['streetview_points']:
                        if pt_info['streetview_id'] == sv_id:
                            landuse_relations.append({
                                'landuse_id': landuse_id,
                                'road_id': road_id,
                                'road_sequence': road_info['sequence'],
                                'point_sequence': pt_info['sequence']
                            })
                            break
        
        if landuse_relations:
            multi_mapping.append({
                'streetview_id': sv_id,
                'landuse_relations': landuse_relations
            })
    
    return multi_mapping

def generate_traversal_config(topology_data, streetview_landuse_mapping, output_dir):
    """生成地块遍历配置表 - 只包含与streetview_landuse_mapping.csv一致的地块关联"""
    config_data = []
    
    # 创建街景点到地块的映射
    sv_landuse_map = {}
    for _, row in streetview_landuse_mapping.iterrows():
        original_id = row['id']
        landuse_id = row['landuse_id']
        side = row['side']
        
        if original_id not in sv_landuse_map:
            sv_landuse_map[original_id] = {}
        
        if side == 'L':
            sv_landuse_map[original_id]['left'] = landuse_id
        elif side == 'R':
            sv_landuse_map[original_id]['right'] = landuse_id
    
    # 只处理在streetview_landuse_mapping中有记录的街景点
    for _, row in streetview_landuse_mapping.iterrows():
        original_id = row['id']
        landuse_id = row['landuse_id']
        side = row['side']
        
        # 找到该街景点在拓扑数据中的位置
        for landuse_topology in topology_data:
            if landuse_topology['landuse_id'] == landuse_id:
                for road_info in landuse_topology['road_sequence']:
                    road_id = road_info['road_id']
                    
                    for pt_info in road_info['streetview_points']:
                        # 检查是否是同一个街景点
                        if str(pt_info['streetview_id']) == str(original_id):
                            # 直接使用拓扑数据中的序号
                            road_sequence = road_info['sequence']
                            streetview_sequence = pt_info['sequence']
                            
                            # 确定文件名
                            if side == 'L':
                                filename = f"P{landuse_id}_R{road_id}_S{original_id}_L.jpg"
                            else:
                                filename = f"P{landuse_id}_R{road_id}_S{original_id}_R.jpg"
                            
                            config_data.append({
                                'landuse_id': landuse_id,
                                'road_id': road_id,
                                'road_sequence': road_sequence,
                                'streetview_id': original_id,
                                'streetview_sequence': streetview_sequence,
                                'filename': filename
                            })
                            break
    
    # 按照landuse_id, road_sequence, streetview_sequence排序
    config_data.sort(key=lambda x: (x['landuse_id'], x['road_sequence'], x['streetview_sequence']))
    
    # 保存配置表
    config_df = pd.DataFrame(config_data)
    config_df.to_csv(os.path.join(output_dir, 'landuse_traversal_config.csv'), 
                     index=False, encoding='utf-8')
    
    return config_df

def generate_multi_landuse_mapping(multi_mapping_data, output_dir):
    """生成街景点多地块关联表"""
    mapping_data = []
    
    for sv_mapping in multi_mapping_data:
        sv_id = sv_mapping['streetview_id']
        
        for relation in sv_mapping['landuse_relations']:
            mapping_data.append({
                'streetview_id': sv_id,
                'landuse_id': relation['landuse_id'],
                'road_id': relation['road_id'],
                'road_sequence': relation['road_sequence'],
                'point_sequence': relation['point_sequence']
            })
    
    # 保存关联表
    mapping_df = pd.DataFrame(mapping_data)
    mapping_df.to_csv(os.path.join(output_dir, 'streetview_multi_landuse_mapping.csv'), 
                      index=False, encoding='utf-8')
    
    return mapping_df 