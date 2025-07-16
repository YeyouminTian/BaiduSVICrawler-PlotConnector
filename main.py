import os
import pandas as pd
from shapely.geometry import Point
import cv2
import numpy as np
from tqdm import tqdm 

from landuse_utils import read_landuse_gdb
from streetview_utils import read_streetview_points, wgs84_to_bd09mc, get_streetview_metadata, download_panorama_image
from image_utils import equirectangular_to_perspective
from spatial_analysis import judge_left_right

def main(
    landuse_gdb_path,
    landuse_layer='landuse',
    landuse_id_col='OBJECTID',
    streetview_csv_path='resources/example.csv',
    baidu_ak='',
    output_dir='output',
    zoom=3,
    save_front_back=False,
    save_every=50 
):
    os.makedirs(output_dir, exist_ok=True)
    img_dir = os.path.join(output_dir, 'images')
    os.makedirs(img_dir, exist_ok=True)
    mapping = []
    # 断点续存：读取已处理的id或(x, y)
    processed_keys = set()
    mapping_csv = os.path.join(output_dir, 'streetview_landuse_mapping.csv')
    if os.path.exists(mapping_csv):
        try:
            old_df = pd.read_csv(mapping_csv)
            if 'id' in old_df.columns:
                processed_keys = set(old_df['id'].astype(str))
            else:
                processed_keys = set(zip(old_df['x'], old_df['y']))
            # 断点续存时，先加载已有内容
            mapping = old_df.to_dict('records')
            print(f"[断点续存] 已检测到 {len(processed_keys)} 个已处理点，将跳过这些点。")
        except Exception as e:
            print(f"[断点续存] 读取已有 mapping 文件失败：{e}")
    landuse_gdf = read_landuse_gdb(landuse_gdb_path, landuse_layer, landuse_id_col)
    sv_points = read_streetview_points(streetview_csv_path)
    # 过滤未处理点
    filtered_points = []
    for pt_info in sv_points:
        if len(pt_info) == 3:
            id_val, x, y = pt_info
            key = str(id_val)
        else:
            id_val = None
            x, y = pt_info
            key = (x, y)
        if key not in processed_keys:
            filtered_points.append(pt_info)
    print(f"共 {len(sv_points)} 个点，未处理 {len(filtered_points)} 个点。")
    for idx, pt_info in enumerate(tqdm(filtered_points, desc='Processing streetview points')):
        if len(pt_info) == 3:
            id_val, x, y = pt_info
        else:
            id_val = None
            x, y = pt_info
        try:
            x_bd, y_bd = wgs84_to_bd09mc(x, y, baidu_ak)
            sid, meta = get_streetview_metadata(x_bd, y_bd)
            if not sid or not meta:
                print(f"No streetview at {x},{y}")
                continue
            heading = float(meta.get('Heading', 0))
            movedir = float(meta.get('MoveDir', heading))
            capture_time = meta.get('Time', '')
            pano_img = download_panorama_image(sid, zoom=zoom)
            if pano_img is None:
                print(f"Failed to download panorama for {sid}")
                continue
            pano_np = cv2.cvtColor(np.array(pano_img), cv2.COLOR_RGB2BGR)
            out_size = (1024, 683)
            fov_h = 120
            fov_v = 90
            left_view = equirectangular_to_perspective(pano_np, fov_h, fov_v, 0, 0, out_size)
            right_view = equirectangular_to_perspective(pano_np, fov_h, fov_v, 180, 0, out_size)
            base_name = str(id_val) if id_val is not None else str(sid)
            fname_L = f"{base_name}_L.jpg"
            fname_R = f"{base_name}_R.jpg"
            cv2.imwrite(os.path.join(img_dir, fname_L), left_view)
            cv2.imwrite(os.path.join(img_dir, fname_R), right_view)
            if save_front_back:
                front_view = equirectangular_to_perspective(pano_np, fov_h, fov_v, 90, 0, out_size)
                back_view = equirectangular_to_perspective(pano_np, fov_h, fov_v, 270, 0, out_size)
                fname_F = f"{base_name}_front.jpg"
                fname_B = f"{base_name}_back.jpg"
                cv2.imwrite(os.path.join(img_dir, fname_F), front_view)
                cv2.imwrite(os.path.join(img_dir, fname_B), back_view)
            pt = Point(x, y)
            left_min_dist = float('inf')
            right_min_dist = float('inf')
            left_row = None
            right_row = None
            for _, row in landuse_gdf.iterrows():
                if 'GH_LAYOUT' in row and row['GH_LAYOUT'] == 'S1':
                    continue
                centroid = (row['centroid_x'], row['centroid_y'])
                side = judge_left_right((x, y), movedir, centroid)
                dist = pt.distance(row['geometry'])
                if side == 'L' and dist < left_min_dist:
                    left_min_dist = dist
                    left_row = row
                elif side == 'R' and dist < right_min_dist:
                    right_min_dist = dist
                    right_row = row
            if left_row is not None:
                mapping.append({
                    'streetview_id': sid,
                    'filename': fname_L,
                    'landuse_id': left_row[landuse_id_col],
                    'side': 'L',
                    'heading': heading,
                    'capture_time': capture_time,
                    'x': x,
                    'y': y,
                    'id': id_val
                })
            if right_row is not None:
                mapping.append({
                    'streetview_id': sid,
                    'filename': fname_R,
                    'landuse_id': right_row[landuse_id_col],
                    'side': 'R',
                    'heading': heading,
                    'capture_time': capture_time,
                    'x': x,
                    'y': y,
                    'id': id_val
                })
            print(f"Processed streetview {sid} at {x},{y}")
        except Exception as e:
            print(f"Error processing point {x},{y}: {e}")
        # 定期保存
        if ((idx + 1) % save_every == 0) or (idx == len(filtered_points) - 1):
            df = pd.DataFrame(mapping)
            df.to_csv(os.path.join(output_dir, 'streetview_landuse_mapping.csv'), index=False, encoding='utf-8')
            df.to_json(os.path.join(output_dir, 'streetview_landuse_mapping.json'), orient='records', force_ascii=False)
            print(f"[进度保存] 已保存 {len(mapping)} 条记录。")
    print(f"Done! Mapping table saved to {output_dir}")

if __name__ == '__main__':
    main(
        landuse_gdb_path=r'矢量数据路径',
        landuse_layer='landuse',#图层名称
        landuse_id_col='landuse_id_col',#landuse_id_col为矢量数据中用于唯一标识每个地块的列名
        streetview_csv_path='streetview_csv_path',#街景点csv文件路径
        baidu_ak='百度ak',#百度ak
        output_dir='output_dir',#输出目录
        zoom=3,#街景图缩放级别
        #save_front_back=True  # 如需保存前后方视图，取消注释
        save_every=50  # 新增参数：每多少个点保存一次，断点续存时，每多少个点保存一次
    ) 