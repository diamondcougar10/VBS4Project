"""Utility functions for preparing and launching PhotoMesh Wizard.

This module makes sure the custom ``OECPP`` preset is available for the
current user and that PhotoMesh defaults to OBJ output only.  The functions are
idempotent and safe to call on every run so new user profiles or Skyline
updates do not break the desired behaviour.

Typical usage::

    ensure_oeccp_preset_in_appdata(repo_hint)
    set_default_preset_in_presetsettings()
    set_user_wizard_defaults()
    enforce_install_cfg_obj_only()  # best effort, requires admin
    launch_wizard_with_preset(name, path, folders)

"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import logging
import xml.etree.ElementTree as ET
from typing import Callable, List

PRESET_NAME = "OECPP"
PRESET_FILENAME = f"{PRESET_NAME}.PMPreset"

# common paths ---------------------------------------------------------------

ARR = "http://schemas.microsoft.com/2003/10/Serialization/Arrays"
XMLNS = "http://www.w3.org/2000/xmlns/"

PROGRAM_FILES = os.getenv("ProgramFiles", r"C:\\Program Files")
WIZARD_DIR = os.path.join(
    PROGRAM_FILES, "Skyline", "PhotoMesh", "Tools", "PhotomeshWizard"
)
INSTALL_CFG = os.path.join(WIZARD_DIR, "config.json")

APPDATA = os.getenv("APPDATA") or os.path.join(
    os.path.expanduser("~"), "AppData", "Roaming"
)
USER_PRESET_DIR = os.path.join(APPDATA, "Skyline", "PhotoMesh", "Presets")
USER_PRESET_PATH = os.path.join(USER_PRESET_DIR, PRESET_FILENAME)
USER_PRESET_SETTINGS = os.path.join(USER_PRESET_DIR, "PresetSettings.xml")
USER_CFG = os.path.join(APPDATA, "Skyline", "PhotoMesh", "Wizard", "config.json")


# helpers -------------------------------------------------------------------

def _is_admin() -> bool:
    """Return ``True`` if the process has administrative rights."""

    if os.name == "nt":
        try:  # pragma: no cover - platform specific
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return os.geteuid() == 0


def _find_file_recursive(start_dir: str, filename: str, max_depth: int = 6) -> str | None:
    """Search for *filename* under *start_dir* up to *max_depth* levels."""

    start_dir = os.path.abspath(start_dir)
    for root, dirs, files in os.walk(start_dir):
        depth = root[len(start_dir) :].count(os.sep)
        if filename in files:
            return os.path.join(root, filename)
        if depth >= max_depth:
            dirs[:] = []
    return None


def _load_json(path: str) -> dict:
    """Load JSON from *path*, returning an empty dict on failure."""

    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


# core functionality ---------------------------------------------------------

def ensure_oeccp_preset_in_appdata(repo_hint: str) -> str:
    """Copy and sanitise the ``OECPP`` preset into the user's AppData.

    The preset is located using *repo_hint* or by searching recursively up to
    six levels deep.  It is copied to ``%APPDATA%\\Skyline\\PhotoMesh\\Presets``
    and then adjusted so it is marked as default, last used and outputs OBJ
    only.

    Returns the full path to the copied preset.
    """

    repo_hint = os.path.abspath(repo_hint)
    preset_src = (
        repo_hint
        if os.path.isfile(repo_hint)
        else _find_file_recursive(os.path.dirname(repo_hint), PRESET_FILENAME)
    )
    if not preset_src:
        raise FileNotFoundError(
            f"Preset {PRESET_FILENAME} not found starting from {repo_hint}"
        )

    os.makedirs(USER_PRESET_DIR, exist_ok=True)
    shutil.copy2(preset_src, USER_PRESET_PATH)

    # adjust XML inside the preset
    try:
        tree = ET.parse(USER_PRESET_PATH)
        root = tree.getroot()
    except Exception:
        root = ET.Element("BuildParametersPreset")
        tree = ET.ElementTree(root)

    # ensure expected fields
    for tag in ("IsDefault", "IsLastUsed"):
        elem = root.find(tag)
        if elem is None:
            elem = ET.SubElement(root, tag)
        elem.text = "true"

    name = root.find("PresetName")
    if name is None:
        name = ET.SubElement(root, "PresetName")
    name.text = PRESET_NAME

    bp = root.find("BuildParameters")
    if bp is None:
        bp = ET.SubElement(root, "BuildParameters")
    out = bp.find("OutputFormats")
    if out is None:
        out = ET.SubElement(bp, "OutputFormats")
    out.attrib.clear()
    out.set(f"{{{XMLNS}}}d3p1", ARR)
    for child in list(out):
        out.remove(child)
    ET.SubElement(out, f"{{{ARR}}}string").text = "OBJ"

    ET.register_namespace("d3p1", ARR)
    tree.write(USER_PRESET_PATH, encoding="utf-8", xml_declaration=True)
    return USER_PRESET_PATH


def set_default_preset_in_presetsettings(preset_name: str = PRESET_NAME) -> None:
    """Ensure ``PresetSettings.xml`` points to *preset_name* as default."""

    os.makedirs(USER_PRESET_DIR, exist_ok=True)
    if os.path.isfile(USER_PRESET_SETTINGS):
        try:
            tree = ET.parse(USER_PRESET_SETTINGS)
            root = tree.getroot()
        except Exception:
            root = ET.Element("PresetSettings")
            tree = ET.ElementTree(root)
    else:
        root = ET.Element("PresetSettings")
        tree = ET.ElementTree(root)

    dn = root.find("DefaultPresetNames")
    if dn is None:
        dn = ET.SubElement(root, "DefaultPresetNames")
    for child in list(dn):
        dn.remove(child)
    ET.SubElement(dn, f"{{{ARR}}}string").text = preset_name

    ET.register_namespace("d2p1", ARR)
    tree.write(USER_PRESET_SETTINGS, encoding="utf-8", xml_declaration=True)


def set_user_wizard_defaults(preset: str = PRESET_NAME, autostart: bool = True) -> None:
    """Write wizard ``config.json`` with our desired defaults."""

    cfg = _load_json(USER_CFG)
    cfg.update(
        {
            "OverrideSettings": True,
            "AutoBuild": bool(autostart),
            "SelectedPreset": preset,
            "DefaultPresetName": preset,
        }
    )
    _save_json(USER_CFG, cfg)


def enforce_install_cfg_obj_only() -> bool:
    """Best-effort enforcement of OBJ-only output in the install config.

    Returns ``True`` if the configuration file was written.  The function
    silently skips when not running with administrative privileges or when the
    install configuration file is missing.
    """

    if not _is_admin() or not os.path.isfile(INSTALL_CFG):
        return False

    cfg = _load_json(INSTALL_CFG)
    ui = cfg.setdefault("DefaultPhotoMeshWizardUI", {})
    outputs = ui.setdefault("OutputProducts", {})
    outputs["3DModel"] = True
    outputs["Ortho"] = False
    m3d = ui.setdefault("Model3DFormats", {})
    for key in list(m3d.keys()):
        if isinstance(m3d[key], bool):
            m3d[key] = False
    m3d["OBJ"] = True
    m3d["3DML"] = False
    ui["CenterPivotToProject"] = True
    ui["ReprojectToEllipsoid"] = True

    try:
        _save_json(INSTALL_CFG, cfg)
        return True
    except Exception:  # pragma: no cover - disk write failure
        return False


def find_wizard_exe() -> str:
    """Return full path to the PhotoMesh Wizard executable."""

    for name in ("PhotoMeshWizard.exe", "WizardGUI.exe"):
        path = os.path.join(WIZARD_DIR, name)
        if os.path.isfile(path):
            return path
    raise FileNotFoundError("PhotoMesh Wizard executable not found")


def launch_wizard_with_preset(
    project_name: str,
    project_path: str,
    folders: List[str],
    preset: str = PRESET_NAME,
) -> subprocess.Popen:
    """Launch the PhotoMesh Wizard with the supplied preset and folders."""

    exe = find_wizard_exe()
    args = [
        exe,
        "--projectName",
        project_name,
        "--projectPath",
        project_path,
        "--overrideSettings",
        "--preset",
        preset,
    ]
    for fld in folders:
        args += ["--folder", fld]
    return subprocess.Popen(args, cwd=os.path.dirname(exe))


def verify_effective_settings(log: Callable[[str], None] = print) -> None:
    """Log resolved values from the preset, user and install configs."""

    # Preset details ---------------------------------------------------------
    try:
        tree = ET.parse(USER_PRESET_PATH)
        bp = tree.getroot().find("BuildParameters")
        outputs = []
        if bp is not None:
            out = bp.find("OutputFormats")
            if out is not None:
                outputs = [child.text for child in out]
        log(f"Preset OutputFormats: {outputs}")
    except Exception:
        log("Preset OutputFormats: <error>")

    # PresetSettings ---------------------------------------------------------
    try:
        ps_tree = ET.parse(USER_PRESET_SETTINGS)
        dn = ps_tree.getroot().find("DefaultPresetNames")
        names = [child.text for child in dn] if dn is not None else []
        log(f"PresetSettings DefaultPresetNames: {names}")
    except Exception:
        log("PresetSettings DefaultPresetNames: <error>")

    # Install config ---------------------------------------------------------
    install = _load_json(INSTALL_CFG)
    ui = install.get("DefaultPhotoMeshWizardUI", {})
    outputs = ui.get("OutputProducts", {})
    formats = ui.get("Model3DFormats", {})
    log(
        "Install OutputProducts: 3DModel={0} Ortho={1}".format(
            outputs.get("3DModel"), outputs.get("Ortho")
        )
    )
    log(
        "Install Model3DFormats: OBJ={0} 3DML={1}".format(
            formats.get("OBJ"), formats.get("3DML")
        )
    )
    log(
        "Install CenterPivotToProject={0} ReprojectToEllipsoid={1}".format(
            ui.get("CenterPivotToProject"), ui.get("ReprojectToEllipsoid")
        )
    )

    # User config ------------------------------------------------------------
    user = _load_json(USER_CFG)
    log(
        "UserConfig: AutoBuild={0} SelectedPreset={1} DefaultPresetName={2}".format(
            user.get("AutoBuild"),
            user.get("SelectedPreset"),
            user.get("DefaultPresetName"),
        )
    )

