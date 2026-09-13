# -*- coding: utf-8 -*-
"""
坐标转换：
1. 自动判断 GeoJSON 坐标像不像 WGS84 经纬度
2. 如果是经纬度 -> 转 EPSG:32651 (UTM 51N)
3. 减去路口原点 -> 局部米制坐标
4. QGIS +Y(北) -> UE -Y
5. 米 -> 厘米
"""

import math

from project_config import (
    ORIGIN_EASTING,
    ORIGIN_NORTHING,
    UTM_ZONE,
    M_TO_CM,
)


def looks_like_wgs84(x, y):
    """粗判断：x/y 是否像经纬度。"""
    return -180.0 <= x <= 180.0 and -90.0 <= y <= 90.0


def wgs84_to_utm(lon_deg, lat_deg, zone=UTM_ZONE):
    """
    纯 Python WGS84 -> UTM。
    当前项目位于北半球，使用 UTM Zone 51N。
    不依赖 pyproj，避免 UE Python 环境没有第三方库。
    """
    a = 6378137.0
    ecc_sq = 0.0066943799901413165
    ecc_prime_sq = ecc_sq / (1.0 - ecc_sq)
    k0 = 0.9996

    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)

    lon_origin_deg = (zone - 1) * 6 - 180 + 3
    lon_origin = math.radians(lon_origin_deg)

    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    tan_lat = math.tan(lat)

    n = a / math.sqrt(1.0 - ecc_sq * sin_lat * sin_lat)
    t = tan_lat * tan_lat
    c = ecc_prime_sq * cos_lat * cos_lat
    A = cos_lat * (lon - lon_origin)

    m = a * (
        (1 - ecc_sq / 4 - 3 * ecc_sq**2 / 64 - 5 * ecc_sq**3 / 256) * lat
        - (3 * ecc_sq / 8 + 3 * ecc_sq**2 / 32 + 45 * ecc_sq**3 / 1024)
        * math.sin(2 * lat)
        + (15 * ecc_sq**2 / 256 + 45 * ecc_sq**3 / 1024)
        * math.sin(4 * lat)
        - (35 * ecc_sq**3 / 3072) * math.sin(6 * lat)
    )

    easting = (
        k0
        * n
        * (
            A
            + (1 - t + c) * A**3 / 6
            + (5 - 18 * t + t**2 + 72 * c - 58 * ecc_prime_sq)
            * A**5
            / 120
        )
        + 500000.0
    )

    northing = k0 * (
        m
        + n
        * tan_lat
        * (
            A**2 / 2
            + (5 - t + 9 * c + 4 * c**2) * A**4 / 24
            + (
                61
                - 58 * t
                + t**2
                + 600 * c
                - 330 * ecc_prime_sq
            )
            * A**6
            / 720
        )
    )

    # 当前项目是北半球，不加南半球 10,000,000m 假北距
    return easting, northing


def source_xy_to_utm(x, y):
    """
    输入可能是：
    - WGS84 lon/lat
    - EPSG:32651 Easting/Northing
    """
    x = float(x)
    y = float(y)

    if looks_like_wgs84(x, y):
        return wgs84_to_utm(x, y)

    # 否则按当前项目的 EPSG:32651 米制坐标处理
    return x, y


def coord_to_local_m(coord):
    """
    GeoJSON 坐标 -> 路口局部米制坐标。
    coord 可为 [x, y] 或 [x, y, z]。
    """
    x = float(coord[0])
    y = float(coord[1])

    easting, northing = source_xy_to_utm(x, y)

    local_x = easting - ORIGIN_EASTING
    local_y = northing - ORIGIN_NORTHING

    return local_x, local_y


def coord_to_ue_cm(coord, z_cm=0.0):
    """
    QGIS:
      +X = 东
      +Y = 北

    当前 UE / Cesium 局部:
      +X = 东
      +Y = 南

    所以:
      UE X = local_x
      UE Y = -local_y
    """
    local_x, local_y = coord_to_local_m(coord)

    ue_x = local_x * M_TO_CM
    ue_y = -local_y * M_TO_CM

    return ue_x, ue_y, float(z_cm)
