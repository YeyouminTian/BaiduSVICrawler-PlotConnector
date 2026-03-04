import os
import pandas as pd
import geopandas as gpd
import numpy as np
import cv2
import requests
import json
import math
import re
import time
from collections import defaultdict
from shapely.geometry import Point
from shapely.ops import nearest_points
from PIL import Image
from io import BytesIO
from tqdm import tqdm
from math import radians, cos, sin, atan2, sqrt, pi

# 屏蔽Pandas的SettingWithCopyWarning警告
pd.options.mode.chained_assignment = None

# ============================================================================
# 工具函数：投影转换与计算
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

def read_landuse_gdb(gdb_path, layer_name='landuse', id_col='OBJECTID'):
    print(f"正在读取图层: {layer_name} ...")
    gdf = gpd.read_file(gdb_path, layer=layer_name)
    
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
# 街景数据读取和处理
# ============================================================================

def read_streetview_points(csv_path):
    df = pd.read_csv(csv_path)
    
    points = []
    id_col = None
    x_col = None
    y_col = None
    
    for c in df.columns:
        cl = c.lower()
        if cl == 'id':
            id_col = c
        elif cl == 'x':
            x_col = c
        elif cl == 'y':
            y_col = c
    
    if x_col and y_col:
        if id_col:
            points = df[[id_col, x_col, y_col]].values.tolist()
        else:
            points = df[[x_col, y_col]].values.tolist()
    else:
        if df.shape[1] >= 3:
            points = df.iloc[:, :3].values.tolist()
        elif df.shape[1] == 2:
            points = df.iloc[:, :2].values.tolist()
            
    return points

def wgs84_to_bd09mc(x, y, ak):
    """WGS84转百度墨卡托"""
    url = f"http://api.map.baidu.com/geoconv/v1/?coords={x},{y}&from=1&to=6&ak={ak}"
    try:
        resp = requests.get(url, timeout=10)
        data = json.loads(resp.text)
        if data.get('status') == 0:
            return data['result'][0]['x'], data['result'][0]['y']
    except Exception as e:
        print(f"坐标转换请求错误: {e}")
    return None, None

def get_streetview_metadata(x_bd, y_bd):
    """获取街景元数据"""
    url = f"https://mapsv0.bdimg.com/?qt=qsdata&x={x_bd}&y={y_bd}"
    try:
        resp = requests.get(url, timeout=10)
        data = json.loads(resp.text)
        if 'content' not in data or not data['content']:
            return None, None
        sid = data['content'].get('id')
        if not sid:
            return None, None
            
        meta_url = f"https://mapsv0.bdimg.com/?qt=sdata&sid={sid}"
        meta_resp = requests.get(meta_url, timeout=10)
        meta_data = json.loads(meta_resp.text)
        if 'content' in meta_data:
            content = meta_data['content']
            if isinstance(content, list) and content:
                content = content[0]
            return sid, content
        return sid, None
    except Exception:
        return None, None

def download_panorama_image(sid, zoom=3, retries=3):
    """下载全景图"""
    if zoom == 1:
        xrange, yrange = 1, 1
    elif zoom == 2:
        xrange, yrange = 1, 2
    elif zoom == 3:
        xrange, yrange = 2, 4
    elif zoom == 4:
        xrange, yrange = 4, 8
    else:
        xrange, yrange = 2, 4
    
    img_dict = {}
    
    for x in range(xrange):
        for y in range(yrange):
            key = (x, y)
            success = False
            for attempt in range(retries):
                try:
                    url = f"https://mapsv1.bdimg.com/?qt=pdata&sid={sid}&pos={x}_{y}&z={zoom}&from=PC"
                    resp = requests.get(url, timeout=15)
                    if resp.status_code == 200:
                        img = Image.open(BytesIO(resp.content))
                        img_dict[key] = img
                        success = True
                        break
                except Exception:
                    time.sleep(0.5 * (attempt + 1))
            if not success:
                return None

    if not img_dict:
        return None
        
    w, h = img_dict[(0, 0)].size
    pano = Image.new("RGB", (w * yrange, h * xrange))
    for (row, col), img in img_dict.items():
        pano.paste(img, (col * w, row * h))
    return pano

# ============================================================================
# 图像投影处理 - 使用原始正确的实现
# ============================================================================

def equirectangular_to_perspective(img, fov_h, fov_v, heading, pitch, out_size):
    """
    将全景图转换为透视图
    使用原始正确的实现方式
    """
    out_w, out_h = out_size
    height, width = img.shape[:2]
    
    xx, yy = np.meshgrid(np.arange(out_w), np.arange(out_h))
    x = (xx - out_w / 2) / (out_w / 2) * np.tan(np.radians(fov_h / 2))
    y = (yy - out_h / 2) / (out_h / 2) * np.tan(np.radians(fov_v / 2))
    z = np.ones_like(x)
    
    norm = np.sqrt(x ** 2 + y ** 2 + z ** 2)
    x /= norm
    y /= norm
    z /= norm
    
    heading_rad = np.radians(heading)
    pitch_rad = np.radians(pitch)
    
    x_rot = x * np.cos(heading_rad) + z * np.sin(heading_rad)
    y_rot = y
    z_rot = -x * np.sin(heading_rad) + z * np.cos(heading_rad)
    
    x_final = x_rot
    y_final = y_rot * np.cos(pitch_rad) - z_rot * np.sin(pitch_rad)
    z_final = y_rot * np.sin(pitch_rad) + z_rot * np.cos(pitch_rad)
    
    lon = np.arctan2(x_final, z_final)
    lat = np.arcsin(np.clip(y_final, -1, 1))
    
    x_map = (lon / (2 * np.pi) + 0.5) * width
    y_map = (lat / np.pi + 0.5) * height
    
    perspective = cv2.remap(img, x_map.astype(np.float32), y_map.astype(np.float32), 
                           cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
    return perspective

# ============================================================================
# 空间分析与左右判断 - 局部切线法（核心算法）
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
    # 找到车所在位置在道路上的投影
    dist = road_geom.project(pt_proj)
    
    # 获取局部切线
    delta = 0.5
    total_len = road_geom.length
    
    if dist + delta <= total_len:
        p1 = road_geom.interpolate(dist)
        p2 = road_geom.interpolate(dist + delta)
    elif dist >= delta:
        p1 = road_geom.interpolate(dist - delta)
        p2 = road_geom.interpolate(dist)
    else:
        # 道路太短，取首尾
        p1 = road_geom.interpolate(0)
        p2 = road_geom.interpolate(min(delta, total_len))
        
    tangent = np.array([p2.x - p1.x, p2.y - p1.y])
    
    # 归一化
    norm = np.linalg.norm(tangent)
    if norm > 0:
        tangent = tangent / norm
    
    # 计算点积判断方向
    if np.dot(tangent, heading_vec) < 0:
        return -1  # 道路几何方向与车行相反
    return 1       # 同向

def get_tangent_at_distance(road_geom, dist, direction):
    """
    获取道路在指定距离处的切线向量，并根据道路流向进行修正
    """
    delta = 0.5
    total_len = road_geom.length
    
    # 防止越界
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
    
    # 归一化
    norm = np.linalg.norm(vec)
    if norm == 0:
        return np.array([0, 1])  # 异常保护
    vec = vec / norm
    
    # 根据方向修正 (如果道路几何是反的，切线也要反过来)
    return vec * direction

def determine_side_robust(pt_proj, heading, road_gdf_proj, road_sindex, candidates, landuse_id_col, verbose=False):
    """
    终极稳健算法：基于道路流向 + 质心投影的局部切线法
    解决弯道和零距离问题
    
    参数:
        pt_proj: 街景点的投影坐标 (Point)
        heading: 街景车的朝向角度
        road_gdf_proj: 投影后的道路GeoDataFrame
        road_sindex: 道路的空间索引
        candidates: 候选地块GeoDataFrame
        landuse_id_col: 地块ID列名
        verbose: 是否打印详细日志
    
    返回:
        left_candidates: [(landuse_id, distance), ...] 按距离排序
        right_candidates: [(landuse_id, distance), ...] 按距离排序
    """
    if verbose:
        print(f"\n  街景点坐标: ({pt_proj.x:.2f}, {pt_proj.y:.2f})")
    
    # 1. 计算 Heading 向量
    theta = radians(90 - heading)
    heading_vec = np.array([cos(theta), sin(theta)])
    
    # 2. 找到最近的道路
    nearest_road, road_dist, road_idx = find_nearest_road(pt_proj, road_gdf_proj, road_sindex)
    
    is_pure_heading = False
    road_direction = 1
    
    if nearest_road is None:
        if verbose:
            print("  警告: 未找到附近道路，回退到纯Heading模式")
        is_pure_heading = True
    else:
        if verbose:
            print(f"  最近道路距离: {road_dist:.2f}m")
        # 3. 确定整条道路相对于车行方向是顺还是逆
        road_direction = determine_road_direction(nearest_road, pt_proj, heading_vec)
        if verbose:
            status = "同向" if road_direction == 1 else "反向(已自动翻转)"
            print(f"  道路几何流向: {status}")

    left_candidates = []
    right_candidates = []
    
    if verbose:
        print("\n  逐个地块判断 (使用局部切线法):")
    
    for idx, row in candidates.iterrows():
        landuse_id = row[landuse_id_col]
        geom = row.geometry
        centroid = geom.centroid
        
        if is_pure_heading:
            # 纯Heading模式：使用街景点位置和heading向量
            final_vec = heading_vec
            origin_pt = pt_proj
            proj_dist = 0
        else:
            # 局部切线法
            # A. 将质心投影到道路上，找到"道路上离该地块最近的点"
            proj_dist = nearest_road.project(centroid)
            
            # B. 获取该特定位置的道路切线
            final_vec = get_tangent_at_distance(nearest_road, proj_dist, road_direction)
            
            # 投影点坐标 (用于计算向量)
            p_on_road = nearest_road.interpolate(proj_dist)
            origin_pt = p_on_road
            
        # C. 计算向量：参考点 -> 地块质心
        obj_vec = np.array([centroid.x - origin_pt.x, centroid.y - origin_pt.y])
        
        # D. 叉积判断
        cross = final_vec[0] * obj_vec[1] - final_vec[1] * obj_vec[0]
        side = 'L' if cross > 0 else 'R'
        
        # 计算到地块边界的距离
        dist_to_border = pt_proj.distance(geom)
        
        if verbose:
            print(f"    地块 {landuse_id}: 质心投影位置={proj_dist:.1f}m, "
                  f"局部切线=[{final_vec[0]:.2f},{final_vec[1]:.2f}], "
                  f"叉积={cross:.1f} → {side}")
        
        if side == 'L':
            left_candidates.append((landuse_id, dist_to_border))
        else:
            right_candidates.append((landuse_id, dist_to_border))
    
    # 按距离排序
    left_candidates.sort(key=lambda x: x[1])
    right_candidates.sort(key=lambda x: x[1])
    
    return left_candidates, right_candidates

def determine_side_strict(sv_point, sv_heading, candidate_geoms, candidate_ids, 
                          road_gdf_proj=None, road_sindex=None, landuse_id_col='OBJECTID',
                          use_local_tangent=True):
    """
    判断候选地块是在街景点的左侧还是右侧
    支持两种模式：
    1. 局部切线法 (use_local_tangent=True) - 更精确，需要道路数据
    2. 纯Heading法 (use_local_tangent=False) - 快速，不需要道路数据
    
    返回: l_id, l_dist, r_id, r_dist
    """
    if use_local_tangent and road_gdf_proj is not None and road_sindex is not None:
        # 构建临时的candidates GeoDataFrame
        candidates_data = []
        for geom, oid in zip(candidate_geoms, candidate_ids):
            candidates_data.append({landuse_id_col: oid, 'geometry': geom})
        
        if not candidates_data:
            return None, float('inf'), None, float('inf')
            
        candidates_gdf = gpd.GeoDataFrame(candidates_data, crs=road_gdf_proj.crs)
        
        left_list, right_list = determine_side_robust(
            sv_point, sv_heading, road_gdf_proj, road_sindex, 
            candidates_gdf, landuse_id_col, verbose=False
        )
        
        l_id, l_dist = (left_list[0] if left_list else (None, float('inf')))
        r_id, r_dist = (right_list[0] if right_list else (None, float('inf')))
        
        return l_id, l_dist, r_id, r_dist
    
    else:
        # 原始的纯Heading方法
        theta = radians(90 - sv_heading)
        road_vec = np.array([cos(theta), sin(theta)])
        
        left_candidates = []
        right_candidates = []
        
        for geom, oid in zip(candidate_geoms, candidate_ids):
            nearest_pt_on_poly = nearest_points(sv_point, geom)[1]
            dist = sv_point.distance(geom)
            
            dx = nearest_pt_on_poly.x - sv_point.x
            dy = nearest_pt_on_poly.y - sv_point.y
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
# 拓扑排序相关
# ============================================================================

def calculate_angle(origin, point):
    """计算点相对于原点的角度 (0-2pi, 正北为0, 顺时针)"""
    dx = point[0] - origin[0]
    dy = point[1] - origin[1]
    angle = math.atan2(dx, dy)
    if angle < 0:
        angle += 2 * math.pi
    return angle

def build_landuse_topology(landuse_id, streetview_road_mapping, landuse_gdf, landuse_id_col, 
                           streetview_landuse_mapping, traversal_direction='clockwise'):
    """为单个地块建立道路和街景点的拓扑顺序"""
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

    # 道路排序
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

# ============================================================================
# 配置生成与重命名
# ============================================================================

def generate_final_config(topology_list, mapping_df, output_dir):
    """生成最终的遍历配置表"""
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
    """根据配置表重命名图片"""
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

# ============================================================================
# 主程序
# ============================================================================

def main(
    landuse_gdb_path,
    landuse_layer,
    landuse_id_col,
    road_layer,
    road_id_col,
    streetview_csv_path,
    baidu_ak,
    output_dir,
    zoom=3,
    save_every=50,
    build_topology=True,
    traversal_direction='clockwise',
    test_limit=None,
    distance_threshold=100,
    search_buffer=500,
    use_local_tangent=True,  # 新增：是否使用局部切线法
    verbose_matching=False   # 新增：是否打印详细匹配日志
):
    # 1. 初始化
    os.makedirs(output_dir, exist_ok=True)
    img_dir = os.path.join(output_dir, 'images')
    os.makedirs(img_dir, exist_ok=True)
    
    print("=" * 60)
    print("读取数据中...")
    print("=" * 60)
    
    landuse_gdf = read_landuse_gdb(landuse_gdb_path, landuse_layer, landuse_id_col)
    print(f"读取地块 {len(landuse_gdf)} 个")
    
    print(f"正在读取道路图层: {road_layer} ...")
    road_gdf = gpd.read_file(landuse_gdb_path, layer=road_layer)
    if road_gdf.crs and road_gdf.crs.to_epsg() != 4326:
        road_gdf = road_gdf.to_crs(epsg=4326)
    elif road_gdf.crs is None:
        road_gdf = road_gdf.set_crs(epsg=4326)
    print(f"读取道路 {len(road_gdf)} 条")
    
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
        use_local_tangent=True,    # 启用局部切线法
        verbose_matching=True     # 设为True可查看详细匹配日志
    )