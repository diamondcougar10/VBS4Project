import os
from typing import Iterable

from photomesh_preset import stage_preset


def build_queue_payload(
    project_name: str,
    project_path: str,
    image_folders: Iterable[str],
    config,
    preset_name: str | None = None,
) -> list[dict]:
    api = config.get("PhotoMeshAPI", {})
    desired = (preset_name or api.get("preset") or "OECPP").strip()
    enforce_obj_only = bool(api.get("enforce_obj_only", True))
    preset_name_only = stage_preset(desired, enforce_obj_only=enforce_obj_only)

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
            "preset": preset_name_only,
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
