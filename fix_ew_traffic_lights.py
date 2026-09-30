# -*- coding: utf-8 -*-
"""Execute in the current Unreal Editor: correct only 6 east/west pole lights.

Fixed target angles make repeated execution harmless. Location, scale, pitch,
roll, visibility, other actors, source assets and source data stay unchanged.
Scene changes can be undone together with Ctrl+Z. The level is not auto-saved.
API: https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/Actor?application_version=5.4
"""
from pathlib import Path
import unreal

TARGETS = {
    "AUTO_TL_FAC-001_东": -70.0,
    "AUTO_TL_FAC-002_东": -70.0,
    "AUTO_TL_FAC-007_西": 110.0,
    "AUTO_TL_FAC-008_西": 110.0,
    "AUTO_TL_FAC-009_西": 110.0,
    "AUTO_TL_FAC-010_东": -70.0,
}


def main():
    project_file = Path(unreal.Paths.get_project_file_path())
    if project_file.name.casefold() != "路口0902.uproject".casefold():
        raise RuntimeError("Please open 路口0902.uproject before running this one-off repair script")
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    matches = {label: [] for label in TARGETS}
    for actor in subsystem.get_all_level_actors():
        label = actor.get_actor_label()
        if label in matches and actor.get_class().get_name() == "BP_TrafficLight_01_C":
            matches[label].append(actor)
    duplicates = [label for label, actors in matches.items() if len(actors) > 1]
    if duplicates:
        raise RuntimeError("Duplicate labels; no changes made: " + ", ".join(duplicates))
    changed = unchanged = missing = 0
    with unreal.ScopedEditorTransaction("Fix east/west pole traffic light yaw"):
        for label, yaw in TARGETS.items():
            if not matches[label]:
                missing += 1
                unreal.log_warning("[EW_FIX] Missing actor: " + label)
                continue
            actor = matches[label][0]
            rotation = actor.get_actor_rotation()
            delta = (rotation.yaw - yaw + 180.0) % 360.0 - 180.0
            if abs(delta) < 0.01:
                unchanged += 1
                continue
            actor.modify()
            if not actor.set_actor_rotation(unreal.Rotator(pitch=rotation.pitch, yaw=yaw, roll=rotation.roll), False):
                raise RuntimeError("Could not rotate " + label + "; use Ctrl+Z to undo this batch")
            changed += 1
            unreal.log("[EW_FIX] {}: {:.1f} -> {:.1f}".format(label, rotation.yaw, yaw))
    unreal.log_warning("[EW_FIX] changed={}, already_correct={}, missing={}. North/south lights unchanged. Inspect then save.".format(changed, unchanged, missing))


if __name__ == "__main__":
    main()
