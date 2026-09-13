# -*- coding: utf-8 -*-

import math
from pathlib import Path

import unreal

from project_config import DATA_FOLDER
from geojson_utils import (
    load_geojson,
    iter_polygons,
    remove_closing_duplicate,
    remove_consecutive_duplicates,
)
from coordinate_utils import coord_to_local_m


# ============================================================
# 配置
# ============================================================

# 裁剪比真实 GIS Mesh 向外多多少米
# 先用 0.25m = 25cm
CLIP_MARGIN_M = 0.25

CLIP_FOLDER = "地图裁剪"

TERRAIN_ACTOR_NAME = "Cesium World Terrain"


CLIP_LAYERS = {
    "road_surface": "Road_Terrain_Clip",
    "sidewalk": "Sidewalk_Terrain_Clip",
    "greenbelt": "Greenbelt_Terrain_Clip",
    "traffic_island": "TrafficIsland_Terrain_Clip",
}


# ============================================================
# 二维几何工具
# ============================================================

def signed_area(points):
    area = 0.0

    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]

        area += x1 * y2 - x2 * y1

    return area * 0.5


def normalize(x, y):

    length = math.hypot(x, y)

    if length < 1e-9:
        return 0.0, 0.0

    return x / length, y / length


def cross(ax, ay, bx, by):
    return ax * by - ay * bx


def offset_polygon(points, distance):
    """
    给简单 Polygon 做小距离向外扩张。

    这里专门用于 Cesium 裁剪，
    不修改真正的 Road / Sidewalk Mesh。
    """

    if len(points) < 3:
        return points

    area = signed_area(points)

    # CCW = True
    ccw = area > 0.0

    result = []

    count = len(points)

    for i in range(count):

        prev_point = points[(i - 1) % count]
        point = points[i]
        next_point = points[(i + 1) % count]

        px, py = point

        # 前一条边
        d1x, d1y = normalize(
            point[0] - prev_point[0],
            point[1] - prev_point[1],
        )

        # 后一条边
        d2x, d2y = normalize(
            next_point[0] - point[0],
            next_point[1] - point[1],
        )

        # ----------------------------------------------------
        # 求 Polygon 外法线
        #
        # CCW Polygon：
        # 内部在边左侧，所以外侧是右边
        # ----------------------------------------------------

        if ccw:

            n1x, n1y = d1y, -d1x
            n2x, n2y = d2y, -d2x

        else:

            n1x, n1y = -d1y, d1x
            n2x, n2y = -d2y, d2x


        # 两条已经向外平移的边
        p1x = px + n1x * distance
        p1y = py + n1y * distance

        p2x = px + n2x * distance
        p2y = py + n2y * distance


        denominator = cross(
            d1x,
            d1y,
            d2x,
            d2y,
        )


        # ----------------------------------------------------
        # 两条边基本平行
        # ----------------------------------------------------

        if abs(denominator) < 1e-7:

            nx, ny = normalize(
                n1x + n2x,
                n1y + n2y,
            )

            if abs(nx) < 1e-7 and abs(ny) < 1e-7:

                nx = n1x
                ny = n1y

            result.append(
                (
                    px + nx * distance,
                    py + ny * distance,
                )
            )

            continue


        # ----------------------------------------------------
        # 求两条 Offset Line 的交点
        # ----------------------------------------------------

        qpx = p2x - p1x
        qpy = p2y - p1y

        t = cross(
            qpx,
            qpy,
            d2x,
            d2y,
        ) / denominator

        ix = p1x + d1x * t
        iy = p1y + d1y * t


        # ----------------------------------------------------
        # 防止非常尖的角产生超长尖刺
        # ----------------------------------------------------

        miter_distance = math.hypot(
            ix - px,
            iy - py,
        )

        max_miter = distance * 5.0


        if miter_distance > max_miter:

            nx, ny = normalize(
                n1x + n2x,
                n1y + n2y,
            )

            if abs(nx) < 1e-7 and abs(ny) < 1e-7:

                nx = n1x
                ny = n1y

            ix = px + nx * distance
            iy = py + ny * distance


        result.append(
            (ix, iy)
        )


    return result


# ============================================================
# 创建一个 Cesium Cartographic Polygon
# ============================================================

def create_clip_actor(
    actor_system,
    actor_name,
    local_points,
):

    clip_actor = actor_system.spawn_actor_from_class(
        unreal.CesiumCartographicPolygon,
        unreal.Vector(0.0, 0.0, 0.0),
        unreal.Rotator(0.0, 0.0, 0.0),
    )

    clip_actor.set_actor_label(actor_name)

    # 和 gis / cesium 平级
    clip_actor.set_folder_path(
        CLIP_FOLDER
    )


    spline = clip_actor.get_component_by_class(
        unreal.SplineComponent
    )

    spline.clear_spline_points(
        False
    )


    for local_x, local_y in local_points:

        # GIS局部米 → UE厘米
        #
        # GIS +Y 北
        # UE  +Y 南

        ue_x = local_x * 100.0
        ue_y = -local_y * 100.0

        spline.add_spline_point(
            unreal.Vector(
                ue_x,
                ue_y,
                0.0,
            ),
            unreal.SplineCoordinateSpace.WORLD,
            False,
        )


    spline.set_closed_loop(
        True,
        False,
    )


    for point_index in range(
        spline.get_number_of_spline_points()
    ):

        spline.set_spline_point_type(
            point_index,
            unreal.SplinePointType.LINEAR,
            False,
        )


    spline.update_spline()

    return clip_actor


# ============================================================
# MAIN
# ============================================================

def main():

    unreal.log_warning(
        "========================================"
    )

    unreal.log_warning(
        "开始重建全部 Cesium Terrain Clip"
    )

    unreal.log_warning(
        "裁剪外扩："
        + str(CLIP_MARGIN_M)
        + " m"
    )


    actor_system = unreal.get_editor_subsystem(
        unreal.EditorActorSubsystem
    )

    all_actors = actor_system.get_all_level_actors()


    # ========================================================
    # 1. 删除以前生成的裁剪 Polygon
    # ========================================================

    clip_prefixes = tuple(
        CLIP_LAYERS.values()
    )


    for actor in all_actors:

        if not isinstance(
            actor,
            unreal.CesiumCartographicPolygon
        ):
            continue

        actor_label = actor.get_actor_label()

        if actor_label.startswith(
            clip_prefixes
        ):

            actor_system.destroy_actor(
                actor
            )


    # ========================================================
    # 2. 根据四类 GIS 地表重新生成 Clip
    # ========================================================

    new_clip_actors = []


    for layer_name, clip_prefix in CLIP_LAYERS.items():

        geojson_path = (
            Path(DATA_FOLDER)
            / f"{layer_name}.geojson"
        )


        if not geojson_path.exists():

            unreal.log_warning(
                "找不到："
                + str(geojson_path)
            )

            continue


        data = load_geojson(
            geojson_path
        )


        polygon_index = 0


        for rings in iter_polygons(data):

            if not rings:
                continue


            outer_ring = remove_closing_duplicate(
                rings[0]
            )

            outer_ring = remove_consecutive_duplicates(
                outer_ring
            )


            if len(outer_ring) < 3:
                continue


            # -----------------------------------------------
            # GeoJSON真实坐标 → 局部米
            # -----------------------------------------------

            local_points = []

            for coord in outer_ring:

                local_x, local_y = coord_to_local_m(
                    coord
                )

                local_points.append(
                    (
                        local_x,
                        local_y,
                    )
                )


            # -----------------------------------------------
            # 只对 Clip 向外扩
            # GIS Mesh 本身完全不变
            # -----------------------------------------------

            buffered_points = offset_polygon(
                local_points,
                CLIP_MARGIN_M,
            )


            polygon_index += 1


            # Road 第一块继续保留熟悉的名称
            if (
                layer_name == "road_surface"
                and polygon_index == 1
            ):

                actor_name = "Road_Terrain_Clip"

            else:

                actor_name = (
                    f"{clip_prefix}_"
                    f"{polygon_index:03d}"
                )


            clip_actor = create_clip_actor(
                actor_system,
                actor_name,
                buffered_points,
            )


            new_clip_actors.append(
                clip_actor
            )


            unreal.log_warning(
                "生成裁剪："
                + actor_name
            )


    # ========================================================
    # 3. 找 Cesium World Terrain
    # ========================================================

    terrain_actor = None


    for actor in actor_system.get_all_level_actors():

        if (
            actor.get_actor_label()
            == TERRAIN_ACTOR_NAME
        ):

            terrain_actor = actor
            break


    if terrain_actor is None:

        raise RuntimeError(
            "没有找到 Cesium World Terrain"
        )


    # ========================================================
    # 4. 找 Polygon Raster Overlay
    # ========================================================

    overlay = None


    components = terrain_actor.get_components_by_class(
        unreal.ActorComponent
    )


    for component in components:

        if (
            component.get_class().get_name()
            == "CesiumPolygonRasterOverlay"
        ):

            overlay = component
            break


    if overlay is None:

        raise RuntimeError(
            "Cesium World Terrain 上没有 "
            "CesiumPolygonRasterOverlay"
        )


    # ========================================================
    # 5. 自动填入全部 Polygon
    # ========================================================

    new_clip_actors.sort(
        key=lambda actor:
        actor.get_actor_label()
    )


    overlay.set_editor_property(
        "polygons",
        new_clip_actors,
    )

    overlay.set_editor_property(
        "invert_selection",
        False,
    )

    overlay.set_editor_property(
        "exclude_selected_tiles",
        True,
    )


    # ========================================================
    # 6. 自动 Refresh
    # ========================================================

    overlay.refresh()


    unreal.log_warning(
        "========================================"
    )

    unreal.log_warning(
        "Terrain Clip 重建完成"
    )

    unreal.log_warning(
        "Polygon 数量："
        + str(len(new_clip_actors))
    )

    unreal.log_warning(
        "========================================"
    )


if __name__ == "__main__":
    main()