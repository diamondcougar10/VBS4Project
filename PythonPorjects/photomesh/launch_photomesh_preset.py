"""Prepare and launch PhotoMesh Wizard using a predefined preset."""

from __future__ import annotations

import os, json, shutil, time, threading, xml.etree.ElementTree as ET
import re, subprocess
from typing import List


# Base directory of the repo (PythonPorjects)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# New/updated install paths for Presets + Wizard config
WIZARD_DIR = r"C:\\Program Files\\Skyline\\PhotoMeshWizard"
WIZARD_INSTALL_CFG = rf"{WIZARD_DIR}\config.json"
WIZARD_PRESET_DIR = rf"{WIZARD_DIR}\Presets"

PM_INSTALL_DIR = r"C:\\Program Files\\Skyline\\PhotoMesh"
PM_PRESET_DIR = rf"{PM_INSTALL_DIR}\Presets"

# Our preset file name (do NOT include any weird characters)
PRESET_NAME = "OECPP"
PRESET_FILENAME = f"{PRESET_NAME}.PMPreset"

# Where we store a master copy in the repo (already present)
REPO_PRESET = rf"{BASE_DIR}\photomesh\{PRESET_FILENAME}"

# Your shared fuser UNC (host may vary — keep a formatter)
DEFAULT_FUSER_UNC_FMT = r"\\{host}\SharedMeshDrive\WorkingFuser"
DEFAULT_HOST = "kit1-1"

# Launchable Wizard EXE
WIZARD_EXE = rf"{WIZARD_DIR}\WizardGUI.exe"


def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def _load_json_safe(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json_safe(path: str, obj: dict) -> None:
    _ensure_dir(os.path.dirname(path))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


# Sanitize preset XML and enforce OBJ-only + pivot/ellipsoid
ARR = "http://schemas.microsoft.com/2003/10/Serialization/Arrays"
ET.register_namespace("d3p1", ARR)


def _strip_illegal_xmlns(raw: str) -> str:
    raw = re.sub(r"\sxmlns:[A-Za-z_][\w\-.]*=\"(?:xml|xmlns)\"", "", raw)
    raw = re.sub(r"\sxmlns=\"(?:xml|xmlns)\"", "", raw)
    return raw


def repair_and_normalize_preset(preset_path: str, preset_name: str = PRESET_NAME) -> None:
    try:
        with open(preset_path, "r", encoding="utf-8", errors="ignore") as f:
            cleaned = _strip_illegal_xmlns(f.read())
        tree = ET.ElementTree(ET.fromstring(cleaned))
    except Exception:
        root = ET.Element("BuildParametersPreset")
        tree = ET.ElementTree(root)

    root = tree.getroot()
    bp = root.find("./BuildParameters") or ET.SubElement(root, "BuildParameters")

    # Ensure OutputFormats = [OBJ]
    ofs = bp.find("./OutputFormats") or ET.SubElement(bp, "OutputFormats")
    for c in list(ofs):
        ofs.remove(c)
    ET.SubElement(ofs, f"{{{ARR}}}string").text = "OBJ"

    # Set center pivot + ellipsoid reprojection
    for tag in ("CenterModelsToProject", "CesiumReprojectZ"):
        n = bp.find(tag) or ET.SubElement(bp, tag)
        n.text = "true"

    # Make it the default/last used for good measure
    for tag in ("IsDefault", "IsLastUsed"):
        n = root.find(tag) or ET.SubElement(root, tag)
        n.text = "true"

    pn = root.find("PresetName") or ET.SubElement(root, "PresetName")
    pn.text = preset_name

    tmp = preset_path + ".tmp"
    tree.write(tmp, encoding="utf-8", xml_declaration=True)
    os.replace(tmp, preset_path)


def _try_copy_preset(src: str, dst_dir: str) -> bool:
    try:
        _ensure_dir(dst_dir)
        dst = os.path.join(dst_dir, PRESET_FILENAME)
        shutil.copy2(src, dst)
        repair_and_normalize_preset(dst)
        return True
    except PermissionError:
        return False


def install_presets_to_program_files(repo_src: str = REPO_PRESET) -> None:
    # PhotoMeshWizard\Presets
    ok1 = _try_copy_preset(repo_src, WIZARD_PRESET_DIR)
    # PhotoMesh\Presets
    ok2 = _try_copy_preset(repo_src, PM_PRESET_DIR)

    # If not admin, at least ensure per-user preset exists (Wizard also reads user roaming)
    if not (ok1 and ok2):
        user_dir = os.path.expandvars(r"%APPDATA%\\Skyline\\PhotoMesh\\Presets")
        _try_copy_preset(repo_src, user_dir)


def _wizard_write_defaults(host: str = DEFAULT_HOST) -> None:
    cfg = _load_json_safe(WIZARD_INSTALL_CFG)

    # keep nice runtime defaults (minimized, low-priority optional)
    cfg.setdefault("UseMinimize", True)
    cfg.setdefault("ClosePMWhenDone", False)
    cfg.setdefault("UseLowPriorityPM", False)

    # Default UI seeds — safe for launch
    ui = cfg.setdefault("DefaultPhotoMeshWizardUI", {})
    outs = ui.setdefault("OutputProducts", {})
    outs["3DModel"] = True
    outs["Model3D"] = True
    outs["Ortho"] = True  # lets the Wizard happily kick off; preset controls real output

    m3d = ui.setdefault("Model3DFormats", {})
    # don't force 3DML on; leave formats neutral in UI — preset will choose OBJ
    for k, v in list(m3d.items()):
        if isinstance(v, bool):
            m3d[k] = False
    m3d.setdefault("OBJ", True)

    # Fuser UNC
    network = cfg.setdefault("NetworkWorkingFolder", {})
    network["UNC"] = DEFAULT_FUSER_UNC_FMT.format(host=host)

    _save_json_safe(WIZARD_INSTALL_CFG, cfg)


def prepare_presets_and_wizard_defaults(host: str = DEFAULT_HOST) -> None:
    install_presets_to_program_files()
    _wizard_write_defaults(host=host)


def launch_wizard_with_preset(
    project_name: str,
    project_path: str,
    folders: List[str],
    host: str = DEFAULT_HOST,
):
    """Launch PhotoMesh Wizard with our preset and autostart flags."""

    # prep presets + defaults
    prepare_presets_and_wizard_defaults(host=host)

    # Build args — preset + override + autostart (Wizard 1.5+)
    args = [
        WIZARD_EXE,
        "--projectName",
        project_name,
        "--projectPath",
        project_path,
        "--preset",
        PRESET_NAME,
        "--overrideSettings",
        "--autostart",
    ]
    for fld in folders or []:
        args += ["--folder", fld]

    # No messagebox confirmations; just launch
    return subprocess.Popen(args, cwd=WIZARD_DIR)


__all__ = ["launch_wizard_with_preset", "prepare_presets_and_wizard_defaults"]

