import os
import json
import shutil
import logging
import filecmp
import subprocess
import xml.etree.ElementTree as ET
from typing import Callable, List

PRESET_NAME = "OECPP"
PRESET_FILENAME = f"{PRESET_NAME}.PMPreset"

PROGRAM_FILES = os.getenv("ProgramFiles", r"C:\\Program Files")
WIZARD_DIR = os.path.join(PROGRAM_FILES, "Skyline", "PhotoMesh", "Tools", "PhotomeshWizard")
INSTALL_CFG = os.path.join(WIZARD_DIR, "config.json")

APPDATA = os.getenv("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
USER_PRESET_DIR = os.path.join(APPDATA, "Skyline", "PhotoMesh", "Presets")
USER_PRESET_PATH = os.path.join(USER_PRESET_DIR, PRESET_FILENAME)
USER_PRESET_SETTINGS = os.path.join(USER_PRESET_DIR, "PresetSettings.xml")
USER_CFG = os.path.join(APPDATA, "Skyline", "PhotoMesh", "Wizard", "config.json")


def _is_admin() -> bool:
    """Return True if running with administrative privileges."""
    if os.name == "nt":
        try:
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
    """Load JSON file from *path* returning empty dict on failure."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def _preset_dst_for_profile(profile_dir: str) -> str:
    return os.path.join(
        profile_dir,
        "AppData",
        "Roaming",
        "Skyline",
        "PhotoMesh",
        "Presets",
        PRESET_FILENAME,
    )


def _preset_settings_xml_for_profile(profile_dir: str) -> str:
    return os.path.join(
        profile_dir,
        "AppData",
        "Roaming",
        "Skyline",
        "PhotoMesh",
        "Presets",
        "PresetSettings.xml",
    )


def _user_cfg_for_profile(profile_dir: str) -> str:
    return os.path.join(
        profile_dir,
        "AppData",
        "Roaming",
        "Skyline",
        "PhotoMesh",
        "Wizard",
        "config.json",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_profile_settings(profile_dir: str, preset_src: str, autostart: bool) -> None:
    """Copy preset and enforce defaults for a given user profile."""
    try:
        dst = _preset_dst_for_profile(profile_dir)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.isfile(dst) or not filecmp.cmp(preset_src, dst, False):
            shutil.copy2(preset_src, dst)

        # PresetSettings.xml
        xml_path = _preset_settings_xml_for_profile(profile_dir)
        os.makedirs(os.path.dirname(xml_path), exist_ok=True)
        if os.path.isfile(xml_path):
            try:
                tree = ET.parse(xml_path)
                root = tree.getroot()
            except Exception:
                root = ET.Element("PresetSettings")
                tree = ET.ElementTree(root)
        else:
            root = ET.Element("PresetSettings")
            tree = ET.ElementTree(root)
        default = root.find("DefaultPresetNames")
        if default is None:
            default = ET.SubElement(root, "DefaultPresetNames")
        for child in list(default):
            default.remove(child)
        ET.SubElement(default, "string").text = PRESET_NAME
        tree.write(xml_path, encoding="utf-8", xml_declaration=True)

        # User config
        cfg_path = _user_cfg_for_profile(profile_dir)
        cfg = _load_json(cfg_path)
        cfg.update(
            {
                "OverrideSettings": True,
                "AutoBuild": bool(autostart),
                "SelectedPreset": PRESET_NAME,
                "DefaultPresetName": PRESET_NAME,
            }
        )
        _save_json(cfg_path, cfg)
    except Exception as exc:  # pragma: no cover - continue on error
        logging.warning("Failed to seed profile %s: %s", profile_dir, exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def seed_preset_everywhere(repo_hint: str, also_set_default_profile: bool = True) -> None:
    """Copy preset into all user profiles and set defaults."""
    repo_hint = os.path.abspath(repo_hint)
    preset_src = repo_hint if os.path.isfile(repo_hint) else _find_file_recursive(
        os.path.dirname(repo_hint), PRESET_FILENAME
    )
    if not preset_src:
        raise FileNotFoundError(f"Preset {PRESET_FILENAME} not found from {repo_hint}")

    users_root = os.path.join(os.getenv("SystemDrive", "C:"), "Users")
    try:
        names = os.listdir(users_root)
    except FileNotFoundError:  # pragma: no cover
        names = []

    profiles = []
    for name in names:
        if not also_set_default_profile and name.lower() in {"default"}:
            continue
        path = os.path.join(users_root, name)
        if os.path.isdir(path):
            profiles.append(path)

    for profile in profiles:
        _apply_profile_settings(profile, preset_src, True)


def prepare_photomesh_environment_per_user(repo_hint: str, autostart: bool = True) -> None:
    """Ensure the current user's preset and configs are correct."""
    repo_hint = os.path.abspath(repo_hint)
    preset_src = repo_hint if os.path.isfile(repo_hint) else _find_file_recursive(
        os.path.dirname(repo_hint), PRESET_FILENAME
    )
    if not preset_src:
        raise FileNotFoundError(f"Preset {PRESET_FILENAME} not found from {repo_hint}")

    profile_dir = os.path.dirname(os.path.dirname(APPDATA))
    _apply_profile_settings(profile_dir, preset_src, autostart)


def enforce_install_cfg_obj_only(
    center_pivot: bool = True,
    ellipsoid: bool = True,
    disable_ortho: bool = True,
    obj_only: bool = True,
) -> bool:
    """Write install-level Wizard config enforcing OBJ-only output."""
    if not _is_admin() or not os.path.isfile(INSTALL_CFG):
        return False

    cfg = _load_json(INSTALL_CFG)
    ui = cfg.setdefault("DefaultPhotoMeshWizardUI", {})
    outputs = ui.setdefault("OutputProducts", {})
    outputs["3DModel"] = True
    if disable_ortho:
        outputs["Ortho"] = False
    m3d = ui.setdefault("Model3DFormats", {})
    if obj_only:
        for key in list(m3d.keys()):
            if isinstance(m3d[key], bool):
                m3d[key] = False
        m3d["OBJ"] = True
        m3d["3DML"] = False
    if center_pivot:
        ui["CenterPivotToProject"] = True
    if ellipsoid:
        ui["ReprojectToEllipsoid"] = True

    try:
        _save_json(INSTALL_CFG, cfg)
        return True
    except Exception:  # pragma: no cover
        return False


def find_wizard_exe() -> str:
    """Return full path to the PhotoMesh Wizard executable."""
    for name in ("PhotoMeshWizard.exe", "WizardGUI.exe"):
        path = os.path.join(WIZARD_DIR, name)
        if os.path.isfile(path):
            return path
    raise FileNotFoundError("PhotoMesh Wizard executable not found")


def launch_wizard_with_preset(
    project_name: str, project_path: str, folders: List[str], preset_name: str = PRESET_NAME
) -> subprocess.Popen:
    """Launch the PhotoMesh Wizard with provided folders and preset."""
    exe = find_wizard_exe()
    args = [
        exe,
        "--projectName",
        project_name,
        "--projectPath",
        project_path,
        "--overrideSettings",
        "--preset",
        preset_name,
    ]
    for fld in folders:
        args += ["--folder", fld]
    return subprocess.Popen(args, cwd=os.path.dirname(exe))


def verify_effective_settings(log: Callable[[str], None] = print) -> None:
    """Log selected output products and formats from configs."""
    install = _load_json(INSTALL_CFG)
    user = _load_json(USER_CFG)
    ui = install.get("DefaultPhotoMeshWizardUI", {})
    outputs = ui.get("OutputProducts", {})
    m3d = ui.get("Model3DFormats", {})
    log(
        f"OutputProducts: 3DModel={outputs.get('3DModel')} Ortho={outputs.get('Ortho')}"
    )
    log(f"Model3DFormats: OBJ={m3d.get('OBJ')} 3DML={m3d.get('3DML')}")
    log(
        f"CenterPivotToProject={ui.get('CenterPivotToProject')} "
        f"ReprojectToEllipsoid={ui.get('ReprojectToEllipsoid')}"
    )
    log(
        f"UserConfig: AutoBuild={user.get('AutoBuild')} SelectedPreset={user.get('SelectedPreset')}"
    )
