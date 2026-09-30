# -*- coding: utf-8 -*-
"""Spawn BP_TrafficLight from this project's road_facility.geojson."""
import math
import unreal

from coordinate_utils import coord_to_local_m, coord_to_ue_cm
from geojson_utils import load_geojson
from project_config import (
    DATA_FOLDER, TRAFFIC_LIGHT_BLUEPRINT, TRAFFIC_LIGHT_FOLDER,
    TRAFFIC_LIGHT_Z_CM, TRAFFIC_LIGHT_MODEL_FORWARD_OFFSET_DEG,
    TRAFFIC_LIGHT_MAX_CENTERLINE_DISTANCE_M,
    TRAFFIC_LIGHT_REPLACE_EXISTING,
)


def _iter_segments(data):
    """Yield projected local-meter segments and road metadata."""
    def walk(geometry):
        if not geometry:
            return
        kind = geometry.get("type")
        coords = geometry.get("coordinates", [])
        if kind == "LineString":
            lines = [coords]
        elif kind == "MultiLineString":
            lines = coords
        elif kind == "GeometryCollection":
            for child in geometry.get("geometries", []):
                for item in walk(child):
                    yield item
            return
        else:
            return
        for line in lines:
            for a, b in zip(line, line[1:]):
                ax, ay = coord_to_local_m(a)
                bx, by = coord_to_local_m(b)
                dx, dy = bx - ax, by - ay
                if dx * dx + dy * dy > 1e-12:
                    yield (ax, ay, bx, by, dx, dy)

    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        for segment in walk(feature.get("geometry")):
            yield segment, props


def _nearest_segment(point, segments):
    px, py = point
    best = None
    for segment, props in segments:
        ax, ay, bx, by, dx, dy = segment
        length2 = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
        qx, qy = ax + t * dx, ay + t * dy
        distance = math.hypot(px - qx, py - qy)
        if best is None or distance < best[0]:
            best = (distance, dx, dy, props)
    return best


def _yaws_for_direction(dx, dy, direction):
    """Return actor yaw(s); labels choose the sign of the local road axis."""
    # QGIS local axes are east/north; UE local axes are east/south.
    tangent_yaw = math.degrees(math.atan2(-dy, dx))
    tangent_length = math.hypot(dx, dy)
    ux, uy = dx / tangent_length, dy / tangent_length  # GIS east, north
    aliases = {"東": "东", "東西": "东西"}
    direction = aliases.get((direction or "").strip(), (direction or "").strip())
    if direction in ("东西", "南北"):
        return [tangent_yaw, tangent_yaw + 180.0]
    compass = {"东": (1.0, 0.0), "西": (-1.0, 0.0),
               "北": (0.0, 1.0), "南": (0.0, -1.0)}
    wanted = compass.get(direction)
    if wanted is None:
        return None
    dot = ux * wanted[0] + uy * wanted[1]
    # These labels describe the local traffic axis. If the GIS label is almost
    # perpendicular to the selected line, retain the road axis and warn.
    if abs(dot) < 0.35:
        unreal.log_warning("[FacilityBuilder] direction {!r} is not aligned with nearest centerline; using nearest-axis sign".format(direction))
    yaw = tangent_yaw if dot >= 0.0 else tangent_yaw + 180.0
    return [yaw]


def _find_actor(subsystem, label):
    for actor in subsystem.get_all_level_actors():
        if actor and actor.get_actor_label() == label:
            return actor
    return None


def build_traffic_lights():
    facility_path = DATA_FOLDER / "road_facility.geojson"
    centerline_path = DATA_FOLDER / "road_centerline.geojson"
    facilities = load_geojson(str(facility_path))
    centerlines = load_geojson(str(centerline_path))
    segments = list(_iter_segments(centerlines))
    if not segments:
        raise ValueError("road_centerline.geojson contains no usable line segments")
    blueprint = unreal.EditorAssetLibrary.load_asset(TRAFFIC_LIGHT_BLUEPRINT)
    if not blueprint:
        raise RuntimeError("找不到 BP_TrafficLight：{}".format(TRAFFIC_LIGHT_BLUEPRINT))

    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    created = updated = skipped = 0
    for feature in facilities.get("features", []):
        props = feature.get("properties") or {}
        if (props.get("type") or "").strip() != "红绿灯":
            continue
        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "Point":
            skipped += 1
            continue
        coord = geometry.get("coordinates", [])
        if len(coord) < 2:
            skipped += 1
            continue
        local = coord_to_local_m(coord)
        nearest = _nearest_segment(local, segments)
        if nearest is None or nearest[0] > TRAFFIC_LIGHT_MAX_CENTERLINE_DISTANCE_M:
            unreal.log_warning("[FacilityBuilder] {} has no nearby centerline ({} m)".format(
                props.get("id", props.get("fid")), None if nearest is None else round(nearest[0], 2)))
            skipped += 1
            continue
        yaws = _yaws_for_direction(nearest[1], nearest[2], props.get("direction"))
        if yaws is None:
            unreal.log_warning("[FacilityBuilder] unsupported direction {!r} for {}".format(
                props.get("direction"), props.get("id", props.get("fid"))))
            skipped += 1
            continue
        x, y, _ = coord_to_ue_cm(coord, TRAFFIC_LIGHT_Z_CM)
        feature_id = str(props.get("id") or props.get("fid") or "FAC")
        for index, road_yaw in enumerate(yaws, 1):
            label = "TL_{}{}".format(feature_id.replace("-", "_"), "_{}".format(index) if len(yaws) > 1 else "")
            yaw = road_yaw - TRAFFIC_LIGHT_MODEL_FORWARD_OFFSET_DEG
            rotation = unreal.Rotator(0.0, 0.0, yaw)
            actor = _find_actor(subsystem, label)
            if actor and TRAFFIC_LIGHT_REPLACE_EXISTING:
                subsystem.destroy_actor(actor)
                actor = None
            if actor:
                actor.set_actor_location(unreal.Vector(x, y, TRAFFIC_LIGHT_Z_CM), False, False)
                actor.set_actor_rotation(rotation, False)
                updated += 1
            else:
                actor = subsystem.spawn_actor_from_object(
                    blueprint, unreal.Vector(x, y, TRAFFIC_LIGHT_Z_CM), rotation)
                if not actor:
                    unreal.log_error("[FacilityBuilder] spawn failed: " + label)
                    skipped += 1
                    continue
                actor.set_actor_label(label)
                created += 1
            actor.set_folder_path(TRAFFIC_LIGHT_FOLDER)
            unreal.log("[FacilityBuilder] {} direction={} yaw={:.2f} nearest={:.2f}m road={}".format(
                label, props.get("direction"), yaw, nearest[0], nearest[3].get("road_name", nearest[3].get("road_id", ""))))
    unreal.log_warning("[FacilityBuilder] 完成 | 新建={} 更新={} 跳过={}".format(created, updated, skipped))
    return created, updated, skipped
