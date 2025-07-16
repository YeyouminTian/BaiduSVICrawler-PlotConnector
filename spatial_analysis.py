import numpy as np
from math import radians, cos, sin

def judge_left_right(streetview_pt, road_dir, landuse_centroid):
    dx = landuse_centroid[0] - streetview_pt[0]
    dy = landuse_centroid[1] - streetview_pt[1]
    theta = radians(road_dir)
    road_vec = np.array([cos(theta), sin(theta)])
    landuse_vec = np.array([dx, dy])
    cross = road_vec[0] * landuse_vec[1] - road_vec[1] * landuse_vec[0]
    return 'L' if cross > 0 else 'R' 