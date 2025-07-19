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
    """对单条道路内的街景点排序"""
    if not streetview_points:
        return []
    
    # 计算道路内街景点的质心
    road_centroid_x = np.mean([pt['x'] for pt in streetview_points])
    road_centroid_y = np.mean([pt['y'] for pt in streetview_points])
    road_centroid = (road_centroid_x, road_centroid_y)
    
    # 按角度排序
    angles = []
    for pt in streetview_points:
        angle = calculate_angle(road_centroid, (pt['x'], pt['y']))
        angles.append((pt, angle))
    
    angles.sort(key=lambda x: x[1], reverse=clockwise)
    return [pt for pt, _ in angles]

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

def build_landuse_topology(landuse_id, streetview_road_mapping, landuse_gdf, landuse_id_col):
    """为单个地块建立道路和街景点的拓扑顺序"""
    # 获取地块信息
    landuse_row = landuse_gdf[landuse_gdf[landuse_id_col] == landuse_id].iloc[0]
    landuse_centroid = (landuse_row['centroid_x'], landuse_row['centroid_y'])
    
    # 收集该地块相关的街景点
    landuse_streetviews = []
    for sv_mapping in streetview_road_mapping:
        # 检查街景点是否与该地块关联
        x, y = sv_mapping['x'], sv_mapping['y']
        point = Point(x, y)
        
        # 计算距离，如果足够近则认为有关联
        dist = point.distance(landuse_row.geometry)
        if dist < 0.002:  # 阈值可调整
            landuse_streetviews.append(sv_mapping)
    
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
    
    # 按角度对道路排序
    road_sequence = sort_roads_by_angle(landuse_centroid, road_centroids, clockwise=True)
    
    # 构建拓扑结构
    topology = {
        'landuse_id': landuse_id,
        'road_sequence': []
    }
    
    for road_seq, road_id in enumerate(road_sequence, 1):
        if road_id in road_groups:
            # 对道路内的街景点排序
            sorted_streetviews = sort_streetview_in_road(road_id, road_groups[road_id], clockwise=True)
            
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

def build_multi_landuse_mapping(streetview_road_mapping, landuse_gdf, landuse_id_col):
    """建立街景点在多地块中的位置关系"""
    multi_mapping = []
    
    for sv_mapping in streetview_road_mapping:
        sv_id = sv_mapping['streetview_id']
        x, y = sv_mapping['x'], sv_mapping['y']
        road_id = sv_mapping['road_id']
        
        # 找到该街景点关联的所有地块
        point = Point(x, y)
        landuse_relations = []
        
        for _, landuse_row in landuse_gdf.iterrows():
            if 'GH_LAYOUT' in landuse_row and landuse_row['GH_LAYOUT'] == 'S1':
                continue
            
            # 计算距离，如果足够近则认为有关联
            dist = point.distance(landuse_row.geometry)
            if dist < 0.002:  # 阈值可调整
                landuse_id = landuse_row[landuse_id_col]
                
                # 为每个地块建立拓扑
                topology = build_landuse_topology(landuse_id, streetview_road_mapping, landuse_gdf, landuse_id_col)
                
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

def generate_traversal_config(topology_data, output_dir):
    """生成地块遍历配置表"""
    config_data = []
    
    for landuse_topology in topology_data:
        landuse_id = landuse_topology['landuse_id']
        
        for road_info in landuse_topology['road_sequence']:
            road_id = road_info['road_id']
            road_sequence = road_info['sequence']
            
            for pt_info in road_info['streetview_points']:
                sv_id = pt_info['streetview_id']
                point_sequence = pt_info['sequence']
                
                # 生成文件名
                filename_L = f"P{landuse_id}_R{road_id}_S{sv_id}_L.jpg"
                filename_R = f"P{landuse_id}_R{road_id}_S{sv_id}_R.jpg"
                
                config_data.append({
                    'landuse_id': landuse_id,
                    'road_id': road_id,
                    'road_sequence': road_sequence,
                    'streetview_id': sv_id,
                    'point_sequence': point_sequence,
                    'filename_L': filename_L,
                    'filename_R': filename_R
                })
    
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