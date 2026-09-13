# -*- coding: utf-8 -*-
"""
可选检查脚本。
不生成任何 UE Actor，只检查同目录 GeoJSON 的 Geometry 类型。
出现问题时先运行它。
"""

from pathlib import Path
import sys
import importlib
import unreal

SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import geojson_utils
importlib.reload(geojson_utils)

from geojson_utils import load_geojson, geometry_types


def main():
    unreal.log_warning("========== GeoJSON 图层检查 ==========")

    for path in sorted(SCRIPT_DIR.glob("*.geojson")):
        try:
            data = load_geojson(path)
            types = sorted(geometry_types(data))
            unreal.log_warning(f"{path.name}: {types}")
        except Exception as exc:
            unreal.log_error(f"{path.name}: {exc}")

    unreal.log_warning("========== 检查结束 ==========")


if __name__ == "__main__":
    main()
