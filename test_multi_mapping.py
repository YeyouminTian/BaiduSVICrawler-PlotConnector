import pandas as pd
import os

def test_multi_mapping_simple():
    """简化的多地块映射测试"""
    output_dir = 'output'
    
    # 读取现有数据
    mapping_csv = os.path.join(output_dir, 'streetview_landuse_mapping.csv')
    if not os.path.exists(mapping_csv):
        print("streetview_landuse_mapping.csv 不存在")
        return
    
    streetview_landuse_mapping = pd.read_csv(mapping_csv)
    print(f"读取到 {len(streetview_landuse_mapping)} 条街景-地块映射记录")
    
    # 分析数据
    print("\n数据分析:")
    print(f"唯一的街景点ID数量: {len(streetview_landuse_mapping['streetview_id'].unique())}")
    print(f"唯一的地块ID数量: {len(streetview_landuse_mapping['landuse_id'].unique())}")
    print(f"地块ID列表: {sorted(streetview_landuse_mapping['landuse_id'].unique())}")
    
    # 按原始ID分组，检查每个街景点的左右地块
    print("\n每个街景点的左右地块映射:")
    for original_id in sorted(streetview_landuse_mapping['id'].unique()):
        if pd.isna(original_id):
            continue
            
        records = streetview_landuse_mapping[streetview_landuse_mapping['id'] == original_id]
        left_landuse = records[records['side'] == 'L']['landuse_id'].iloc[0] if len(records[records['side'] == 'L']) > 0 else None
        right_landuse = records[records['side'] == 'R']['landuse_id'].iloc[0] if len(records[records['side'] == 'R']) > 0 else None
        
        print(f"街景点 {original_id}: 左地块={left_landuse}, 右地块={right_landuse}")
    
    # 手动创建多地块映射数据
    multi_mapping_data = []
    
    # 按原始ID排序，确保序列号连续
    sorted_original_ids = sorted([id for id in streetview_landuse_mapping['id'].unique() if not pd.isna(id)])
    
    for idx, original_id in enumerate(sorted_original_ids, 1):  # 从1开始编号
        records = streetview_landuse_mapping[streetview_landuse_mapping['id'] == original_id]
        landuse_relations = []
        
        for _, record in records.iterrows():
            landuse_id = record['landuse_id']
            side = record['side']
            
            # 生成文件名
            filename_L = f"P{landuse_id}_R634.0_S{original_id}_L.jpg"
            filename_R = f"P{landuse_id}_R634.0_S{original_id}_R.jpg"
            
            landuse_relations.append({
                'landuse_id': landuse_id,
                'road_id': 634.0,  # 假设所有街景点都在道路634上
                'road_sequence': 1,  # 假设都是第一条道路
                'point_sequence': idx,  # 使用连续的序列号
                'filename_L': filename_L,
                'filename_R': filename_R
            })
        
        if landuse_relations:
            multi_mapping_data.append({
                'streetview_id': str(original_id),
                'landuse_relations': landuse_relations
            })
    
    print(f"\n生成了 {len(multi_mapping_data)} 条多地块映射记录")
    
    # 生成CSV文件
    mapping_data = []
    for sv_mapping in multi_mapping_data:
        sv_id = sv_mapping['streetview_id']
        for relation in sv_mapping['landuse_relations']:
            mapping_data.append({
                'streetview_id': sv_id,
                'landuse_id': relation['landuse_id'],
                'road_id': relation['road_id'],
                'road_sequence': relation['road_sequence'],
                'point_sequence': relation['point_sequence'],
                'filename_L': relation['filename_L'],
                'filename_R': relation['filename_R']
            })
    
    mapping_df = pd.DataFrame(mapping_data)
    output_file = os.path.join(output_dir, 'streetview_multi_landuse_mapping.csv')
    mapping_df.to_csv(output_file, index=False, encoding='utf-8')
    
    print(f"成功生成多地块映射文件: {output_file}")
    print(f"共 {len(mapping_df)} 条记录")
    
    # 显示列说明
    print("\n=== 列说明 ===")
    print("streetview_id: 街景点ID（原始ID，如3655.0）")
    print("landuse_id: 地块ID（如3365.0, 3368.0）")
    print("road_id: 道路ID（如634.0）")
    print("road_sequence: 道路序列号（在该地块中的道路顺序）")
    print("point_sequence: 街景点序列号（在该道路中的街景点顺序）")
    print("filename_L: 左视图图像文件名（格式：P{地块ID}_R{道路ID}_S{街景点ID}_L.jpg）")
    print("filename_R: 右视图图像文件名（格式：P{地块ID}_R{道路ID}_S{街景点ID}_R.jpg）")
    
    # 显示前几条记录
    if len(mapping_df) > 0:
        print("\n前10条记录:")
        print(mapping_df.head(10))

if __name__ == '__main__':
    test_multi_mapping_simple() 