import math
import numpy as np
from topology_utils import calculate_angle, sort_roads_by_angle, sort_streetview_in_road

def test_traversal_direction():
    """测试不同的遍历方向"""
    
    print("=== 遍历方向测试 ===\n")
    
    # 模拟地块质心
    landuse_centroid = (121.505, 31.282)
    
    # 模拟多条道路的质心
    road_centroids = {
        634: (121.505, 31.283),  # 北边
        635: (121.506, 31.282),  # 东边  
        636: (121.505, 31.281),  # 南边
        637: (121.504, 31.282),  # 西边
    }
    
    print("=== 顺时针遍历 ===")
    clockwise_roads = sort_roads_by_angle(landuse_centroid, road_centroids, clockwise=True)
    for i, road_id in enumerate(clockwise_roads, 1):
        centroid = road_centroids[road_id]
        angle_rad = calculate_angle(landuse_centroid, centroid)
        angle_deg = math.degrees(angle_rad)
        print(f"第{i}条道路: 道路{road_id} (角度: {angle_deg:.1f}°)")
    
    print("\n=== 逆时针遍历 ===")
    counterclockwise_roads = sort_roads_by_angle(landuse_centroid, road_centroids, clockwise=False)
    for i, road_id in enumerate(counterclockwise_roads, 1):
        centroid = road_centroids[road_id]
        angle_rad = calculate_angle(landuse_centroid, centroid)
        angle_deg = math.degrees(angle_rad)
        print(f"第{i}条道路: 道路{road_id} (角度: {angle_deg:.1f}°)")
    
    print("\n=== 修改遍历方向的方法 ===")
    print("方法1: 修改 main.py 中的参数")
    print("   main(..., traversal_direction='counterclockwise')")
    print()
    print("方法2: 直接修改 topology_utils.py")
    print("   第120行: clockwise=True → clockwise=False")
    print("   第131行: clockwise=True → clockwise=False")
    print()
    print("方法3: 使用配置参数")
    print("   traversal_direction='clockwise'    # 顺时针")
    print("   traversal_direction='counterclockwise'  # 逆时针")

if __name__ == '__main__':
    test_traversal_direction() 