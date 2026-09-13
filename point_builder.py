# -*- coding: utf-8 -*-
"""
Point / MultiPoint -> UE 定位标记。

当前 road_facility 先生成小球 Locator，只验证设施点位。
以后有红绿灯、摄像头、标牌等资产后，
这里改成“按属性选择 Static Mesh 并实例化”。
"""

import unreal

from coordinate_utils import coord_to_ue_cm
from geojson_utils import iter_points
from polygon_builder import destroy_actor_by_label, apply_material


def build_point_layer(layer_name, data, config):
    actor_name = config["actor_name"]

    actor_z_cm = float(config.get("z_cm", 0.0))
    radius_cm = float(config.get("marker_radius_cm", 20.0))

    destroy_actor_by_label(actor_name)

    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    actor = subsystem.spawn_actor_from_class(
        unreal.DynamicMeshActor,
        unreal.Vector(0.0, 0.0, actor_z_cm),
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

    point_count = 0

    for coord in iter_points(data):
        x, y, _ = coord_to_ue_cm(coord, 0.0)

        transform = unreal.Transform(
            location=unreal.Vector(x, y, 0.0)
        )

        unreal.GeometryScript_Primitives.append_sphere_lat_long(
            target_mesh=dynamic_mesh,
            primitive_options=primitive_options,
            transform=transform,
            radius=radius_cm,
            steps_phi=8,
            steps_theta=12,
            origin=unreal.GeometryScriptPrimitiveOriginMode.CENTER,
        )

        point_count += 1

    if point_count == 0:
        subsystem.destroy_actor(actor)
        unreal.log_warning(f"{layer_name}: 没找到可生成的 Point")
        return None, 0

    try:
        component.notify_mesh_modified()
    except Exception:
        pass

    apply_material(component, config.get("material"))

    unreal.log(
        f"{layer_name}: Point Locator生成完成 | Actor={actor_name} | 数量={point_count}"
    )

    return actor, point_count
