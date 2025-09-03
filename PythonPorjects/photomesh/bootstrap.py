"""PhotoMesh preset staging and autostart utilities.

This module installs a preset into the PhotoMesh application directory,
forces OBJ-only output with project-centred models and ellipsoid reproject,
and launches the PhotoMesh Wizard with ``--autostart``.

The functions are intentionally light-weight so they can be used from both
command line tools and GUI applications.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

ARR = "http://schemas.microsoft.com/2003/10/Serialization/Arrays"
ET.register_namespace("d3p1", ARR)


def _strip_illegal_xmlns(raw: str) -> str:
    """Remove XML namespace declarations that confuse ``ElementTree``."""

    raw = re.sub(r"\sxmlns:[A-Za-z_][\w\-.]*=\"(?:xml|xmlns)\"", "", raw)
    raw = re.sub(r"\sxmlns=\"(?:xml|xmlns)\"", "", raw)
    return raw


def detect_pm_dir() -> str:
    """Return the PhotoMesh installation directory or raise ``FileNotFoundError``."""

    root = r"C:\\Program Files\\Skyline\\PhotoMesh"
    if os.path.isdir(root):
        return root
    raise FileNotFoundError("PhotoMesh not found")


def detect_wizard_dir(pm_dir: str) -> str:
    """Return the directory containing ``PhotoMeshWizard.exe``."""

    cands = [
        r"C:\\Program Files\\Skyline\\PhotoMeshWizard",
        os.path.join(pm_dir, r"Tools\\PhotomeshWizard"),
    ]
    for d in cands:
        if os.path.isdir(d):
            return d
    for dp, _, fs in os.walk(r"C:\\Program Files\\Skyline"):
        if "PhotoMeshWizard.exe" in fs or "WizardGUI.exe" in fs:
            return dp
    raise FileNotFoundError("Wizard not found")


# Attempt to locate installed paths but fall back to defaults if missing so the
# module remains importable on systems without PhotoMesh (e.g. during testing).
try:  # pragma: no cover - environment specific
    PM_DIR = detect_pm_dir()
except FileNotFoundError:  # pragma: no cover - missing install
    PM_DIR = r"C:\\Program Files\\Skyline\\PhotoMesh"

PM_PRESETS_DIR = os.path.join(PM_DIR, "Presets")

try:  # pragma: no cover - environment specific
    WIZ_DIR = detect_wizard_dir(PM_DIR)
except FileNotFoundError:  # pragma: no cover - missing install
    WIZ_DIR = os.path.join(PM_DIR, r"Tools\PhotomeshWizard")

try:  # pragma: no cover - environment specific
    WIZ_EXE = next(
        p
        for p in (
            os.path.join(WIZ_DIR, "PhotoMeshWizard.exe"),
            os.path.join(WIZ_DIR, "WizardGUI.exe"),
        )
        if os.path.isfile(p)
    )
except StopIteration:  # pragma: no cover - missing install
    WIZ_EXE = os.path.join(WIZ_DIR, "PhotoMeshWizard.exe")

WIZ_CFG = os.path.join(WIZ_DIR, "config.json")


def _wizard_presets_dirs() -> list[str]:
    return [
        r"C:\Program Files\Skyline\PhotoMeshWizard\Presets",
        r"C:\Program Files\Skyline\PhotoMesh\Tools\PhotomeshWizard\Presets",
    ]


def _resolve_wizard_preset(name: str) -> str:
    for d in _wizard_presets_dirs():
        p = os.path.join(d, f"{name}.PMPreset")
        if os.path.isfile(p):
            return p
    return ""


def _repair_output_and_pivot(
    preset_path: str, preset_name: str, log: logging.Logger | callable = logging.info
) -> None:
    """Force OBJ-only output and enable project-centred pivot/ellipsoid."""

    try:
        with open(preset_path, "r", encoding="utf-8", errors="ignore") as f:
            cleaned = _strip_illegal_xmlns(f.read())
        tree = ET.ElementTree(ET.fromstring(cleaned))
    except Exception:  # pragma: no cover - corrupt preset
        root = ET.Element("BuildParametersPreset")
        tree = ET.ElementTree(root)

    root = tree.getroot()
    bp = root.find("BuildParameters") or ET.SubElement(root, "BuildParameters")

    ofs = bp.find("OutputFormats") or ET.SubElement(bp, "OutputFormats")
    for c in list(ofs):
        ofs.remove(c)
    ET.SubElement(ofs, f"{{{ARR}}}string").text = "OBJ"

    for tag in ("CenterModelsToProject", "CesiumReprojectZ"):
        n = bp.find(tag) or ET.SubElement(bp, tag)
        n.text = "true"

    for tag in ("IsDefault", "IsLastUsed"):
        n = root.find(tag) or ET.SubElement(root, tag)
        n.text = "true"

    pn = root.find("PresetName") or ET.SubElement(root, "PresetName")
    pn.text = preset_name

    tmp = preset_path + ".tmp"
    tree.write(tmp, encoding="utf-8", xml_declaration=True)
    os.replace(tmp, preset_path)
    log(f"[preset] normalized: {preset_path}")


def stage_install_preset(repo_preset_path: str, preset_name: str) -> str:
    """Copy and normalise the preset into the installed PhotoMesh preset folder."""

    os.makedirs(PM_PRESETS_DIR, exist_ok=True)
    dst = os.path.join(PM_PRESETS_DIR, f"{preset_name}.PMPreset")
    shutil.copy2(repo_preset_path, dst)
    _repair_output_and_pivot(dst, preset_name)
    for d in _wizard_presets_dirs():
        os.makedirs(d, exist_ok=True)
        shutil.copy2(dst, os.path.join(d, f"{preset_name}.PMPreset"))
    return dst


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json(path, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def enforce_wizard_defaults_obj_only() -> None:
    """Ensure Wizard defaults to OBJ output, centred pivot and ellipsoid reprojection."""

    cfg = _load_json(WIZ_CFG)
    ui = cfg.setdefault("DefaultPhotoMeshWizardUI", {})
    outs = ui.setdefault("OutputProducts", {})
    outs["3DModel"] = True
    outs["Ortho"] = False
    m3d = ui.setdefault("Model3DFormats", {})
    for k, v in list(m3d.items()):
        if isinstance(v, bool):
            m3d[k] = False
    m3d["OBJ"] = True
    m3d["3DML"] = True
    ui["CenterPivotToProject"] = True
    ui["CenterModelsToProject"] = True
    ui["ReprojectToEllipsoid"] = True
    cfg["UseMinimize"] = True
    cfg["ClosePMWhenDone"] = True
    _save_json(WIZ_CFG, cfg)


def launch_autostart_build(
    project_name: str, project_path: str, folders: list[str], preset_name: str
) -> subprocess.Popen:
    """Launch the Wizard with ``--autostart`` using an install-level preset."""

    enforce_wizard_defaults_obj_only()
    preset_abs = _resolve_wizard_preset(preset_name) or preset_name
    logging.info(f"[wizard] exe: {WIZ_EXE}")
    logging.info(f"[wizard] preset: {preset_abs}")
    args = [
        WIZ_EXE,
        "--projectName",
        project_name,
        "--projectPath",
        project_path,
        "--preset",
        preset_abs,
        "--autostart",
    ]
    for f in folders:
        args += ["--folder", f]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(args, cwd=WIZ_DIR, creationflags=creationflags)


__all__ = [
    "stage_install_preset",
    "launch_autostart_build",
    "enforce_wizard_defaults_obj_only",
]

