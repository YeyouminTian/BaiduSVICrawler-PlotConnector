import numpy as np
from math import radians, cos, sin
from shapely.geometry import Point
from shapely.ops import nearest_points

def judge_left_right(streetview_pt, road_dir, landuse_centroid):
    """
    判断地块相对于街景点的左右位置（使用叉乘）
    
    Args:
        streetview_pt: 街景点坐标 (x, y)
        road_dir: 道路方向角度（度，0=正北，90=正东，180=正南，270=正西）
        landuse_centroid: 地块质心坐标 (x, y)
    
    Returns:
        'L' 或 'R': 地块相对于街景点的左右位置
    """
    dx = landuse_centroid[0] - streetview_pt[0]
    dy = landuse_centroid[1] - streetview_pt[1]
    
    # 计算道路方向向量（单位向量）
    # heading=0表示正北方向，所以需要调整角度
    theta = radians(90 - road_dir)  # 转换为数学坐标系
    road_vec = np.array([cos(theta), sin(theta)])
    
    # 计算地块到街景点的向量
    landuse_vec = np.array([dx, dy])
    
    # 计算叉积：landuse_vec × road_vec
    # 叉积的正负表示landuse_vec相对于road_vec的位置
    cross = landuse_vec[0] * road_vec[1] - landuse_vec[1] * road_vec[0]
    
    # 如果叉积为正，地块在道路方向的左侧
    # 如果叉积为负，地块在道路方向的右侧
    return 'L' if cross < 0 else 'R'

def judge_left_right_by_perpendicular(streetview_pt, road_dir, landuse_geometry):
    """
    使用街景点到最近街坊边界的垂线方向进行左右判断
    
    Args:
        streetview_pt: 街景点坐标 (x, y)
        road_dir: 道路方向角度（度）
        landuse_geometry: 街坊几何对象
    
    Returns:
        'L' 或 'R': 街坊相对于街景点的左右位置
    """
    # 创建街景点Point对象
    sv_point = Point(streetview_pt)
    
    # 找到街景点到街坊边界的最短距离点
    nearest_pt_on_boundary, _ = nearest_points(sv_point, landuse_geometry)
    
    # 计算垂线方向向量（从街景点指向边界最近点）
    perpendicular_dx = nearest_pt_on_boundary.x - streetview_pt[0]
    perpendicular_dy = nearest_pt_on_boundary.y - streetview_pt[1]
    
    # 计算道路方向向量
    theta = radians(road_dir)
    road_vec = np.array([cos(theta), sin(theta)])
    
    # 计算垂线向量
    perpendicular_vec = np.array([perpendicular_dx, perpendicular_dy])
    
    # 计算叉积判断左右
    # 如果垂线向量在道路方向向量的左侧，则街坊在左侧
    cross = road_vec[0] * perpendicular_vec[1] - road_vec[1] * perpendicular_vec[0]
    
    return 'L' if cross > 0 else 'R'

def judge_left_right_by_centroid_perpendicular(streetview_pt, road_dir, landuse_centroid, landuse_geometry):
    """
    结合质心和边界垂线的左右判断方法
    
    Args:
        streetview_pt: 街景点坐标 (x, y)
        road_dir: 道路方向角度（度）
        landuse_centroid: 街坊质心坐标 (x, y)
        landuse_geometry: 街坊几何对象
    
    Returns:
        'L' 或 'R': 街坊相对于街景点的左右位置
    """
    # 方法1: 使用质心方向
    dx_centroid = landuse_centroid[0] - streetview_pt[0]
    dy_centroid = landuse_centroid[1] - streetview_pt[1]
    
    # 方法2: 使用边界垂线方向
    sv_point = Point(streetview_pt)
    nearest_pt_on_boundary, _ = nearest_points(sv_point, landuse_geometry)
    dx_perpendicular = nearest_pt_on_boundary.x - streetview_pt[0]
    dy_perpendicular = nearest_pt_on_boundary.y - streetview_pt[1]
    
    # 计算道路方向向量
    theta = radians(road_dir)
    road_vec = np.array([cos(theta), sin(theta)])
    
    # 计算两个方向的叉积
    centroid_vec = np.array([dx_centroid, dy_centroid])
    perpendicular_vec = np.array([dx_perpendicular, dy_perpendicular])
    
    cross_centroid = road_vec[0] * centroid_vec[1] - road_vec[1] * centroid_vec[0]
    cross_perpendicular = road_vec[0] * perpendicular_vec[1] - road_vec[1] * perpendicular_vec[0]
    
    # 如果两个方法结果一致，返回结果
    if (cross_centroid > 0 and cross_perpendicular > 0) or (cross_centroid < 0 and cross_perpendicular < 0):
        return 'L' if cross_centroid > 0 else 'R'
    else:
        # 如果不一致，优先使用垂线方向（更准确）
        return 'L' if cross_perpendicular > 0 else 'R' 