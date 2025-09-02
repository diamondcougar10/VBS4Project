import os
from typing import Iterable

from photomesh_preset import stage_preset

# === Preset (hard-coded) ===
# Use either the NAME if it's already under a Presets folder, or the absolute file path:
PRESET_INPUT = r"STEPRESET"  # or r"C:\\path\\to\\STEPRESET.PMPreset"
PRESET_NAME_ONLY = stage_preset(PRESET_INPUT)


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
