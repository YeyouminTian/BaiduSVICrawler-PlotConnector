"""
空间分析与左右判断模块
支持局部切线法和纯Heading法
"""
import numpy as np
import geopandas as gpd
from math import radians, cos, sin
from shapely.geometry import Point
from shapely.ops import nearest_points


# ============================================================================
# 基础方法：纯Heading法
# ============================================================================

def judge_left_right(streetview_pt, road_dir, block_centroid):
    """
    判断街坊/地块相对于街景点的左右位置（使用叉乘）

    Args:
        streetview_pt: 街景点坐标 (x, y)
        road_dir: 道路方向角度（度，0=正北，90=正东，180=正南，270=正西）
        block_centroid: 街坊/地块质心坐标 (x, y)

    Returns:
        'L' 或 'R': 街坊/地块相对于街景点的左右位置
    """
    dx = block_centroid[0] - streetview_pt[0]
    dy = block_centroid[1] - streetview_pt[1]

    # 计算道路方向向量（单位向量）
    theta = radians(90 - road_dir)  # 转换为数学坐标系
    road_vec = np.array([cos(theta), sin(theta)])

    # 计算街坊/地块到街景点的向量
    block_vec = np.array([dx, dy])

    # 计算叉积：block_vec × road_vec
    cross = block_vec[0] * road_vec[1] - block_vec[1] * road_vec[0]

    # 如果叉积为正，街坊/地块在道路方向的左侧；否则在右侧
    return 'L' if cross > 0 else 'R'


# ============================================================================
# 高级方法：局部切线法
# ============================================================================

def find_nearest_road(pt_proj, road_gdf_proj, road_sindex, search_buffer=500):
    """
    找到距离街景点最近的道路

    Args:
        pt_proj: 街景点的投影坐标 (Point对象)
        road_gdf_proj: 投影后的道路GeoDataFrame
        road_sindex: 道路的空间索引
        search_buffer: 搜索缓冲区（米）

    Returns:
        (道路几何, 距离, 道路索引) 或 (None, inf, None)
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

    Args:
        road_geom: 道路几何
        pt_proj: 街景点投影坐标
        heading_vec: Heading向量

    Returns:
        1 (同向) 或 -1 (反向)
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

    Args:
        road_geom: 道路几何
        dist: 投影距离
        direction: 方向修正系数（1或-1）

    Returns:
        切线向量（numpy数组）
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


def determine_side_robust(pt_proj, heading, road_gdf_proj, road_sindex, candidates, block_id_col, verbose=False):
    """
    终极稳健算法：基于道路流向 + 质心投影的局部切线法
    解决弯道和零距离问题

    Args:
        pt_proj: 街景点的投影坐标 (Point)
        heading: 街景车的朝向角度
        road_gdf_proj: 投影后的道路GeoDataFrame
        road_sindex: 道路的空间索引
        candidates: 候选地块GeoDataFrame
        block_id_col: 地块ID列名
        verbose: 是否打印详细日志

    Returns:
        left_candidates: [(block_id, distance), ...] 按距离排序
        right_candidates: [(block_id, distance), ...] 按距离排序
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
        block_id = row[block_id_col]
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
            print(f"    地块 {block_id}: 质心投影位置={proj_dist:.1f}m, "
                  f"局部切线=[{final_vec[0]:.2f},{final_vec[1]:.2f}], "
                  f"叉积={cross:.1f} → {side}")

        if side == 'L':
            left_candidates.append((block_id, dist_to_border))
        else:
            right_candidates.append((block_id, dist_to_border))

    # 按距离排序
    left_candidates.sort(key=lambda x: x[1])
    right_candidates.sort(key=lambda x: x[1])

    return left_candidates, right_candidates


def determine_side_strict(sv_point, sv_heading, candidate_geoms, candidate_ids,
                          road_gdf_proj=None, road_sindex=None, block_id_col='OBJECTID',
                          use_local_tangent=True):
    """
    判断候选地块是在街景点的左侧还是右侧
    支持两种模式：
    1. 局部切线法 (use_local_tangent=True) - 更精确，需要道路数据
    2. 纯Heading法 (use_local_tangent=False) - 快速，不需要道路数据

    Args:
        sv_point: 街景点投影坐标 (Point对象)
        sv_heading: 街景车朝向角度
        candidate_geoms: 候选地块几何列表
        candidate_ids: 候选地块ID列表
        road_gdf_proj: 投影后的道路GeoDataFrame（局部切线法需要）
        road_sindex: 道路空间索引（局部切线法需要）
        block_id_col: 地块ID列名
        use_local_tangent: 是否使用局部切线法

    Returns:
        (left_id, left_dist, right_id, right_dist)
    """
    if use_local_tangent and road_gdf_proj is not None and road_sindex is not None:
        # 构建临时的candidates GeoDataFrame
        candidates_data = []
        for geom, oid in zip(candidate_geoms, candidate_ids):
            candidates_data.append({block_id_col: oid, 'geometry': geom})

        if not candidates_data:
            return None, float('inf'), None, float('inf')

        candidates_gdf = gpd.GeoDataFrame(candidates_data, crs=road_gdf_proj.crs)

        left_list, right_list = determine_side_robust(
            sv_point, sv_heading, road_gdf_proj, road_sindex,
            candidates_gdf, block_id_col, verbose=False
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
