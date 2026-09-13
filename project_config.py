# -*- coding: utf-8 -*-
"""
项目统一配置
QGIS / GeoJSON -> UE5 路口生成
"""

from pathlib import Path

# ------------------------------------------------------------
# 数据目录
# 默认：所有 .py 和 .geojson 放在同一个文件夹
# ------------------------------------------------------------
DATA_FOLDER = Path(__file__).resolve().parent

# ------------------------------------------------------------
# 路口局部原点
# EPSG:32651 / WGS84 UTM Zone 51N
# ------------------------------------------------------------
ORIGIN_EASTING = 345478.104486
ORIGIN_NORTHING = 3170937.085305
UTM_ZONE = 51

# GIS 米 -> UE 厘米
M_TO_CM = 100.0

# 生成 Actor 的统一前缀不是必须，这里保持名称清晰即可
GENERATED_FOLDER_NAME = "GIS_Generated"

# ------------------------------------------------------------
# 图层配置
#
# enabled:
#   True  = 总脚本会处理
#   False = 暂时保留数据但不生成
#
# z_cm:
#   Actor 在 UE 中的 Z
#
# height_cm:
#   Polygon 挤出厚度
#
# width_cm / thickness_cm:
#   LineString 扫掠成带状 Mesh 时的宽度 / 厚度
# ------------------------------------------------------------
LAYER_CONFIG = {

    # ========================================================
    # 地面
    # ========================================================

    "road_surface": {
        "enabled": True,
        "actor_name": "Road_Surface",

        "z_cm": 0.0,
        "height_cm": 15.0,

        "folder": "gis/地面",

        "material": "/Game/道路材质",
    },

    "sidewalk": {
        "enabled": True,
        "actor_name": "Sidewalk",

        "z_cm": 0.0,
        "height_cm": 20.0,

        "folder": "gis/地面",

        "material":"/Game/行人道材质",
    },

    "greenbelt": {
        "enabled": True,
        "actor_name": "Greenbelt",

        "z_cm": 20.0,
        "height_cm": 5.0,

        "folder": "gis/地面",

        "material": "/Game/绿化材质",
    },

    "traffic_island": {
        "enabled": True,
        "actor_name": "Traffic_Island",

        "z_cm": 0.0,
        "height_cm": 20.0,

        "folder": "gis/地面",

        "material": "/Game/交通岛材质",
    },


    # ========================================================
    # 标线
    # ========================================================

    "arrow_left_3m": {
        "enabled": True,
        "actor_name": "Arrow_Left",

        "z_cm": 17.0,
        "height_cm": 1.0,

        "folder": "gis/标线",

        "material": "/Game/标线材质",
    },

    "arrow_right_3m": {
        "enabled": True,
        "actor_name": "Arrow_Right",

        "z_cm": 17.0,
        "height_cm": 1.0,

        "folder": "gis/标线",

        "material": "/Game/标线材质",
    },

    "arrow_straight_3m": {
        "enabled": True,
        "actor_name": "Arrow_Straight",

        "z_cm": 17.0,
        "height_cm": 1.0,

        "folder": "gis/标线",

        "material": "/Game/标线材质",
    },

    "marking": {
        "enabled": True,
        "actor_name": "Road_Marking",

        "z_cm": 17.0,

        # 如果 GeoJSON 是 Polygon
        "height_cm": 1.0,

        # 标线 Feature 的 width_m 属性优先；此值只作缺少属性时的回退。
        "width_cm": 17.0,
        "thickness_cm": 1.0,

        "folder": "gis/标线",

        "material": "/Game/标线材质",
    },


    # ========================================================
    # 暂不正式生成
    # ========================================================

    "guardrail": {
        "enabled": False,
        "actor_name": "Guardrail_Guide",

        "z_cm": 0.0,
        "width_cm": 10.0,
        "thickness_cm": 100.0,

        "folder": "gis/设施",

        "material": None,
    },

    "road_centerline": {
        "enabled": False,
        "actor_name": "Road_Centerline_Guide",

        "z_cm": 16.0,
        "width_cm": 5.0,
        "thickness_cm": 1.0,

        "folder": "gis/辅助",

        "material": None,
    },


    # ========================================================
    # 道路设施定位
    # ========================================================
    "road_facility": {
        "enabled": True,
        "actor_name": "Road_Facility_Locators",

        "z_cm": 30.0,
        "marker_radius_cm": 20.0,

        "folder": "gis/设施",

        "material": None,
    },
}
