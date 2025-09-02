import os
from typing import Iterable

from photomesh_preset import stage_preset

# === Preset (hard-coded) ===
# Use either a preset name ("OECPP") or a full .PMPreset path from the repo.
PRESET_INPUT = r"C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\photomesh\OECPP.PMPreset"  # or "OECPP"
ENFORCE_OBJ_ONLY = True  # keep OBJ-only + center/ellipsoid on

PRESET_NAME_ONLY = stage_preset(PRESET_INPUT, enforce_obj_only=ENFORCE_OBJ_ONLY)


def build_queue_payload(
    project_name: str,
    project_path: str,
    image_folders: Iterable[str],
    config,
) -> list[dict]:
    api = config.get("PhotoMeshAPI", {})
    working = api.get("working_fuser_unc", "")
    max_local = int(api.get("max_local_fusers", 4))

    src: list[dict] = []
    for f in image_folders:
        if f and os.path.isdir(f):
            src.append({"name": os.path.basename(f), "path": f, "properties": ""})
    if not src:
        raise ValueError("No valid imagery folders")

    return [
        {
            "comment": f"{project_name}",
            "action": 0,
            "projectPath": project_path,
            "buildFrom": 1,
            "buildUntil": 6,
            "inheritBuild": "",
            "preset": PRESET_NAME_ONLY,  # <- NAME ONLY, no extension
            "workingFolder": working,
            "MaxLocalFusers": max_local,
            "MaxAWSFusers": 0,
            "AWSFuserStartupScript": "",
            "AWSBuildConfigurationName": "",
            "AWSBuildConfigurationJsonPath": "",
            "sourceType": 0,
            "sourcePath": src,
        }
    ]


__all__ = ["build_queue_payload"]
