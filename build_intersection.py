# -*- coding: utf-8 -*-
"""
唯一需要运行的入口脚本。

把本文件与所有 GeoJSON 放在同一个脚本文件夹，并从 UE 编辑器的 Python 环境运行。

它会：
1. 扫描同目录 .geojson
2. 按文件名读取 layer_config
3. 自动读取实际 Geometry 类型
4. 自动选择 Polygon / Line / Point Builder
5. 删除同名旧 Actor
6. 重新生成整个路口
"""

from pathlib import Path
import importlib
import sys

import unreal


SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


# ------------------------------------------------------------
# UE Python 会缓存 import。
# 每次运行入口脚本时主动 reload，
# 这样你改了其他模块后不必重启 UE。
# ------------------------------------------------------------
import project_config
import coordinate_utils
import geojson_utils
import polygon_builder
import line_builder
import marking_builder
import point_builder

importlib.reload(project_config)
importlib.reload(coordinate_utils)
importlib.reload(geojson_utils)
importlib.reload(polygon_builder)
importlib.reload(line_builder)
importlib.reload(marking_builder)
importlib.reload(point_builder)

from project_config import DATA_FOLDER, LAYER_CONFIG
from geojson_utils import load_geojson, geometry_types
from polygon_builder import build_polygon_layer
from line_builder import build_line_layer
from marking_builder import build_marking_layer
from point_builder import build_point_layer


def choose_builder(types):
    polygon_types = {"Polygon", "MultiPolygon"}
    line_types = {"LineString", "MultiLineString"}
    point_types = {"Point", "MultiPoint"}

    if types & polygon_types:
        return "polygon"

    if types & line_types:
        return "line"

    if types & point_types:
        return "point"

    return None


def main():
    unreal.log_warning("==============================================")
    unreal.log_warning("GIS -> UE 路口总生成脚本开始")
    unreal.log_warning("数据目录：" + str(DATA_FOLDER))
    unreal.log_warning("==============================================")

    geojson_files = sorted(DATA_FOLDER.glob("*.geojson"))

    if not geojson_files:
        unreal.log_error("当前脚本目录没有找到任何 .geojson 文件")
        return

    success = 0
    skipped = 0
    failed = 0

    for path in geojson_files:
        layer_name = path.stem

        config = LAYER_CONFIG.get(layer_name)

        if config is None:
            unreal.log_warning(f"{layer_name}: 没有配置，跳过")
            skipped += 1
            continue

        if not config.get("enabled", True):
            unreal.log_warning(f"{layer_name}: 当前配置 enabled=False，跳过")
            skipped += 1
            continue

        try:
            data = load_geojson(path)

            types = geometry_types(data)

            unreal.log_warning(
                f"处理 {path.name} | Geometry={sorted(types)}"
            )

            builder_type = choose_builder(types)

            # marking.geojson has semantic attributes (mark_type/width_m/color),
            # so it must be dispatched before the generic LineString builder.
            if layer_name == "marking":
                actor, count = build_marking_layer(
                    layer_name, data, config
                )

            elif builder_type == "polygon":
                actor, count = build_polygon_layer(
                    layer_name, data, config
                )

            elif builder_type == "line":
                actor, count = build_line_layer(
                    layer_name, data, config
                )

            elif builder_type == "point":
                actor, count = build_point_layer(
                    layer_name, data, config
                )

            else:
                unreal.log_warning(
                    f"{layer_name}: 暂不支持 Geometry={sorted(types)}"
                )
                skipped += 1
                continue

            if actor is not None and count > 0:
                success += 1
            else:
                failed += 1

        except Exception as exc:
            failed += 1
            unreal.log_error(
                f"{layer_name}: 生成失败 -> {type(exc).__name__}: {exc}"
            )

    unreal.log_warning("==============================================")
    unreal.log_warning(
        f"生成结束 | 成功图层={success} | 跳过={skipped} | 失败={failed}"
    )
    unreal.log_warning("==============================================")


if __name__ == "__main__":
    main()
