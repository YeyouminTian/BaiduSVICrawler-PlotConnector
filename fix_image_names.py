#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复图像文件名，使其符合正确的命名规则
确保左右图对应正确的地块
"""

import os
import pandas as pd
import shutil
import re

def fix_image_names():
    """修复图像文件名"""
    print("=== 修复图像文件名 ===")
    
    # 读取配置文件
    config_csv = 'output/landuse_traversal_config.csv'
    if not os.path.exists(config_csv):
        print(f"配置文件不存在: {config_csv}")
        return
    
    config_df = pd.read_csv(config_csv)
    print(f"读取配置表，共 {len(config_df)} 条记录")
    
    # 读取原始关联表
    mapping_csv = 'output/streetview_landuse_mapping.csv'
    if not os.path.exists(mapping_csv):
        print(f"关联表不存在: {mapping_csv}")
        return
    
    mapping_df = pd.read_csv(mapping_csv)
    print(f"读取关联表，共 {len(mapping_df)} 条记录")
    
    # 按街景点ID分组，确保左右图对应正确的地块
    streetview_groups = {}
    for _, row in config_df.iterrows():
        streetview_id = str(row['streetview_id'])  # 转换为字符串
        landuse_id = row['landuse_id']
        road_id = row['road_id']
        filename = row['filename']
        
        if streetview_id not in streetview_groups:
            streetview_groups[streetview_id] = {}
        
        # 根据文件名中的L/R判断左右
        if '_L.jpg' in filename:
            streetview_groups[streetview_id]['left'] = {
                'landuse_id': landuse_id,
                'road_id': road_id,
                'filename': filename
            }
        elif '_R.jpg' in filename:
            streetview_groups[streetview_id]['right'] = {
                'landuse_id': landuse_id,
                'road_id': road_id,
                'filename': filename
            }
    
    # 检查当前文件
    img_dir = 'output/images'
    current_files = os.listdir(img_dir)
    current_file_map = {}
    
    for filename in current_files:
        if filename.endswith('.jpg'):
            # 解析当前文件名格式：P{landuse_id}_R{road_id}_S{streetview_id}_{L/R}.jpg
            match = re.match(r'P([^_]+)_R([^_]+)_S([^_]+)_([LR])\.jpg', filename)
            if match:
                current_landuse_id = match.group(1)
                current_road_id = match.group(2)
                current_streetview_id = match.group(3)  # 已经是字符串
                current_side = match.group(4)
                
                if current_streetview_id not in current_file_map:
                    current_file_map[current_streetview_id] = {}
                
                current_file_map[current_streetview_id][current_side] = filename
    
    print(f"发现当前文件，共 {len(current_file_map)} 个街景点")
    
    # 创建重命名映射
    rename_mapping = {}
    
    for streetview_id, sides in streetview_groups.items():
        if streetview_id in current_file_map:
            current_sides = current_file_map[streetview_id]
            
            # 左图重命名
            if 'left' in sides and 'L' in current_sides:
                old_filename_L = current_sides['L']
                new_filename_L = sides['left']['filename']
                if old_filename_L != new_filename_L:
                    rename_mapping[old_filename_L] = new_filename_L
                    print(f"左图需要重命名: {old_filename_L} -> {new_filename_L}")
            
            # 右图重命名
            if 'right' in sides and 'R' in current_sides:
                old_filename_R = current_sides['R']
                new_filename_R = sides['right']['filename']
                if old_filename_R != new_filename_R:
                    rename_mapping[old_filename_R] = new_filename_R
                    print(f"右图需要重命名: {old_filename_R} -> {new_filename_R}")
    
    print(f"创建重命名映射，共 {len(rename_mapping)} 个文件需要重命名")
    
    if len(rename_mapping) == 0:
        print("没有文件需要重命名")
        return
    
    # 执行重命名
    renamed_count = 0
    failed_count = 0
    
    for old_name, new_name in rename_mapping.items():
        old_path = os.path.join(img_dir, old_name)
        new_path = os.path.join(img_dir, new_name)
        
        if os.path.exists(old_path):
            try:
                # 如果新文件名已存在，先删除
                if os.path.exists(new_path):
                    os.remove(new_path)
                    print(f"删除已存在的文件: {new_name}")
                
                # 重命名文件
                os.rename(old_path, new_path)
                renamed_count += 1
                print(f"重命名成功: {old_name} -> {new_name}")
            except Exception as e:
                print(f"重命名失败 {old_name} -> {new_name}: {e}")
                failed_count += 1
        else:
            print(f"文件不存在: {old_path}")
            failed_count += 1
    
    print(f"重命名完成:")
    print(f"- 成功: {renamed_count} 个文件")
    print(f"- 失败: {failed_count} 个文件")
    
    # 验证重命名结果
    print("\n=== 验证重命名结果 ===")
    for streetview_id, sides in streetview_groups.items():
        print(f"街景点 {streetview_id}:")
        if 'left' in sides:
            left_file = sides['left']['filename']
            left_landuse = sides['left']['landuse_id']
            left_path = os.path.join(img_dir, left_file)
            if os.path.exists(left_path):
                print(f"  ✓ 左图: {left_file} (地块: {left_landuse})")
            else:
                print(f"  ✗ 左图: {left_file} (地块: {left_landuse}) - 文件不存在")
        
        if 'right' in sides:
            right_file = sides['right']['filename']
            right_landuse = sides['right']['landuse_id']
            right_path = os.path.join(img_dir, right_file)
            if os.path.exists(right_path):
                print(f"  ✓ 右图: {right_file} (地块: {right_landuse})")
            else:
                print(f"  ✗ 右图: {right_file} (地块: {right_landuse}) - 文件不存在")
        print()

if __name__ == '__main__':
    fix_image_names() 