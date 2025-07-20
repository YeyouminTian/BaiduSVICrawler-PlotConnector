import math
import numpy as np
from topology_utils import calculate_angle, sort_roads_by_angle, sort_streetview_in_road

def test_consistent_ordering():
    """测试道路和街景点的一致性排序"""
    
    print("=== 一致性排序示例 ===\n")
    
    # 模拟地块质心
    landuse_centroid = (121.505, 31.282)
    print(f"地块质心: {landuse_centroid}")
    
    # 模拟多条道路的质心
    road_centroids = {
        634: (121.505, 31.283),  # 北边
        635: (121.506, 31.282),  # 东边  
        636: (121.505, 31.281),  # 南边
    }
    
    print("\n=== 道路排序 (顺时针) ===")
    clockwise_roads = sort_roads_by_angle(landuse_centroid, road_centroids, clockwise=True)
    for i, road_id in enumerate(clockwise_roads, 1):
        centroid = road_centroids[road_id]
        angle_rad = calculate_angle(landuse_centroid, centroid)
        angle_deg = math.degrees(angle_rad)
        print(f"第{i}条道路: 道路{road_id} (角度: {angle_deg:.1f}°)")
    
    # 模拟每条道路上的街景点
    road_streetviews = {
        634: [  # 北边道路上的街景点
            {'streetview_id': '3655', 'x': 121.505, 'y': 31.2835},
            {'streetview_id': '3656', 'x': 121.505, 'y': 31.284},
            {'streetview_id': '3657', 'x': 121.505, 'y': 31.2845},
        ],
        635: [  # 东边道路上的街景点
            {'streetview_id': '3658', 'x': 121.5065, 'y': 31.282},
            {'streetview_id': '3659', 'x': 121.507, 'y': 31.282},
            {'streetview_id': '3660', 'x': 121.5075, 'y': 31.282},
        ],
        636: [  # 南边道路上的街景点
            {'streetview_id': '3661', 'x': 121.505, 'y': 31.2805},
            {'streetview_id': '3662', 'x': 121.505, 'y': 31.280},
            {'streetview_id': '3663', 'x': 121.505, 'y': 31.2795},
        ]
    }
    
    print("\n=== 街景点排序 (每条道路内顺时针) ===")
    for road_id in clockwise_roads:
        print(f"\n道路{road_id}上的街景点:")
        streetviews = road_streetviews[road_id]
        
        # 计算道路质心
        road_centroid_x = np.mean([pt['x'] for pt in streetviews])
        road_centroid_y = np.mean([pt['y'] for pt in streetviews])
        road_centroid = (road_centroid_x, road_centroid_y)
        
        print(f"  道路质心: {road_centroid}")
        
        # 按顺时针排序街景点
        sorted_streetviews = sort_streetview_in_road(road_id, streetviews, clockwise=True)
        
        for i, pt in enumerate(sorted_streetviews, 1):
            angle_rad = calculate_angle(road_centroid, (pt['x'], pt['y']))
            angle_deg = math.degrees(angle_rad)
            print(f"  第{i}个街景点: {pt['streetview_id']} (角度: {angle_deg:.1f}°)")
    
    print("\n=== 完整遍历路径 ===")
    print("遍历顺序: 地块 → 道路 → 街景点 (全部顺时针)")
    sequence = 1
    for road_id in clockwise_roads:
        sorted_streetviews = sort_streetview_in_road(road_id, road_streetviews[road_id], clockwise=True)
        for pt in sorted_streetviews:
            print(f"{sequence:2d}. 道路{road_id} → 街景点{pt['streetview_id']}")
            sequence += 1
    
    print("\n=== 说明 ===")
    print("1. 道路排序: 以地块质心为原点，按顺时针角度排序")
    print("2. 街景点排序: 以道路质心为原点，按顺时针角度排序")
    print("3. 整体效果: 实现了一致的顺时针遍历体验")
    print("4. 遍历路径: 模拟人类绕地块行走，在每条道路上按顺序前进")

if __name__ == '__main__':
    test_consistent_ordering() 