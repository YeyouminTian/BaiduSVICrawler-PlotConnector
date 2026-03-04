"""
地块数据读取与处理模块
"""
import geopandas as gpd
from geometry_utils import get_utm_crs


def read_landuse_gdb(gdb_path, layer_name='landuse', id_col='OBJECTID'):
    """
    读取地块数据（GDB格式）

    Args:
        gdb_path: GDB文件路径
        layer_name: 图层名称
        id_col: ID字段名

    Returns:
        GeoDataFrame，包含地块几何、质心和GH_LAYOUT字段
    """
    print(f"正在读取图层: {layer_name} ...")
    gdf = gpd.read_file(gdb_path, layer=layer_name)

    # 统一转换为WGS84
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    elif gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)

    # 检查id_col是否存在
    if id_col not in gdf.columns:
        if id_col == 'OBJECTID':
            gdf[id_col] = gdf.index
        else:
            raise KeyError(f"列 '{id_col}' 未在数据集中找到。可用列: {gdf.columns.tolist()}")

    # 检查GH_LAYOUT是否存在
    if 'GH_LAYOUT' not in gdf.columns:
        gdf['GH_LAYOUT'] = None

    # 使用投影坐标系计算质心（更准确）
    bounds = gdf.total_bounds
    center_lon = (bounds[0] + bounds[2]) / 2
    center_lat = (bounds[1] + bounds[3]) / 2
    utm_crs = get_utm_crs(center_lon, center_lat)

    gdf_proj = gdf.to_crs(utm_crs)
    centroids_proj = gdf_proj.geometry.centroid
    centroids_wgs84 = gpd.GeoSeries(centroids_proj, crs=utm_crs).to_crs(epsg=4326)

    gdf['centroid_geo'] = centroids_wgs84
    gdf['centroid_x'] = centroids_wgs84.x
    gdf['centroid_y'] = centroids_wgs84.y

    return gdf
