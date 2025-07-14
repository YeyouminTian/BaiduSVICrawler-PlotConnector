import geopandas as gpd
from shapely.geometry import Point

# 1. 地块数据读取
def read_landuse_gdb(gdb_path, layer_name='landuse', id_col='OBJECTID'):
    gdf = gpd.read_file(gdb_path, layer=layer_name)
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    gdf['centroid'] = gdf.geometry.centroid
    gdf['centroid_x'] = gdf['centroid'].x
    gdf['centroid_y'] = gdf['centroid'].y
    # 返回时包含GH_LAYOUT字段
    return gdf[[id_col, 'geometry', 'centroid', 'centroid_x', 'centroid_y', 'GH_LAYOUT']] 