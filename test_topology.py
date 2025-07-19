#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
拓扑关系功能测试脚本
"""

import os
import pandas as pd
import sys

def test_topology_functions():
    """测试拓扑关系功能"""
    
    # 测试参数
    gdb_path = r'D:/LifeOS/01Projects/GraduateThesis/250510 Test/卫星图测试/卫星图测试.gdb'
    landuse_layer = 'landuse'
    landuse_id_col = 'GH_ZXC_2_I'
    road_layer = 'road_街景测试范围_0712'
    road_id_col = 'OBJECTID'
    csv_path = 'example.csv'
    output_dir = 'test_output'
    
    print("开始测试拓扑关系功能...")
    print(f"当前工作目录: {os.getcwd()}")
    print(f"CSV文件路径: {csv_path}")
    print(f"CSV文件是否存在: {os.path.exists(csv_path)}")
    
    try:
        # 检查CSV文件
        if not os.path.exists(csv_path):
            print(f"错误: CSV文件不存在: {csv_path}")
            return
        
        # 读取CSV数据
        print("1. 读取CSV数据...")
        sv_points = pd.read_csv(csv_path)
        print(f"   - CSV数据: {len(sv_points)} 行")
        print(f"   - 列名: {list(sv_points.columns)}")
        
        # 转换为列表格式
        if 'id' in sv_points.columns and 'X' in sv_points.columns and 'Y' in sv_points.columns:
            sv_points_list = sv_points[['id', 'X', 'Y']].values.tolist()
        elif 'id' in sv_points.columns and 'x' in sv_points.columns and 'y' in sv_points.columns:
            sv_points_list = sv_points[['id', 'x', 'y']].values.tolist()
        else:
            sv_points_list = sv_points.values.tolist()
        
        print(f"   - 转换后数据: {len(sv_points_list)} 个点")
        print(f"   - 前3个点: {sv_points_list[:3]}")
        
        # 尝试导入模块
        print("2. 导入模块...")
        try:
            from topology_utils import (
                read_road_gdb, 
                build_streetview_road_mapping,
                build_landuse_topology,
                generate_traversal_config
            )
            from landuse_utils import read_landuse_gdb
            from streetview_utils import read_streetview_points
            print("   - 模块导入成功")
        except ImportError as e:
            print(f"   - 模块导入失败: {e}")
            return
        
        # 检查GDB文件
        print("3. 检查GDB文件...")
        if not os.path.exists(gdb_path):
            print(f"   - 警告: GDB文件不存在: {gdb_path}")
            print("   - 跳过GDB相关测试")
            return
        
        # 读取数据
        print("4. 读取GDB数据...")
        try:
            landuse_gdf = read_landuse_gdb(gdb_path, landuse_layer, landuse_id_col)
            road_gdf = read_road_gdb(gdb_path, road_layer, road_id_col)
            print(f"   - 地块数据: {len(landuse_gdf)} 个")
            print(f"   - 道路数据: {len(road_gdf)} 条")
        except Exception as e:
            print(f"   - GDB读取失败: {e}")
            return
        
        # 建立街景点-道路映射
        print("5. 建立街景点-道路映射...")
        try:
            streetview_road_mapping = build_streetview_road_mapping(sv_points_list, road_gdf, road_id_col)
            print(f"   - 映射关系: {len(streetview_road_mapping)} 个")
        except Exception as e:
            print(f"   - 映射建立失败: {e}")
            return
        
        # 测试单个地块拓扑
        print("6. 测试单个地块拓扑...")
        if len(landuse_gdf) > 0:
            try:
                test_landuse_id = 3904.0  # 使用与街景点关联的地块
                topology = build_landuse_topology(test_landuse_id, streetview_road_mapping, landuse_gdf, landuse_id_col)
                print(f"   - 测试地块ID: {test_landuse_id}")
                print(f"   - 关联道路数: {len(topology['road_sequence'])}")
                
                for road_info in topology['road_sequence']:
                    print(f"     - 道路 {road_info['road_id']}: {len(road_info['streetview_points'])} 个街景点")
            except Exception as e:
                print(f"   - 拓扑构建失败: {e}")
        
        # 生成遍历配置
        print("7. 生成遍历配置...")
        os.makedirs(output_dir, exist_ok=True)
        
        # 测试与街景点关联的地块
        # 根据调试结果，使用地块3904.0（与街景点1.0最近）
        test_landuse_ids = [3904.0, 3767.0, 3511.0]
        topology_data = []
        
        for landuse_id in test_landuse_ids:
            try:
                topology = build_landuse_topology(landuse_id, streetview_road_mapping, landuse_gdf, landuse_id_col)
                if topology['road_sequence']:
                    topology_data.append(topology)
            except Exception as e:
                print(f"   警告: 地块 {landuse_id} 拓扑构建失败: {e}")
        
        if topology_data:
            try:
                config_df = generate_traversal_config(topology_data, output_dir)
                print(f"   - 生成配置表: {len(config_df)} 条记录")
                print(f"   - 保存位置: {output_dir}/landuse_traversal_config.csv")
                
                # 显示前几条记录
                print("   - 配置表示例:")
                print(config_df.head().to_string())
            except Exception as e:
                print(f"   - 配置生成失败: {e}")
        else:
            print("   警告: 没有成功构建拓扑关系")
        
        print("测试完成!")
        
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_topology_functions() 