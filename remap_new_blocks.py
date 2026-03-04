import os
import pandas as pd
import geopandas as gpd
import numpy as np
import shutil
from shapely.geometry import Point
from tqdm import tqdm
from math import radians, cos, sin
from collections import defaultdict
import math

# 屏蔽Pandas的SettingWithCopyWarning警告
pd.options.mode.chained_assignment = None

# ============================================================================
# 工具函数：投影转换与计算（从main_merged.py复用）
# ============================================================================

def get_utm_crs(lon, lat):
    """根据经纬度自动计算合适的UTM投影EPSG代码"""
    zone = int((lon + 180) / 6) + 1
    if lat >= 0:
        epsg_code = 32600 + zone
    else:
        epsg_code = 32700 + zone
    return f"EPSG:{epsg_code}"

def project_gdf(gdf, target_crs=None):
    """将GDF投影到米制坐标系"""
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    
    gdf_wgs84 = gdf.to_crs(epsg=4326) if gdf.crs.to_epsg() != 4326 else gdf
    
    if target_crs is None:
        bounds = gdf_wgs84.total_bounds
        center_lon = (bounds[0] + bounds[2]) / 2
        center_lat = (bounds[1] + bounds[3]) / 2
        target_crs = get_utm_crs(center_lon, center_lat)
        print(f"自动选择投影: {target_crs} (中心点: {center_lon:.4f}, {center_lat:.4f})")
    
    return gdf_wgs84.to_crs(target_crs), target_crs

# ============================================================================
# 地块数据读取
# ============================================================================

def read_block_data(block_path, layer_name=None, id_col='OBJECTID'):
    """
    读取地块数据，支持GDB和SHP文件
    """
    print(f"正在读取地块数据: {block_path}")
    
    if block_path.endswith('.gdb') or block_path.endswith('.gdb/'):
        if layer_name is None:
            raise ValueError("GDB文件必须指定layer_name参数")
        print(f"  图层: {layer_name}")
        gdf = gpd.read_file(block_path, layer=layer_name)
    else:
        # SHP文件
        gdf = gpd.read_file(block_path)
    
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    elif gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)

    if id_col not in gdf.columns:
        if id_col == 'OBJECTID':
            gdf[id_col] = gdf.index
        else:
            raise KeyError(f"列 '{id_col}' 未在数据集中找到。可用列: {gdf.columns.tolist()}")
    
    if 'GH_LAYOUT' not in gdf.columns:
        gdf['GH_LAYOUT'] = None

    # 使用投影坐标系计算质心
    bounds = gdf.total_bounds
    center_lon = (bounds[0] + bounds[2]) / 2
    center_lat = (bounds[1] + bounds[3]) / 2
    utm_crs = get_utm_crs(center_lon, center_lat)
    
    gdf_proj = gdf.to_crs(utm_crs)
    centroids_proj = gdf_proj.geometry.centroid
    centroids_wgs84 = gpd.GeoSeries(centroids_proj, crs=utm_crs).to_crs(epsg=4326)
    
    gdf['centroid_geo'] = centroids_wgs84
    gdf['centroid_x'] = centroids_wgs84.x
    gdf['centroid_y'] = centroids_wgs84.y
    
    return gdf

# ============================================================================
# 空间分析与左右判断（从main_merged.py复用）
# ============================================================================

def find_nearest_road(pt_proj, road_gdf_proj, road_sindex, search_buffer=500):
    """
    找到距离街景点最近的道路
    返回: (道路几何, 距离, 道路索引) 或 (None, inf, None)
    """
    buffer_bounds = pt_proj.buffer(search_buffer).bounds
    idx_candidates = list(road_sindex.intersection(buffer_bounds))
    
    nearest_road = None
    min_dist = float('inf')
    nearest_idx = None
    
    if idx_candidates:
        for idx in idx_candidates:
            road_geom = road_gdf_proj.iloc[idx].geometry
            d = pt_proj.distance(road_geom)
            if d < min_dist:
                min_dist = d
                nearest_road = road_geom
                nearest_idx = idx
    
    # 如果缓冲区内没找到，扩大搜索
    if nearest_road is None:
        for idx, row in road_gdf_proj.iterrows():
            d = pt_proj.distance(row.geometry)
            if d < min_dist:
                min_dist = d
                nearest_road = row.geometry
                nearest_idx = idx
                
    return nearest_road, min_dist, nearest_idx

def determine_road_direction(road_geom, pt_proj, heading_vec):
    """
    判断道路几何的方向与车行Heading是否一致
    返回: 1 (同向) 或 -1 (反向)
    """
    dist = road_geom.project(pt_proj)
    
    delta = 0.5
    total_len = road_geom.length
    
    if dist + delta <= total_len:
        p1 = road_geom.interpolate(dist)
        p2 = road_geom.interpolate(dist + delta)
    elif dist >= delta:
        p1 = road_geom.interpolate(dist - delta)
        p2 = road_geom.interpolate(dist)
    else:
        p1 = road_geom.interpolate(0)
        p2 = road_geom.interpolate(min(delta, total_len))
        
    tangent = np.array([p2.x - p1.x, p2.y - p1.y])
    
    norm = np.linalg.norm(tangent)
    if norm > 0:
        tangent = tangent / norm
    
    if np.dot(tangent, heading_vec) < 0:
        return -1
    return 1

def get_tangent_at_distance(road_geom, dist, direction):
    """
    获取道路在指定距离处的切线向量，并根据道路流向进行修正
    """
    delta = 0.5
    total_len = road_geom.length
    
    d_start = dist
    d_end = dist + delta
    
    if d_end > total_len:
        d_start = max(0, total_len - delta)
        d_end = total_len
    if d_start < 0:
        d_start = 0
        d_end = min(delta, total_len)
        
    p1 = road_geom.interpolate(d_start)
    p2 = road_geom.interpolate(d_end)
    
    vec = np.array([p2.x - p1.x, p2.y - p1.y])
    
    norm = np.linalg.norm(vec)
    if norm == 0:
        return np.array([0, 1])
    vec = vec / norm
    
    return vec * direction

def determine_side_strict(sv_point, sv_heading, candidate_geoms, candidate_ids, 
                          road_gdf_proj=None, road_sindex=None, block_id_col='OBJECTID',
                          use_local_tangent=True):
    """
    判断候选地块是在街景点的左侧还是右侧
    返回: l_id, l_dist, r_id, r_dist
    """
    if use_local_tangent and road_gdf_proj is not None and road_sindex is not None:
        # 构建临时的candidates GeoDataFrame
        candidates_data = []
        for geom, oid in zip(candidate_geoms, candidate_ids):
            candidates_data.append({block_id_col: oid, 'geometry': geom})
        
        if not candidates_data:
            return None, float('inf'), None, float('inf')
            
        candidates_gdf = gpd.GeoDataFrame(candidates_data, crs=road_gdf_proj.crs)
        
        # 计算 Heading 向量
        theta = radians(90 - sv_heading)
        heading_vec = np.array([cos(theta), sin(theta)])
        
        # 找到最近的道路
        nearest_road, road_dist, road_idx = find_nearest_road(sv_point, road_gdf_proj, road_sindex)
        
        is_pure_heading = False
        road_direction = 1
        
        if nearest_road is None:
            is_pure_heading = True
        else:
            road_direction = determine_road_direction(nearest_road, sv_point, heading_vec)

        left_candidates = []
        right_candidates = []
        
        for idx, row in candidates_gdf.iterrows():
            block_id = row[block_id_col]
            geom = row.geometry
            centroid = geom.centroid
            
            if is_pure_heading:
                final_vec = heading_vec
                origin_pt = sv_point
            else:
                proj_dist = nearest_road.project(centroid)
                final_vec = get_tangent_at_distance(nearest_road, proj_dist, road_direction)
                p_on_road = nearest_road.interpolate(proj_dist)
                origin_pt = p_on_road
            
            obj_vec = np.array([centroid.x - origin_pt.x, centroid.y - origin_pt.y])
            cross = final_vec[0] * obj_vec[1] - final_vec[1] * obj_vec[0]
            side = 'L' if cross > 0 else 'R'
            
            dist_to_border = sv_point.distance(geom)
            
            if side == 'L':
                left_candidates.append((block_id, dist_to_border))
            else:
                right_candidates.append((block_id, dist_to_border))
        
        left_candidates.sort(key=lambda x: x[1])
        right_candidates.sort(key=lambda x: x[1])
        
        l_id, l_dist = (left_candidates[0] if left_candidates else (None, float('inf')))
        r_id, r_dist = (right_candidates[0] if right_candidates else (None, float('inf')))
        
        return l_id, l_dist, r_id, r_dist
    
    else:
        # 纯Heading方法
        theta = radians(90 - sv_heading)
        road_vec = np.array([cos(theta), sin(theta)])
        
        left_candidates = []
        right_candidates = []
        
        for geom, oid in zip(candidate_geoms, candidate_ids):
            dist = sv_point.distance(geom)
            centroid = geom.centroid
            
            dx = centroid.x - sv_point.x
            dy = centroid.y - sv_point.y
            obj_vec = np.array([dx, dy])
            
            cross_product = road_vec[0] * obj_vec[1] - road_vec[1] * obj_vec[0]
            
            if cross_product > 0:
                left_candidates.append((oid, dist))
            else:
                right_candidates.append((oid, dist))
                
        l_id, l_dist = None, float('inf')
        if left_candidates:
            left_candidates.sort(key=lambda x: x[1])
            l_id, l_dist = left_candidates[0]
            
        r_id, r_dist = None, float('inf')
        if right_candidates:
            right_candidates.sort(key=lambda x: x[1])
            r_id, r_dist = right_candidates[0]
            
        return l_id, l_dist, r_id, r_dist

# ============================================================================
# 拓扑排序相关（从main_merged.py复用）
# ============================================================================

def calculate_angle(origin, point):
    """计算点相对于原点的角度 (0-2pi, 正北为0, 顺时针)"""
    dx = point[0] - origin[0]
    dy = point[1] - origin[1]
    angle = math.atan2(dx, dy)
    if angle < 0:
        angle += 2 * math.pi
    return angle

def build_block_topology(block_id, streetview_road_mapping, block_gdf, block_id_col, 
                           streetview_block_mapping, traversal_direction='clockwise'):
    """为单个地块建立道路和街景点的拓扑顺序"""
    try:
        block_row = block_gdf[block_gdf[block_id_col] == block_id].iloc[0]
    except IndexError:
        return None
        
    block_centroid = (block_row['centroid_x'], block_row['centroid_y'])
    
    # 筛选关联的街景点
    related_records = streetview_block_mapping[streetview_block_mapping['block_id'] == block_id]
    related_sv_ids = related_records['id'].unique()
    
    # 将街景点按道路归类
    road_groups = defaultdict(list)
    sv_lookup = {item['original_id']: item for item in streetview_road_mapping}
    sv_lookup_str = {str(k): v for k, v in sv_lookup.items()}
    
    for sv_id in related_sv_ids:
        sv_info = None
        if sv_id in sv_lookup:
            sv_info = sv_lookup[sv_id]
        elif str(sv_id) in sv_lookup_str:
            sv_info = sv_lookup_str[str(sv_id)]
        elif isinstance(sv_id, str) and sv_id.isdigit():
            if int(sv_id) in sv_lookup:
                sv_info = sv_lookup[int(sv_id)]
            
        if sv_info and sv_info['road_id'] is not None:
            road_groups[sv_info['road_id']].append(sv_info)
    
    if not road_groups:
        return None

    # 道路排序
    road_centroids = {}
    for rid, points in road_groups.items():
        cx = np.mean([p['x'] for p in points])
        cy = np.mean([p['y'] for p in points])
        road_centroids[rid] = (cx, cy)
    
    road_angles = []
    for rid, rc in road_centroids.items():
        ang = calculate_angle(block_centroid, rc)
        road_angles.append((rid, ang))
    
    is_clockwise = (traversal_direction == 'clockwise')
    road_angles.sort(key=lambda x: x[1], reverse=not is_clockwise)
    
    topology = {
        'block_id': block_id,
        'road_sequence': []
    }
    
    for seq_idx, (road_id, _) in enumerate(road_angles, 1):
        points = road_groups[road_id]
        points_with_angle = []
        for p in points:
            ang = calculate_angle(block_centroid, (p['x'], p['y']))
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

# ============================================================================
# 配置生成与文件复制
# ============================================================================

def generate_final_config(topology_list, mapping_df, output_dir):
    """生成最终的遍历配置表"""
    config_rows = []
    
    # 建立mapping的快速查找
    mapping_dict = {}
    for _, row in mapping_df.iterrows():
        key = (str(row['id']), row['block_id'])
        mapping_dict[key] = row['side']
    
    for topo in topology_list:
        lid = topo['block_id']
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
                    'block_id': lid,
                    'road_id': rid,
                    'road_sequence': r_seq,
                    'streetview_id': sid,
                    'streetview_sequence': pt_seq,
                    'side': side,
                    'filename': new_filename
                })
                
    df = pd.DataFrame(config_rows)
    df.to_csv(os.path.join(output_dir, 'block_traversal_config.csv'), index=False, encoding='utf-8')
    return df

def copy_and_rename_images(config_df, old_img_dir, new_img_dir, old_mapping_df):
    """
    根据配置表复制并重命名图片
    保留原文件，在新目录创建新文件
    """
    print("开始复制并重命名图片...")
    
    if not os.path.exists(old_img_dir):
        print(f"原图片目录不存在: {old_img_dir}")
        return
    
    os.makedirs(new_img_dir, exist_ok=True)
    
    # 建立旧文件名到新文件名的映射
    # 需要从old_mapping_df中找到原始文件名
    old_filename_map = {}
    for _, row in old_mapping_df.iterrows():
        sid = str(row['id'])
        side = row['side']
        old_filename = row.get('filename', f"{sid}_{side}.jpg")
        key = (sid, side)
        old_filename_map[key] = old_filename
    
    count = 0
    skipped = 0
    not_found = 0
    
    for _, row in tqdm(config_df.iterrows(), total=len(config_df), desc="复制重命名"):
        sid = str(row['streetview_id'])
        side = row['side']
        target_name = row['filename']
        
        # 尝试从old_mapping_df中获取原始文件名
        old_filename = old_filename_map.get((sid, side), f"{sid}_{side}.jpg")
        
        src_path = os.path.join(old_img_dir, old_filename)
        target_path = os.path.join(new_img_dir, target_name)
        
        if os.path.exists(src_path):
            try:
                # 如果目标文件已存在，跳过（避免重复）
                if not os.path.exists(target_path):
                    shutil.copy2(src_path, target_path)
                    count += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"复制失败 {old_filename} -> {target_name}: {e}")
        else:
            not_found += 1
            if not_found <= 10:  # 只打印前10个未找到的文件
                print(f"未找到原文件: {old_filename}")
            
    print(f"复制完成: 成功 {count} 个, 跳过 {skipped} 个, 未找到 {not_found} 个")

# ============================================================================
# 主程序
# ============================================================================

def main(
    # 新地块数据
    new_block_path,
    new_block_layer=None,  # 如果是shp文件，这个参数会被忽略
    new_block_id_col='ORIG_FID',
    
    # 道路数据
    road_path=None,
    road_layer=None,
    road_id_col='ID',
    
    # 已有数据路径
    old_output_dir=None,  # 之前的输出目录，包含mapping文件和图片
    old_mapping_file=None,  # 或者直接指定mapping文件路径
    
    # 输出配置
    new_output_dir=None,
    
    # 匹配参数
    distance_threshold=100,
    search_buffer=500,
    use_local_tangent=True,
    traversal_direction='clockwise',
    verbose=False
):
    """
    重新映射新地块数据到已有街景数据
    """
    print("=" * 60)
    print("重新映射新地块数据")
    print("=" * 60)
    
    # 1. 读取已有映射文件
    print("\n读取已有映射文件...")
    if old_mapping_file and os.path.exists(old_mapping_file):
        old_mapping_df = pd.read_csv(old_mapping_file)
        old_img_dir = os.path.join(os.path.dirname(old_mapping_file), 'images')
    elif old_output_dir:
        mapping_path = os.path.join(old_output_dir, 'streetview_block_mapping.csv')
        if not os.path.exists(mapping_path):
            raise FileNotFoundError(f"未找到映射文件: {mapping_path}")
        old_mapping_df = pd.read_csv(mapping_path)
        old_img_dir = os.path.join(old_output_dir, 'images')
    else:
        raise ValueError("必须指定old_output_dir或old_mapping_file")
    
    print(f"读取到 {len(old_mapping_df)} 条映射记录")
    
    # 2. 读取新地块数据
    print("\n读取新地块数据...")
    new_block_gdf = read_block_data(new_block_path, new_block_layer, new_block_id_col)
    print(f"读取地块 {len(new_block_gdf)} 个")
    
    # 3. 读取道路数据
    print("\n读取道路数据...")
    if road_path is None:
        road_path = new_block_path  # 默认使用地块数据路径
    
    if road_path.endswith('.gdb') or road_path.endswith('.gdb/'):
        road_gdf = gpd.read_file(road_path, layer=road_layer)
    else:
        road_gdf = gpd.read_file(road_path)
    
    if road_gdf.crs and road_gdf.crs.to_epsg() != 4326:
        road_gdf = road_gdf.to_crs(epsg=4326)
    elif road_gdf.crs is None:
        road_gdf = road_gdf.set_crs(epsg=4326)
    print(f"读取道路 {len(road_gdf)} 条")
    
    # 4. 准备空间分析环境
    print("\n构建空间索引与投影...")
    new_block_gdf_proj, utm_crs = project_gdf(new_block_gdf)
    new_block_sindex = new_block_gdf_proj.sindex
    
    road_gdf_proj = road_gdf.to_crs(utm_crs)
    road_sindex = road_gdf_proj.sindex
    
    print(f"使用{'局部切线法' if use_local_tangent else '纯Heading法'}进行左右判断")
    
    # 5. 建立街景点-道路映射（基于已有坐标）
    print("\n建立街景点-道路关联...")
    sv_road_map = []
    
    # 从old_mapping_df中提取唯一的街景点
    unique_sv_points = old_mapping_df[['id', 'x', 'y', 'heading']].drop_duplicates(subset=['id'])
    
    road_search_buffer = 200
    no_road_count = 0
    
    for _, row in tqdm(unique_sv_points.iterrows(), total=len(unique_sv_points), desc="道路匹配"):
        sv_id = str(row['id'])
        x, y = row['x'], row['y']
        
        p_geom_wgs = Point(x, y)
        p_geom_proj = gpd.GeoSeries([p_geom_wgs], crs="EPSG:4326").to_crs(utm_crs)[0]
        
        nearest_road, min_d, nearest_idx = find_nearest_road(
            p_geom_proj, road_gdf_proj, road_sindex, road_search_buffer
        )
        
        nearest_rid = None
        if nearest_idx is not None:
            nearest_rid = road_gdf_proj.iloc[nearest_idx][road_id_col]
        
        if nearest_rid is None:
            no_road_count += 1
        
        sv_road_map.append({
            'original_id': sv_id,
            'x': x,
            'y': y,
            'road_id': nearest_rid,
            'road_distance': min_d if min_d != float('inf') else None
        })
    
    if no_road_count > 0:
        print(f"警告: {no_road_count} 个点未找到匹配道路")
    
    # 6. 重新匹配街景点到新地块
    print("\n重新匹配街景点到新地块...")
    new_mapping_records = []
    no_match_count = 0
    no_candidates_count = 0
    distance_too_far_count = 0
    wrong_side_count = 0
    
    for _, old_row in tqdm(old_mapping_df.iterrows(), total=len(old_mapping_df), desc="地块匹配"):
        sv_id = str(old_row['id'])
        x = old_row['x']
        y = old_row['y']
        heading = old_row.get('heading', 0)
        old_side = old_row['side']
        old_filename = old_row.get('filename', f"{sv_id}_{old_side}.jpg")
        
        # 空间查询
        pt_wgs = Point(x, y)
        pt_proj = gpd.GeoSeries([pt_wgs], crs="EPSG:4326").to_crs(utm_crs)[0]
        
        buffer_bounds = pt_proj.buffer(search_buffer).bounds
        possible_idxs = list(new_block_sindex.intersection(buffer_bounds))
        
        if not possible_idxs:
            no_match_count += 1
            no_candidates_count += 1
            continue
        
        candidates = new_block_gdf_proj.iloc[possible_idxs].copy()
        
        # 排除非实体地块
        if 'GH_LAYOUT' in candidates.columns:
            candidates = candidates[candidates['GH_LAYOUT'] != 'S1']
        
        if len(candidates) == 0:
            no_match_count += 1
            no_candidates_count += 1
            continue
        
        cand_geoms = candidates.geometry.tolist()
        cand_ids = candidates[new_block_id_col].tolist()
        
        # 判断左右侧（与 main_merged.py 逻辑一致：先判断左右，再检查距离）
        l_id, l_dist, r_id, r_dist = determine_side_strict(
            pt_proj, heading, cand_geoms, cand_ids,
            road_gdf_proj=road_gdf_proj if use_local_tangent else None,
            road_sindex=road_sindex if use_local_tangent else None,
            block_id_col=new_block_id_col,
            use_local_tangent=use_local_tangent
        )
        
        # 根据原side选择匹配的地块（与 main_merged.py 逻辑一致）
        matched_block_id = None
        matched_dist = float('inf')
        
        if old_side == 'L':
            if l_id is not None and l_dist < distance_threshold:
                matched_block_id = l_id
                matched_dist = l_dist
            else:
                # 左侧没有匹配，直接跳过
                no_match_count += 1
                if l_id is None:
                    # 左侧没有候选地块（所有候选地块都在右侧）
                    wrong_side_count += 1
                else:
                    # 左侧有候选但距离太远
                    distance_too_far_count += 1
                continue
        elif old_side == 'R':
            if r_id is not None and r_dist < distance_threshold:
                matched_block_id = r_id
                matched_dist = r_dist
            else:
                # 右侧没有匹配，直接跳过
                no_match_count += 1
                if r_id is None:
                    # 右侧没有候选地块（所有候选地块都在左侧）
                    wrong_side_count += 1
                else:
                    # 右侧有候选但距离太远
                    distance_too_far_count += 1
                continue
        
        if matched_block_id is not None:
            new_mapping_records.append({
                'id': sv_id,
                'streetview_id': old_row.get('streetview_id', sv_id),
                'filename': old_filename,  # 保留原文件名
                'block_id': matched_block_id,
                'side': old_side,
                'x': x,
                'y': y,
                'heading': heading,
                'capture_time': old_row.get('capture_time', ''),
                'distance': matched_dist
            })
        else:
            no_match_count += 1
    
    print(f"\n匹配统计:")
    print(f"  成功匹配: {len(new_mapping_records)} 条")
    print(f"  未匹配总数: {no_match_count} 条")
    print(f"    - 缓冲区内无候选地块: {no_candidates_count} 条")
    print(f"    - 距离超过阈值 ({distance_threshold}m): {distance_too_far_count} 条")
    print(f"    - 左右侧不匹配: {wrong_side_count} 条")
    
    new_mapping_df = pd.DataFrame(new_mapping_records)
    print(f"成功匹配 {len(new_mapping_df)} 条记录")
    
    # 7. 构建拓扑关系
    print("\n构建拓扑结构...")
    topology_results = []
    all_lids = new_mapping_df['block_id'].unique()
    
    for lid in tqdm(all_lids, desc="拓扑构建"):
        topo = build_block_topology(lid, sv_road_map, new_block_gdf, new_block_id_col, 
                                      new_mapping_df, traversal_direction)
        if topo:
            topology_results.append(topo)
    
    print(f"构建拓扑: {len(topology_results)} 个地块")
    
    # 8. 生成配置表和复制文件
    print("\n生成配置表...")
    if new_output_dir is None:
        new_output_dir = 'svi_new_blocks'
    
    os.makedirs(new_output_dir, exist_ok=True)
    new_img_dir = os.path.join(new_output_dir, 'images')
    
    config_df = generate_final_config(topology_results, new_mapping_df, new_output_dir)
    print(f"生成配置表: {len(config_df)} 条记录")
    
    # 保存新映射文件
    new_mapping_df.to_csv(os.path.join(new_output_dir, 'streetview_block_mapping.csv'), 
                         index=False, encoding='utf-8')
    new_mapping_df.to_json(os.path.join(new_output_dir, 'streetview_block_mapping.json'), 
                          orient='records', force_ascii=False)
    
    # 复制并重命名图片
    copy_and_rename_images(config_df, old_img_dir, new_img_dir, old_mapping_df)
    
    # 更新映射表中的filename
    print("\n更新映射表文件名...")
    fname_map = {}
    for _, row in config_df.iterrows():
        key = (str(row['streetview_id']), row['side'])
        fname_map[key] = row['filename']
    
    def update_fname(row):
        key = (str(row['id']), row['side'])
        return fname_map.get(key, row['filename'])
    
    new_mapping_df['filename'] = new_mapping_df.apply(update_fname, axis=1)
    new_mapping_df.to_csv(os.path.join(new_output_dir, 'streetview_block_mapping.csv'), 
                         index=False, encoding='utf-8')
    new_mapping_df.to_json(os.path.join(new_output_dir, 'streetview_block_mapping.json'), 
                          orient='records', force_ascii=False)
    
    print("\n" + "=" * 60)
    print("处理完成！")
    print(f"输出目录: {new_output_dir}")
    print("=" * 60)

if __name__ == '__main__':
    main(
        # 新地块数据
        new_block_path=r'D:\LifeOS\01Projects\GraduateThesis\251118街景+虹口测试\hongkou_test\hongkou_test.gdb',
        new_block_layer='hk_251207_result',
        new_block_id_col='ORIG_FID',
        
        # 道路数据（可以用原来的）
        road_path=r'D:\LifeOS\01Projects\GraduateThesis\251118街景+虹口测试\hongkou_test\hongkou_test.gdb',
        road_layer='road_hongkou_251206',
        road_id_col='ID',
        
        # 已有数据路径
        old_output_dir='svi_251206',  # 之前的输出目录
        
        # 输出配置
        new_output_dir='svi_251207',  # 新输出目录
        
        # 匹配参数
        distance_threshold=100,
        search_buffer=500,
        use_local_tangent=True,
        traversal_direction='clockwise',
        verbose=False
    )

