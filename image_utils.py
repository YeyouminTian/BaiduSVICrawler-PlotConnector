import numpy as np
import cv2

def equirectangular_to_perspective(img, fov_h, fov_v, heading, pitch, out_size):
    out_w, out_h = out_size  # (width, height)
    height, width = img.shape[:2]
    xx, yy = np.meshgrid(np.arange(out_w), np.arange(out_h))
    x = (xx - out_w / 2) / (out_w / 2) * np.tan(np.radians(fov_h / 2))
    y = (yy - out_h / 2) / (out_h / 2) * np.tan(np.radians(fov_v / 2))
    z = np.ones_like(x)
    norm = np.sqrt(x ** 2 + y ** 2 + z ** 2)
    x /= norm
    y /= norm
    z /= norm
    heading_rad = np.radians(heading)
    pitch_rad = np.radians(pitch)
    x_rot = x * np.cos(heading_rad) + z * np.sin(heading_rad)
    y_rot = y
    z_rot = -x * np.sin(heading_rad) + z * np.cos(heading_rad)
    x_final = x_rot
    y_final = y_rot * np.cos(pitch_rad) - z_rot * np.sin(pitch_rad)
    z_final = y_rot * np.sin(pitch_rad) + z_rot * np.cos(pitch_rad)
    lon = np.arctan2(x_final, z_final)
    lat = np.arcsin(y_final)
    x_map = (lon / (2 * np.pi) + 0.5) * width
    y_map = (lat / np.pi + 0.5) * height
    perspective = cv2.remap(img, x_map.astype(np.float32), y_map.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
    return perspective 