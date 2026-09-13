# -*- coding: utf-8 -*-
"""Polygon / MultiPolygon -> UE Dynamic Mesh。"""

import unreal

from coordinate_utils import coord_to_ue_cm
from geojson_utils import (
    iter_polygons,
    remove_closing_duplicate,
    remove_consecutive_duplicates,
)


def destroy_actor_by_label(label):
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    for actor in subsystem.get_all_level_actors():
        if actor.get_actor_label() == label:
            subsystem.destroy_actor(actor)


def signed_area(points):
    area = 0.0

    for i in range(len(points)):
        j = (i + 1) % len(points)
        area += points[i].x * points[j].y - points[j].x * points[i].y

    return area * 0.5


def apply_material(component, material_path):
    if not material_path:
        return

    material = unreal.load_asset(material_path)

    if material:
        component.set_material(0, material)
    else:
        unreal.log_warning("材质不存在，跳过：" + material_path)


def build_polygon_layer(layer_name, data, config):
    actor_name = config["actor_name"]
    z_cm = float(config.get("z_cm", 0.0))
    height_cm = float(config.get("height_cm", 1.0))

    destroy_actor_by_label(actor_name)

    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    actor = subsystem.spawn_actor_from_class(
        unreal.DynamicMeshActor,
        unreal.Vector(0.0, 0.0, z_cm),
        unreal.Rotator(0.0, 0.0, 0.0),
    )

    actor.set_actor_label(actor_name)
    folder = config.get("folder")

    if folder:
     actor.set_folder_path(folder)


    component = actor.get_component_by_class(unreal.DynamicMeshComponent)
    dynamic_mesh = component.get_dynamic_mesh()
    dynamic_mesh.reset()

    primitive_options = unreal.GeometryScriptPrimitiveOptions()

    polygon_count = 0

    for rings in iter_polygons(data):
        if not rings:
            continue

        # 当前路口这些图层主要使用外环。
        # 如果以后出现带洞 Polygon，再升级为“外环 + 内洞”的三角剖分方案。
        if len(rings) > 1:
            unreal.log_warning(
                f"{layer_name}: 检测到 Polygon 内洞，当前版本先生成外环。内洞数量={len(rings)-1}"
            )

        outer = remove_closing_duplicate(rings[0])
        outer = remove_consecutive_duplicates(outer)

        if len(outer) < 3:
            unreal.log_warning(f"{layer_name}: 一个 Polygon 顶点少于3，跳过")
            continue

        ue_points = []

        for coord in outer:
            x, y, _ = coord_to_ue_cm(coord, 0.0)
            ue_points.append(unreal.Vector2D(x, y))

        # Geometry Script 要求逆时针
        if signed_area(ue_points) < 0:
            ue_points.reverse()

        unreal.GeometryScript_Primitives.append_simple_extrude_polygon(
            target_mesh=dynamic_mesh,
            primitive_options=primitive_options,
            transform=unreal.Transform(),
            polygon_vertices=ue_points,
            height=height_cm,
            height_steps=0,
            capped=True,
            origin=unreal.GeometryScriptPrimitiveOriginMode.BASE,
        )

        polygon_count += 1

    if polygon_count == 0:
        subsystem.destroy_actor(actor)
        unreal.log_warning(f"{layer_name}: 没找到可生成的 Polygon")
        return None, 0

    # 道路/人行道/箭头等硬表面使用面法线，避免三角面被错误平滑。
    try:
        unreal.GeometryScript_Normals.set_per_face_normals(dynamic_mesh)
    except Exception as exc:
        unreal.log_warning(f"{layer_name}: 法线处理跳过：{exc}")

    try:
        component.notify_mesh_modified()
    except Exception:
        # 某些 UE 版本创建 Mesh 后已经自动刷新
        pass

    apply_material(component, config.get("material"))

    unreal.log(
        f"{layer_name}: Polygon生成完成 | Actor={actor_name} | 数量={polygon_count}"
    )

    return actor, polygon_count
