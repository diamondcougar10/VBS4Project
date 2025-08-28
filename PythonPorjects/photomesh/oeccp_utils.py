"""Utilities to enforce OECPP preset for PhotoMesh Wizard.

These helpers keep the desired preset and default settings in place for each
user profile.  They perform idempotent operations so running them repeatedly is
safe and protects against Skyline updates overwriting user configuration.

All paths are resolved via the ``APPDATA`` environment variable in order to
mirror Windows behaviour.  Functions gracefully degrade when run on non-Windows
systems or when missing permissions.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List, Optional
import xml.etree.ElementTree as ET

ARR = "http://schemas.microsoft.com/2003/10/Serialization/Arrays"
ET.register_namespace("d2p1", ARR)

# ---------------------------------------------------------------------------
# Preset handling
# ---------------------------------------------------------------------------

def _preset_repo_path(repo_hint: str) -> Optional[Path]:
    """Resolve the OECPP preset path inside the repository.

    ``repo_hint`` may point directly at the preset file.  If it does not exist
    the repository is searched recursively up to a depth of 6 levels.  ``None``
    is returned when the preset cannot be located.
    """
    p = Path(repo_hint)
    if p.is_file():
        return p
    try:
        root = p if p.is_dir() else p.parent
        for _ in range(6):
            matches = list(root.glob("**/OECPP.PMPreset"))
            if matches:
                return matches[0]
            break
    except Exception:
        pass
    return None


def ensure_oeccp_preset_in_appdata(repo_hint: str) -> str:
    """Ensure the OECPP preset exists under ``%APPDATA%``.

    The preset is copied from the repository into the per-user PhotoMesh preset
    directory.  The XML inside the preset is normalised to ensure the preset is
    marked as default, last used and exports OBJ only.
    """
    repo_preset = _preset_repo_path(repo_hint)
    if not repo_preset or not repo_preset.is_file():
        raise FileNotFoundError(f"Preset not found from hint: {repo_hint}")

    appdata = Path(os.environ["APPDATA"])  # may raise KeyError on non-Windows
    dest_dir = appdata / "Skyline" / "PhotoMesh" / "Presets"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "OECPP.PMPreset"
    shutil.copy2(repo_preset, dest)

    tree = ET.parse(dest)
    root = tree.getroot()

    def _set(tag: str, text: str) -> None:
        elem = root.find(tag)
        if elem is None:
            elem = ET.SubElement(root, tag)
        elem.text = text

    _set("PresetName", "OECPP")
    _set("IsDefault", "true")
    _set("IsLastUsed", "true")

    of = root.find("OutputFormats")
    if of is None:
        of = ET.SubElement(root, "OutputFormats")
    # clear existing children
    for child in list(of):
        of.remove(child)
    ET.SubElement(of, f"{{{ARR}}}string").text = "OBJ"

    tree.write(dest, encoding="utf-8", xml_declaration=True)
    return str(dest)


# ---------------------------------------------------------------------------
# Preset settings
# ---------------------------------------------------------------------------

def set_default_preset_in_presetsettings(preset_name: str = "OECPP") -> str:
    """Ensure PresetSettings.xml points to ``preset_name`` as default."""
    appdata = Path(os.environ["APPDATA"])  # raises KeyError on non-Windows
    xml_path = appdata / "Skyline" / "PhotoMesh" / "Presets" / "PresetSettings.xml"
    xml_path.parent.mkdir(parents=True, exist_ok=True)

    if xml_path.exists():
        tree = ET.parse(xml_path)
        root = tree.getroot()
    else:
        root = ET.Element("PresetSettings")
        tree = ET.ElementTree(root)

    dn = root.find(".//DefaultPresetNames")
    if dn is None:
        dn = ET.SubElement(root, "DefaultPresetNames")

    # clear existing children and add the required default using namespace
    for child in list(dn):
        dn.remove(child)
    ET.SubElement(dn, f"{{{ARR}}}string").text = preset_name

    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    return str(xml_path)


# ---------------------------------------------------------------------------
# Wizard user configuration
# ---------------------------------------------------------------------------

def set_user_wizard_defaults(preset: str = "OECPP", autostart: bool = True) -> str:
    """Write the user-level wizard configuration."""
    appdata = Path(os.environ["APPDATA"])  # raises KeyError on non-Windows
    cfg_path = appdata / "Skyline" / "PhotoMesh" / "Wizard" / "config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    data = {}
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    data.update(
        {
            "OverrideSettings": True,
            "AutoBuild": bool(autostart),
            "SelectedPreset": preset,
            "DefaultPresetName": preset,
        }
    )
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return str(cfg_path)


# ---------------------------------------------------------------------------
# Install-level configuration (optional)
# ---------------------------------------------------------------------------

def enforce_install_cfg_obj_only() -> Optional[str]:
    """Best-effort enforcement of OBJ-only defaults at install level.

    If the configuration file cannot be written (e.g. due to lack of admin
    privileges) the function silently returns ``None``.
    """
    cfg = Path(r"C:\Program Files\Skyline\PhotoMesh\Tools\PhotomeshWizard\config.json")
    if not cfg.exists():
        return None
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

    ui = data.setdefault("DefaultPhotoMeshWizardUI", {})
    outputs = ui.setdefault("OutputProducts", {})
    outputs["3DModel"] = True
    outputs["Ortho"] = False

    m3d = ui.setdefault("Model3DFormats", {})
    for k in list(m3d.keys()):
        m3d[k] = False
    m3d["OBJ"] = True
    m3d["3DML"] = False

    ui["CenterPivotToProject"] = True
    ui["ReprojectToEllipsoid"] = True

    try:
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return str(cfg)
    except PermissionError:
        return None


# ---------------------------------------------------------------------------
# Wizard launching
# ---------------------------------------------------------------------------

def find_wizard_exe() -> Optional[str]:
    """Locate the PhotoMesh Wizard executable in the default install path."""
    base = Path(r"C:\Program Files\Skyline\PhotoMesh\Tools\PhotomeshWizard")
    for exe in ("PhotoMeshWizard.exe", "WizardGUI.exe"):
        p = base / exe
        if p.exists():
            return str(p)
    return None


def launch_wizard_with_preset(
    project_name: str,
    project_path: str,
    folders: Iterable[str],
    preset: str = "OECPP",
) -> subprocess.Popen:
    """Launch PhotoMesh Wizard with the given preset and imagery folders."""
    exe = find_wizard_exe()
    if not exe:
        raise FileNotFoundError("PhotoMeshWizard executable not found")

    args: List[str] = [
        exe,
        "--projectName",
        project_name,
        "--projectPath",
        project_path,
        "--overrideSettings",
        "--preset",
        preset,
    ]
    for folder in folders:
        args.extend(["--folder", folder])

    return subprocess.Popen(args, cwd=os.path.dirname(exe))


# ---------------------------------------------------------------------------
# Verification helper
# ---------------------------------------------------------------------------

def verify_effective_settings(log=print) -> None:
    """Read key configuration files and log effective values."""
    appdata = Path(os.environ.get("APPDATA", ""))
    preset_path = appdata / "Skyline" / "PhotoMesh" / "Presets" / "OECPP.PMPreset"
    preset_xml = None
    if preset_path.exists():
        try:
            preset_xml = ET.parse(preset_path).getroot()
        except Exception:
            preset_xml = None

    preset_settings = appdata / "Skyline" / "PhotoMesh" / "Presets" / "PresetSettings.xml"
    wizard_cfg = appdata / "Skyline" / "PhotoMesh" / "Wizard" / "config.json"

    if preset_xml is not None:
        of = [e.text for e in preset_xml.findall("OutputFormats/*")]
        log(f"Preset OutputFormats: {of}")
        log(f"IsDefault: {preset_xml.findtext('IsDefault')}")
        log(f"CenterPivotToProject: {preset_xml.findtext('CenterPivotToProject')}" )
    log(f"PresetSettings.xml exists: {preset_settings.exists()}")
    log(f"Wizard config exists: {wizard_cfg.exists()}")
