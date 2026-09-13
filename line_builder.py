# -*- coding: utf-8 -*-
"""
LineString / MultiLineString -> 带状 Dynamic Mesh。

适合当前：
- marking 标线

以后：
- guardrail 不建议直接用这个作为最终护栏，
  应改成沿线实例化 Blender/UE 护栏资产。
"""

import unreal

from coordinate_utils import coord_to_ue_cm
from geojson_utils import iter_lines, remove_consecutive_duplicates
from polygon_builder import destroy_actor_by_label, apply_material


def build_line_layer(layer_name, data, config):
    actor_name = config["actor_name"]

    z_cm = float(config.get("z_cm", 0.0))
    width_cm = float(config.get("width_cm", 15.0))
    thickness_cm = float(config.get("thickness_cm", 1.0))

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

    # Sweep 的 2D 截面：
    # U = 左右宽度
    # V = 上下厚度
    half_width = width_cm * 0.5

    profile = [
        unreal.Vector2D(-half_width, 0.0),
        unreal.Vector2D(half_width, 0.0),
        unreal.Vector2D(half_width, thickness_cm),
        unreal.Vector2D(-half_width, thickness_cm),
    ]

    line_count = 0

    for raw_line in iter_lines(data):
        raw_line = remove_consecutive_duplicates(raw_line)

        if len(raw_line) < 2:
            continue

        sweep_path = []

        for coord in raw_line:
            x, y, _ = coord_to_ue_cm(coord, 0.0)
            sweep_path.append(unreal.Vector(x, y, 0.0))

        unreal.GeometryScript_Primitives.append_simple_swept_polygon(
            target_mesh=dynamic_mesh,
            primitive_options=primitive_options,
            transform=unreal.Transform(),
            polygon_vertices=profile,
            sweep_path=sweep_path,
            loop=False,
            capped=True,
            start_scale=1.0,
            end_scale=1.0,
            rotation_angle_deg=0.0,
            miter_limit=4.0,
        )

        line_count += 1

    if line_count == 0:
        subsystem.destroy_actor(actor)
        unreal.log_warning(f"{layer_name}: 没找到可生成的 LineString")
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

    unreal.log(
        f"{layer_name}: Line生成完成 | Actor={actor_name} | 数量={line_count}"
    )

    return actor, line_count
