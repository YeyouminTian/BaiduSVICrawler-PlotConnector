import math
import numpy as np
from topology_utils import calculate_angle, sort_roads_by_angle

def test_road_sequencing():
    """测试道路顺序确定逻辑"""
    
    # 模拟地块质心
    landuse_centroid = (121.505, 31.282)
    
    # 模拟多条道路的质心（围绕地块的不同位置）
    road_centroids = {
        634: (121.505, 31.283),  # 北边
        635: (121.506, 31.282),  # 东边  
        636: (121.505, 31.281),  # 南边
        637: (121.504, 31.282),  # 西边
        638: (121.5055, 31.2825),  # 东北
        639: (121.5045, 31.2815),  # 西南
    }
    
    print("=== 道路顺序确定示例 ===")
    print(f"地块质心: {landuse_centroid}")
    print("\n各道路质心:")
    for road_id, centroid in road_centroids.items():
        angle_rad = calculate_angle(landuse_centroid, centroid)
        angle_deg = math.degrees(angle_rad)
        print(f"道路{road_id}: {centroid} (角度: {angle_deg:.1f}°)")
    
    # 测试顺时针排序
    print("\n=== 顺时针排序 ===")
    clockwise_sequence = sort_roads_by_angle(landuse_centroid, road_centroids, clockwise=True)
    for i, road_id in enumerate(clockwise_sequence, 1):
        centroid = road_centroids[road_id]
        angle_rad = calculate_angle(landuse_centroid, centroid)
        angle_deg = math.degrees(angle_rad)
        print(f"第{i}条道路: 道路{road_id} (角度: {angle_deg:.1f}°)")
    
    # 测试逆时针排序
    print("\n=== 逆时针排序 ===")
    counterclockwise_sequence = sort_roads_by_angle(landuse_centroid, road_centroids, clockwise=False)
    for i, road_id in enumerate(counterclockwise_sequence, 1):
        centroid = road_centroids[road_id]
        angle_rad = calculate_angle(landuse_centroid, centroid)
        angle_deg = math.degrees(angle_rad)
        print(f"第{i}条道路: 道路{road_id} (角度: {angle_deg:.1f}°)")
    
    print("\n=== 说明 ===")
    print("1. 以地块质心为原点，计算各道路质心的角度")
    print("2. 角度范围: -180° 到 +180°")
    print("3. 顺时针排序: 角度从大到小")
    print("4. 逆时针排序: 角度从小到大")
    print("5. 这样实现了类似人类绕地块行走的遍历效果")

if __name__ == '__main__':
    test_road_sequencing() 