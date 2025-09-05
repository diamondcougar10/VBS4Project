# =============================================================================
# Project: VBS4Project
# File: update_photomesh_config.py
# Purpose: Apply minimal defaults to PhotoMesh Wizard config
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
CONFIG_CANDIDATES = [
    r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard\\config.json",
    r"C:\\Program Files\\Skyline\\PhotoMeshWizard\\config.json",
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
def update_config(path: str) -> None:
    """Enable 3D model OBJ and 3DML flags in install-level Wizard config."""
    try:
        config = _load_config(path)
    except FileNotFoundError:
        print(f"❌ File not found: {path}")
        return
    except PermissionError as exc:
        print(f"❌ Permission denied reading file: {exc}")
        return
    except json.JSONDecodeError as exc:
        print(f"❌ Failed to parse JSON: {exc}")
        return

    ui = config.setdefault("DefaultPhotoMeshWizardUI", {})
    ui.setdefault("OutputProducts", {}).update({"Model3D": True})
    fmts = ui.setdefault("Model3DFormats", {})
    fmts["3DML"] = True
    fmts["OBJ"] = True
    # Optional:
    # fmts["LAS"] = True

    config["NetworkWorkingFolder"] = resolve_network_working_folder_from_cfg(
        get_offline_cfg()
    )

    try:
        _save_config(path, config)
        print("✅ config.json updated successfully.")
    except PermissionError as exc:
        print(f"❌ Permission denied writing file: {exc}")
        print("Please run this script as Administrator.")
    except Exception as exc:
        print(f"❌ Failed to update config: {exc}")
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
    for path in CONFIG_CANDIDATES:
        if os.path.isfile(path):
            update_config(path)
            any_ok = True
    if not any_ok:
        print("❌ PhotoMesh Wizard config.json not found in expected locations.")
        print(
            "   Please install Skyline PhotoMesh/Wizard or run the Toolkit once to cache the path."
        )


if __name__ == "__main__":
    main()
# endregion

# =============================================================================
# Refactor Notes
# - Added atomic config read/write helpers.
# - Structured file with explicit sections and docstrings.
# =============================================================================

