"""
街景数据处理模块
"""
import time
import pandas as pd
import requests
import json
from PIL import Image
from io import BytesIO


def read_streetview_points(csv_path):
    """
    读取街景点CSV文件

    Args:
        csv_path: CSV文件路径

    Returns:
        列表，每个元素为 [id, x, y] 或 [x, y]
    """
    df = pd.read_csv(csv_path)

    points = []
    id_col = None
    x_col = None
    y_col = None

    # 自动识别列名
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
        # 如果没有识别到列名，按顺序读取
        if df.shape[1] >= 3:
            points = df.iloc[:, :3].values.tolist()
        elif df.shape[1] == 2:
            points = df.iloc[:, :2].values.tolist()

    return points


def wgs84_to_bd09mc(x, y, ak):
    """
    WGS84坐标转百度墨卡托坐标

    Args:
        x: 经度
        y: 纬度
        ak: 百度API密钥

    Returns:
        (bd_x, bd_y) 或 (None, None)
    """
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
    """
    获取街景元数据

    Args:
        x_bd: 百度墨卡托X坐标
        y_bd: 百度墨卡托Y坐标

    Returns:
        (sid, metadata_dict) 或 (None, None)
    """
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
    """
    下载全景图

    Args:
        sid: 街景ID
        zoom: 缩放级别（1-4）
        retries: 重试次数

    Returns:
        PIL.Image 或 None
    """
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
