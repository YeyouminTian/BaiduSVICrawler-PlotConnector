"""
几何与投影工具模块
"""
import geopandas as gpd


def get_utm_crs(lon, lat):
    """根据经纬度自动计算合适的UTM投影EPSG代码"""
    zone = int((lon + 180) / 6) + 1
    if lat >= 0:
        epsg_code = 32600 + zone
    else:
        epsg_code = 32700 + zone
    return f"EPSG:{epsg_code}"


def project_gdf(gdf, target_crs=None):
    """
    将GeoDataFrame投影到米制坐标系

    Args:
        gdf: GeoDataFrame
        target_crs: 目标坐标系，如果为None则自动选择UTM投影

    Returns:
        (投影后的GeoDataFrame, 使用的CRS)
    """
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)

    gdf_wgs84 = gdf.to_crs(epsg=4326) if gdf.crs.to_epsg() != 4326 else gdf

    if target_crs is None:
        bounds = gdf_wgs84.total_bounds
        center_lon = (bounds[0] + bounds[2]) / 2
        center_lat = (bounds[1] + bounds[3]) / 2
        target_crs = get_utm_crs(center_lon, center_lat)
        print(f"自动选择投影: {target_crs} (中心点: {center_lon:.4f}, {center_lat:.4f})")

    return gdf_wgs84.to_crs(target_crs), target_crs
