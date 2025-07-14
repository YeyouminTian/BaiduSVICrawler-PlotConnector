import pandas as pd
import requests
import json
from PIL import Image
from io import BytesIO

def read_streetview_points(csv_path):
    df = pd.read_csv(csv_path)
    if 'id' in df.columns and 'X' in df.columns and 'Y' in df.columns:
        coords = df[['id', 'X', 'Y']].values.tolist()
    elif 'id' in df.columns and 'x' in df.columns and 'y' in df.columns:
        coords = df[['id', 'x', 'y']].values.tolist()
    elif 'X' in df.columns and 'Y' in df.columns:
        coords = df[['X', 'Y']].values.tolist()
    elif 'x' in df.columns and 'y' in df.columns:
        coords = df[['x', 'y']].values.tolist()
    else:
        coords = df.values.tolist()
    return coords

def wgs84_to_bd09mc(x, y, ak):
    url = f"http://api.map.baidu.com/geoconv/v1/?coords={x},{y}&from=1&to=6&ak={ak}"
    resp = requests.get(url)
    data = json.loads(resp.text)
    if data.get('status') == 0:
        return data['result'][0]['x'], data['result'][0]['y']
    else:
        raise RuntimeError(f"坐标转换失败: {data}")

def get_streetview_metadata(x_bd, y_bd):
    url = f"https://mapsv0.bdimg.com/?qt=qsdata&x={x_bd}&y={y_bd}"
    resp = requests.get(url)
    data = json.loads(resp.text)
    if 'content' not in data or not data['content']:
        return None
    sid = data['content'].get('id')
    if not sid:
        return None
    meta_url = f"https://mapsv0.bdimg.com/?qt=sdata&sid={sid}"
    meta_resp = requests.get(meta_url)
    meta_data = json.loads(meta_resp.text)
    if 'content' in meta_data:
        content = meta_data['content']
        if isinstance(content, list) and content:
            content = content[0]
        return sid, content
    return sid, None

def download_panorama_image(sid, zoom=3):
    if zoom == 2:
        xrange, yrange = 1, 2
    elif zoom == 3:
        xrange, yrange = 2, 4
    elif zoom == 1:
        xrange, yrange = 1, 1
    elif zoom == 4:
        xrange, yrange = 4, 8
    else:
        xrange, yrange = 2, 4
    img_list = []
    for x in range(xrange):
        for y in range(yrange):
            url = f"https://mapsv1.bdimg.com/?qt=pdata&sid={sid}&pos={x}_{y}&z={zoom}&from=PC"
            resp = requests.get(url)
            if resp.status_code == 200:
                img = Image.open(BytesIO(resp.content))
                img_list.append(img)
            else:
                return None
    w, h = img_list[0].size
    pano = Image.new("RGB", (w * yrange, h * xrange))
    for i, img in enumerate(img_list):
        row = i // yrange
        col = i % yrange
        pano.paste(img, (col * w, row * h))
    return pano 