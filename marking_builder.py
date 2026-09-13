# -*- coding: utf-8 -*-
"""Build GIS road markings as a single UE Dynamic Mesh Actor.

Feature properties used:
  mark_type: continuous category or dash pattern such as "2-4" (metres on-off)
  width_m: stripe width in metres
  color: retained for diagnostics; the configured UE material controls rendering

This module is intended to sit beside coordinate_utils.py, geojson_utils.py,
polygon_builder.py, project_config.py and the GeoJSON files in the UE script folder.
"""

import math
import re

import unreal

from coordinate_utils import coord_to_local_m
from polygon_builder import apply_material, destroy_actor_by_label


_DASH_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*$")


def _iter_geometry_lines(geometry):
    """Yield each LineString coordinate array, including multipart geometries."""
    if not geometry:
        return
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if geometry_type == "LineString":
        yield coordinates
    elif geometry_type == "MultiLineString":
        for line in coordinates:
            yield line
    elif geometry_type == "GeometryCollection":
        for child in geometry.get("geometries", []):
            yield from _iter_geometry_lines(child)


def _iter_feature_lines(data):
    """Yield (properties, line) for FeatureCollections and plain geometries."""
    data_type = data.get("type")
    if data_type == "FeatureCollection":
        for feature in data.get("features", []):
            properties = feature.get("properties") or {}
            yield from ((properties, line) for line in _iter_geometry_lines(feature.get("geometry")))
    elif data_type == "Feature":
        properties = data.get("properties") or {}
        yield from ((properties, line) for line in _iter_geometry_lines(data.get("geometry")))
    else:
        yield from (({}, line) for line in _iter_geometry_lines(data))


def _local_points(raw_line):
    """Convert source coordinates into local UTM metres and remove duplicates."""
    result = []
    for coord in raw_line:
        x, y = coord_to_local_m(coord)
        point = (float(x), float(y))
        if not result or point != result[-1]:
            result.append(point)
    return result


def _line_length(points):
    return sum(
        math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1])
        for i in range(len(points) - 1)
    )


def _point_at_distance(points, cumulative, distance_m):
    if distance_m <= 0.0:
        return points[0]
    if distance_m >= cumulative[-1]:
        return points[-1]
    for i in range(len(points) - 1):
        if cumulative[i] <= distance_m <= cumulative[i + 1]:
            segment_length = cumulative[i + 1] - cumulative[i]
            if segment_length <= 0.0:
                return points[i]
            t = (distance_m - cumulative[i]) / segment_length
            return (
                points[i][0] + (points[i + 1][0] - points[i][0]) * t,
                points[i][1] + (points[i + 1][1] - points[i][1]) * t,
            )
    return points[-1]


def _slice_polyline(points, cumulative, start_m, end_m):
    """Return an exact polyline slice between two distances along the source line."""
    sliced = [_point_at_distance(points, cumulative, start_m)]
    for i in range(1, len(points) - 1):
        if start_m < cumulative[i] < end_m:
            sliced.append(points[i])
    sliced.append(_point_at_distance(points, cumulative, end_m))
    compact = []
    for point in sliced:
        if not compact or point != compact[-1]:
            compact.append(point)
    return compact


def _dash_slices(points, dash_m, gap_m):
    """Yield on-segments with a repeating dash/gap pattern measured in metres."""
    if dash_m <= 0.0 or gap_m < 0.0:
        return
    cumulative = [0.0]
    for i in range(len(points) - 1):
        cumulative.append(
            cumulative[-1] + math.hypot(
                points[i + 1][0] - points[i][0],
                points[i + 1][1] - points[i][1],
            )
        )
    total = cumulative[-1]
    period = dash_m + gap_m
    if total <= 0.0 or period <= 0.0:
        return
    start_m = 0.0
    while start_m < total:
        end_m = min(start_m + dash_m, total)
        if end_m - start_m > 1e-6:
            yield _slice_polyline(points, cumulative, start_m, end_m)
        start_m += period


def _to_ue_path(points, z_local_cm=0.0):
    """Local metres -> UE centimetres; GIS northing maps to UE negative Y."""
    return [
        unreal.Vector(x_m * 100.0, -y_m * 100.0, z_local_cm)
        for x_m, y_m in points
    ]


def _append_stripe(
    dynamic_mesh,
    primitive_options,
    points,
    width_cm,
    thickness_cm
):
    """
    把一条 GIS 线生成水平 Ribbon 标线。

    points:
        局部米制坐标 [(x, y), ...]

    width_cm:
        标线宽度，单位 cm

    thickness_cm:
        当前版本不用做实体厚度，
        只保留参数兼容。
    """

    if len(points) < 2:
        return False

    half_width_m = (width_cm / 100.0) * 0.5

    left_points = []
    right_points = []

    # ========================================================
    # 1. 每个中心线点计算一个水平法线
    # ========================================================

    for i in range(len(points)):

        # 起点：使用下一段方向
        if i == 0:
            dx = points[1][0] - points[0][0]
            dy = points[1][1] - points[0][1]

        # 终点：使用上一段方向
        elif i == len(points) - 1:
            dx = points[-1][0] - points[-2][0]
            dy = points[-1][1] - points[-2][1]

        # 中间点：用前后方向平均
        else:
            dx1 = points[i][0] - points[i - 1][0]
            dy1 = points[i][1] - points[i - 1][1]

            dx2 = points[i + 1][0] - points[i][0]
            dy2 = points[i + 1][1] - points[i][1]

            len1 = math.hypot(dx1, dy1)
            len2 = math.hypot(dx2, dy2)

            if len1 > 1e-9:
                dx1 /= len1
                dy1 /= len1

            if len2 > 1e-9:
                dx2 /= len2
                dy2 /= len2

            dx = dx1 + dx2
            dy = dy1 + dy2


        length = math.hypot(dx, dy)

        if length < 1e-9:
            continue

        dx /= length
        dy /= length


        # ====================================================
        # 2. 水平法线
        #
        # 中心线方向：
        # (dx, dy)
        #
        # 左法线：
        # (-dy, dx)
        # ====================================================

        nx = -dy
        ny = dx

        cx = points[i][0]
        cy = points[i][1]

        left_points.append(
            (
                cx + nx * half_width_m,
                cy + ny * half_width_m,
            )
        )

        right_points.append(
            (
                cx - nx * half_width_m,
                cy - ny * half_width_m,
            )
        )


    if len(left_points) < 2:
        return False


    # ========================================================
    # 3. 每两组左右点生成一个水平四边形
    #
    # 四边形：
    #
    # L0 -------- L1
    # |           |
    # |           |
    # R0 -------- R1
    #
    # Polygon 挤出极薄高度
    # ========================================================

    for i in range(len(left_points) - 1):

        l0 = left_points[i]
        l1 = left_points[i + 1]

        r0 = right_points[i]
        r1 = right_points[i + 1]

        polygon = [
            unreal.Vector2D(
                l0[0] * 100.0,
                -l0[1] * 100.0
            ),

            unreal.Vector2D(
                r0[0] * 100.0,
                -r0[1] * 100.0
            ),

            unreal.Vector2D(
                r1[0] * 100.0,
                -r1[1] * 100.0
            ),

            unreal.Vector2D(
                l1[0] * 100.0,
                -l1[1] * 100.0
            ),
        ]


        # Geometry Script 要逆时针
        area = 0.0

        for j in range(len(polygon)):

            k = (j + 1) % len(polygon)

            area += (
                polygon[j].x * polygon[k].y
                -
                polygon[k].x * polygon[j].y
            )

        if area < 0:
            polygon.reverse()


        unreal.GeometryScript_Primitives.append_simple_extrude_polygon(
            target_mesh=dynamic_mesh,
            primitive_options=primitive_options,
            transform=unreal.Transform(),
            polygon_vertices=polygon,

            # 只做非常薄的一层
            height=0.2,

            height_steps=0,
            capped=True,

            origin=unreal.GeometryScriptPrimitiveOriginMode.BASE,
        )


    return True


def build_marking_layer(layer_name, data, config):
    """Replace Road_Marking and generate stripes from feature attributes."""
    actor_name = config.get("actor_name", "Road_Marking")
    z_cm = float(config.get("z_cm", 0.0))
    fallback_width_cm = float(config.get("width_cm", 15.0))
    thickness_cm = float(config.get("thickness_cm", 1.0))

    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    destroy_actor_by_label(actor_name)

    actor = subsystem.spawn_actor_from_class(
        unreal.DynamicMeshActor,
        unreal.Vector(0.0, 0.0, z_cm),
        unreal.Rotator(0.0, 0.0, 0.0),
    )
    if not actor:
        unreal.log_error("Road_Marking: 无法创建 DynamicMeshActor")
        return None, 0

    actor.set_actor_label(actor_name)
    folder = config.get("folder")
    if folder:
        actor.set_folder_path(folder)

    component = actor.get_component_by_class(unreal.DynamicMeshComponent)
    dynamic_mesh = component.get_dynamic_mesh()
    dynamic_mesh.reset()
    primitive_options = unreal.GeometryScriptPrimitiveOptions()

    source_lines = 0
    generated_stripes = 0
    dashed_lines = 0
    color_counts = {}

    for properties, raw_line in _iter_feature_lines(data):
        points = _local_points(raw_line)
        if len(points) < 2:
            continue

        source_lines += 1
        mark_type = str(properties.get("mark_type", "")).strip()
        color = str(properties.get("color", "")).strip()
        color_counts[color or "(未设置)"] = color_counts.get(color or "(未设置)", 0) + 1

        try:
            width_m = float(properties.get("width_m"))
            if width_m <= 0.0:
                raise ValueError("width_m 必须大于 0")
            width_cm = width_m * 100.0
        except (TypeError, ValueError):
            width_cm = fallback_width_cm
            unreal.log_warning(
                f"标线缺少有效 width_m，使用配置回退宽度 {width_cm:.1f} cm"
            )

        dash_match = _DASH_PATTERN.match(mark_type)
        if dash_match:
            dash_m = float(dash_match.group(1))
            gap_m = float(dash_match.group(2))
            dashed_lines += 1
            for stripe_points in _dash_slices(points, dash_m, gap_m):
                if _append_stripe(
                    dynamic_mesh, primitive_options, stripe_points,
                    width_cm, thickness_cm,
                ):
                    generated_stripes += 1
        else:
            if _append_stripe(
                dynamic_mesh, primitive_options, points,
                width_cm, thickness_cm,
            ):
                generated_stripes += 1

    if generated_stripes == 0:
        subsystem.destroy_actor(actor)
        unreal.log_warning(f"{layer_name}: 没有可生成的标线 LineString")
        return None, 0

    try:
        unreal.GeometryScript_Normals.set_per_face_normals(dynamic_mesh)
    except Exception:
        pass
    try:
        component.notify_mesh_modified()
    except Exception:
        pass

    apply_material(component, config.get("material"))
    unreal.log_warning(
        f"{layer_name}: 标线重建完成 | Actor={actor_name} | "
        f"线段={source_lines} | 虚线={dashed_lines} | "
        f"生成条带={generated_stripes} | 颜色属性={color_counts}"
    )
    return actor, source_lines
