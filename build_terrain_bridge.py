# -*- coding: utf-8 -*-
"""
Build a terrain-following bridge/skirt between Road_Surface
and Cesium terrain.

用途：
    road_surface.geojson 外轮廓
        ↓
    UE局部坐标
        ↓
    向外偏移一点
        ↓
    Line Trace采样Cesium地形Z
        ↓
    生成道路边缘到地形之间的桥接面
"""

import math
import unreal

from geojson_utils import load_geojson
from coordinate_utils import coord_to_ue_cm
from project_config import DATA_FOLDER


# ============================================================
# 可调参数
# ============================================================

ROAD_GEOJSON = DATA_FOLDER / "road_surface.geojson"

ACTOR_LABEL = "Road_Terrain_Bridge"
ACTOR_FOLDER = "地图裁剪/边缘过渡"

# 你的Road_Surface顶部大约在15cm附近。
# 如果当前实际道路顶面不是这个数，后面只改这里。
ROAD_TOP_Z_CM = 15.0

# 从道路边缘稍微向外伸出去一点。
# 先用50cm。这样桥接面不是完全竖直，会形成一个小斜坡。
OUTWARD_OFFSET_CM = 50.0

# Line Trace范围。
# 对你这个路口足够大。
TRACE_TOP_Z_CM = 5000.0
TRACE_BOTTOM_Z_CM = -5000.0

# 地形连接点略微压进地形，避免留下细黑缝。
TERRAIN_Z_BIAS_CM = -5.0

# 如果边太长，就插值采样。
# 100cm = 每约1米一个点。
MAX_SEGMENT_LENGTH_CM = 100.0

# 材质，可暂时None。
BRIDGE_MATERIAL = None
# 例如：
# BRIDGE_MATERIAL = "/Game/道路材质.道路材质"


# ============================================================
# 工具函数
# ============================================================

def _get_editor_world():
    subsystem = unreal.get_editor_subsystem(
        unreal.UnrealEditorSubsystem
    )
    return subsystem.get_editor_world()


def _get_actor_subsystem():
    return unreal.get_editor_subsystem(
        unreal.EditorActorSubsystem
    )


def _find_actor(label):
    subsystem = _get_actor_subsystem()

    for actor in subsystem.get_all_level_actors():
        if actor and actor.get_actor_label() == label:
            return actor

    return None


def _delete_existing_actor():
    subsystem = _get_actor_subsystem()
    actor = _find_actor(ACTOR_LABEL)

    if actor:
        subsystem.destroy_actor(actor)
        unreal.log(
            "[TerrainBridge] 删除旧Actor: {}".format(ACTOR_LABEL)
        )


def _signed_area(points):
    """
    计算二维polygon的方向。
    >0 通常表示逆时针。
    """

    area = 0.0

    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]

        area += x1 * y2 - x2 * y1

    return area * 0.5


def _densify_ring(points, max_length_cm):
    """
    长边插值。
    避免Cesium地形高低变化较大时，
    一整段只采两个点。
    """

    result = []

    count = len(points)

    for i in range(count):
        a = points[i]
        b = points[(i + 1) % count]

        ax, ay = a
        bx, by = b

        dx = bx - ax
        dy = by - ay

        length = math.hypot(dx, dy)

        steps = max(
            1,
            int(math.ceil(length / max_length_cm))
        )

        for j in range(steps):
            t = j / steps

            x = ax + dx * t
            y = ay + dy * t

            result.append((x, y))

    return result


def _outward_offset_ring(points, distance_cm):
    """
    简单的顶点法线外扩。

    注意：
    这是小范围视觉桥接用途，
    不是GIS精确buffer。
    """

    if len(points) < 3:
        return points

    ccw = _signed_area(points) > 0.0

    result = []

    count = len(points)

    for i in range(count):

        prev_pt = points[(i - 1) % count]
        curr_pt = points[i]
        next_pt = points[(i + 1) % count]

        px, py = prev_pt
        cx, cy = curr_pt
        nx, ny = next_pt

        # 前一段方向
        d1x = cx - px
        d1y = cy - py

        # 后一段方向
        d2x = nx - cx
        d2y = ny - cy

        len1 = math.hypot(d1x, d1y)
        len2 = math.hypot(d2x, d2y)

        if len1 < 1e-6 or len2 < 1e-6:
            result.append(curr_pt)
            continue

        d1x /= len1
        d1y /= len1

        d2x /= len2
        d2y /= len2

        # UE XY平面的外法线
        if ccw:
            n1x, n1y = d1y, -d1x
            n2x, n2y = d2y, -d2x
        else:
            n1x, n1y = -d1y, d1x
            n2x, n2y = -d2y, d2x

        ox = n1x + n2x
        oy = n1y + n2y

        olen = math.hypot(ox, oy)

        if olen < 1e-6:
            ox, oy = n1x, n1y
        else:
            ox /= olen
            oy /= olen

        result.append((
            cx + ox * distance_cm,
            cy + oy * distance_cm
        ))

    return result


def _trace_terrain_z(x, y, actors_to_ignore):
    """
    从高处向下Line Trace。

    命中Cesium地形后返回Z。
    """

    world = _get_editor_world()

    start = unreal.Vector(
        x,
        y,
        TRACE_TOP_Z_CM
    )

    end = unreal.Vector(
        x,
        y,
        TRACE_BOTTOM_Z_CM
    )

    hit = unreal.SystemLibrary.line_trace_single(
        world,
        start,
        end,
        unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
        False,
        actors_to_ignore,
        unreal.DrawDebugTrace.NONE,
        True
    )

    if not hit:
        return None

    # UE Python不同版本返回结构可能略有区别。
    # BreakHitResult是最稳定的读取方式。
    hit_data = unreal.GameplayStatics.break_hit_result(hit)

    # Hit Location
    location = hit_data[4]

    if location is None:
        return None

    return location.z + TERRAIN_Z_BIAS_CM


def _get_outer_rings():
    """
    读取road_surface.geojson外环。
    目前只取Polygon/MultiPolygon的outer ring。
    """

    data = load_geojson(str(ROAD_GEOJSON))

    rings = []

    for feature in data.get("features", []):

        geometry = feature.get("geometry") or {}

        kind = geometry.get("type")
        coords = geometry.get("coordinates", [])

        polygons = []

        if kind == "Polygon":
            polygons = [coords]

        elif kind == "MultiPolygon":
            polygons = coords

        else:
            continue

        for polygon in polygons:

            if not polygon:
                continue

            outer = polygon[0]

            points = []

            for coord in outer:

                x, y, _ = coord_to_ue_cm(
                    coord,
                    ROAD_TOP_Z_CM
                )

                points.append((x, y))

            # GeoJSON最后一个点一般重复第一个点。
            if (
                len(points) > 1
                and math.isclose(
                    points[0][0],
                    points[-1][0],
                    abs_tol=0.01
                )
                and math.isclose(
                    points[0][1],
                    points[-1][1],
                    abs_tol=0.01
                )
            ):
                points.pop()

            if len(points) >= 3:
                rings.append(points)

    return rings


# ============================================================
# Mesh生成
# ============================================================

def _add_quad(mesh, a, b, c, d):
    """
    四边形拆成两个三角形：

        a ----- b
        |     / |
        |   /   |
        d ----- c
    """

    _, ia = mesh.add_vertex_to_mesh(a)
    _, ib = mesh.add_vertex_to_mesh(b)
    _, ic = mesh.add_vertex_to_mesh(c)
    _, id_ = mesh.add_vertex_to_mesh(d)

    mesh.add_triangle_to_mesh(
        unreal.IntVector(
            ia,
            ib,
            ic
        )
    )

    mesh.add_triangle_to_mesh(
        unreal.IntVector(
            ia,
            ic,
            id_
        )
    )


def _create_dynamic_mesh_actor():
    subsystem = _get_actor_subsystem()

    actor = subsystem.spawn_actor_from_class(
        unreal.DynamicMeshActor,
        unreal.Vector(0, 0, 0),
        unreal.Rotator(0, 0, 0)
    )

    actor.set_actor_label(ACTOR_LABEL)
    actor.set_folder_path(ACTOR_FOLDER)

    return actor


# ============================================================
# 主函数
# ============================================================

def build_terrain_bridge():

    unreal.log_warning(
        "======================================"
    )

    unreal.log_warning(
        "[TerrainBridge] 开始生成道路-地形桥接面"
    )

    _delete_existing_actor()

    road_actor = _find_actor("Road_Surface")

    ignore_actors = []

    if road_actor:
        ignore_actors.append(road_actor)

    rings = _get_outer_rings()

    if not rings:
        raise RuntimeError(
            "road_surface.geojson 未找到可用Polygon"
        )

    actor = _create_dynamic_mesh_actor()

    component = actor.get_component_by_class(
        unreal.DynamicMeshComponent
    )

    if not component:
        raise RuntimeError(
            "无法取得DynamicMeshComponent"
        )

    mesh = component.get_dynamic_mesh()

    successful_points = 0
    failed_points = 0

    for ring_index, ring in enumerate(rings):

        # 先插值
        dense = _densify_ring(
            ring,
            MAX_SEGMENT_LENGTH_CM
        )

        # 外扩
        terrain_xy = _outward_offset_ring(
            dense,
            OUTWARD_OFFSET_CM
        )

        road_points = []
        terrain_points = []

        for i in range(len(dense)):

            road_x, road_y = dense[i]
            terrain_x, terrain_y = terrain_xy[i]

            terrain_z = _trace_terrain_z(
                terrain_x,
                terrain_y,
                ignore_actors
            )

            if terrain_z is None:

                unreal.log_warning(
                    "[TerrainBridge] 地形采样失败 ring={} point={}".format(
                        ring_index,
                        i
                    )
                )

                # 采不到时先给一个安全值，
                # 这样整个mesh不会断掉。
                terrain_z = (
                    ROAD_TOP_Z_CM - 300.0
                )

                failed_points += 1

            else:
                successful_points += 1

            road_points.append(
                unreal.Vector(
                    road_x,
                    road_y,
                    ROAD_TOP_Z_CM
                )
            )

            terrain_points.append(
                unreal.Vector(
                    terrain_x,
                    terrain_y,
                    terrain_z
                )
            )

        count = len(road_points)

        for i in range(count):

            j = (i + 1) % count

            road_a = road_points[i]
            road_b = road_points[j]

            terrain_b = terrain_points[j]
            terrain_a = terrain_points[i]

            _add_quad(
                mesh,
                road_a,
                road_b,
                terrain_b,
                terrain_a
            )

    component.notify_mesh_updated()

    # 材质
    if BRIDGE_MATERIAL:

        material = unreal.EditorAssetLibrary.load_asset(
            BRIDGE_MATERIAL
        )

        if material:
            component.set_material(
                0,
                material
            )

    unreal.log_warning(
        "[TerrainBridge] 完成"
    )

    unreal.log_warning(
        "[TerrainBridge] 地形采样成功={} 失败={}".format(
            successful_points,
            failed_points
        )
    )

    unreal.log_warning(
        "======================================"
    )

    return actor


# 在UE Python中直接运行此文件时：
build_terrain_bridge()