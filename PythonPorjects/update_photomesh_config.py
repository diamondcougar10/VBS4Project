# =============================================================================
# Project: VBS4Project
# File: update_photomesh_config.py
# Purpose: Enforce OBJ-only defaults and WorkingFuser UNC in Wizard config
# =============================================================================
# Table of Contents
#   1) Imports
#   2) Constants & Configuration
#   3) Paths & Environment
#   4) Data Models / Types (if any)
#   5) Utilities (pure helpers, no I/O)
#   6) File I/O & JSON helpers
#   7) Wizard Config (read/patch install config)
#   8) Network / UNC resolution
#   9) Launch / CLI argument builders
#  10) GUI / Tkinter handlers
#  11) Logging & Error handling
#  12) Main entry point
# =============================================================================

# region Imports
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from STE_Toolkit import build_unc_from_cfg, get_offline_cfg
from photomesh_launcher import (
    resolve_network_working_folder_from_cfg,
    _load_json,
    _save_json,
)
# endregion

# region Constants & Configuration
# PhotoMesh Wizard install config (read by Wizard at startup)
CONFIGS = [
    r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard\\config.json",
    r"C:\\Program Files\\Skyline\\PhotoMeshWizard\\config.json",
    r"C:\\Program Files (x86)\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard\\config.json",
    r"C:\\Program Files (x86)\\Skyline\\PhotoMeshWizard\\config.json",
]
# endregion

# region Paths & Environment
# No additional environment paths required.
# endregion

# region Data Models / Types
# endregion

# region Utilities
# endregion

# region File I/O & JSON helpers
# Shared via photomesh_launcher._load_json/_save_json
# endregion

# region Wizard Config
def update_config(path: str) -> bool:
    """Force OBJ-only defaults and update NetworkWorkingFolder for Wizard 1.5.1."""
    if not os.path.isfile(path):
        return False

    cfg = _load_json(path) or {}

    ui = cfg.setdefault("DefaultPhotoMeshWizardUI", {})
    ui.setdefault("OutputProducts", {}).update({"Model3D": True})
    fmts = ui.setdefault("Model3DFormats", {})
    fmts["OBJ"] = True
    fmts["3DML"] = False
    fmts["SLPK"] = False
    ui.setdefault("VerticalDatum", "Ellipsoid")

    offline = get_offline_cfg()
    root_unc = build_unc_from_cfg(offline)
    wf_unc = ""
    if root_unc:
        subdir = (offline.get("working_fuser_subdir") or "WorkingFuser").strip() or "WorkingFuser"
        wf_unc = os.path.join(root_unc, subdir).replace("/", "\\")
    else:
        try:
            wf_unc = resolve_network_working_folder_from_cfg(offline)
        except Exception:
            wf_unc = ""

    if wf_unc:
        cfg["NetworkWorkingFolder"] = wf_unc

    if root_unc:
        projects_unc = os.path.join(root_unc, "Projects").replace("/", "\\")
        for key in ("ProjectsRoot", "ProjectsRootFolder", "ProjectsRootPath"):
            if key in cfg:
                cfg[key] = projects_unc
        paths = cfg.get("Paths")
        if isinstance(paths, dict):
            for key in ("ProjectsRoot", "ProjectRoot", "ProjectsFolder"):
                if key in paths:
                    paths[key] = projects_unc

    host_ip = (offline.get("host_ip") or "").strip()
    host_name = (offline.get("host_name") or "").strip()

    def _rewrite(value):
        if isinstance(value, dict):
            return {k: _rewrite(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_rewrite(v) for v in value]
        if isinstance(value, str) and host_ip:
            newv = value.replace("{host}", host_ip)
            if host_name:
                newv = newv.replace(f"\\\\{host_name}\\", f"\\\\{host_ip}\\")
                newv = newv.replace(f"//{host_name}/", f"//{host_ip}/")
            return newv
        return value

    cfg = _rewrite(cfg)

    try:
        _save_json(path, cfg)
    except PermissionError as exc:
        print(f"[Wizard 1.5.1] Permission denied writing {path}: {exc}")
        print("Run this updater as Administrator.")
        return False
    except Exception as exc:
        print(f"[Wizard 1.5.1] Failed updating {path}: {exc}")
        return False

    print(f"[Wizard 1.5.1] Updated -> {path}")
    return True
# endregion

# region Network / UNC resolution
# endregion

# region Launch / CLI argument builders
# endregion

# region GUI / Tkinter handlers
# endregion

# region Logging & Error handling
# endregion

# region Main entry point
def main() -> None:
    any_ok = False
    for path in CONFIGS:
        if not os.path.isfile(path):
            continue
        if update_config(path):
            any_ok = True
    if not any_ok:
        print("No PhotoMesh Wizard config.json found in standard locations.")


if __name__ == "__main__":
    main()
# endregion

# =============================================================================
# Refactor Notes
# - Added atomic config read/write helpers.
# - Structured file with explicit sections and docstrings.
# =============================================================================

