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
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from photomesh_launcher import (
    get_offline_cfg,
    resolve_network_working_folder_from_cfg,
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
def _load_config(path: str) -> dict:
    """Load JSON configuration from *path*."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_config(path: str, config: dict) -> None:
    """Write JSON *config* to *path* atomically."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
    os.replace(tmp, path)
# endregion

# region Wizard Config
def update_config(path: str) -> bool:
    """Force OBJ-only defaults and update NetworkWorkingFolder for Wizard 1.5.1."""
    try:
        config = _load_config(path)
    except FileNotFoundError:
        return False
    except PermissionError as exc:
        print(f"[Wizard 1.5.1] Permission denied reading {path}: {exc}")
        print("Run this updater as Administrator.")
        return False
    except json.JSONDecodeError as exc:
        print(f"[Wizard 1.5.1] Failed to parse {path}: {exc}")
        return False

    ui = config.setdefault("DefaultPhotoMeshWizardUI", {})
    ui.setdefault("OutputProducts", {}).update({"Model3D": True})
    fmts = ui.setdefault("Model3DFormats", {})
    fmts["OBJ"] = True
    fmts["3DML"] = False
    fmts["SLPK"] = False
    ui.setdefault("VerticalDatum", "Ellipsoid")

    try:
        config["NetworkWorkingFolder"] = resolve_network_working_folder_from_cfg(
            get_offline_cfg()
        )
    except Exception:
        pass

    try:
        _save_config(path, config)
    except PermissionError:
        print(
            f"[Wizard 1.5.1] Permission denied writing {path}. Run as Administrator."
        )
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

