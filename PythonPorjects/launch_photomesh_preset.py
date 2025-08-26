from pathlib import Path
import os
import json
import subprocess
import configparser
from typing import Iterable, List

# ---------------------------------------------------------------------------
# PhotoMesh Wizard configuration
# ---------------------------------------------------------------------------

# User-level config written under %APPDATA%
WIZARD_USER_CFG = os.path.join(
    os.environ.get("APPDATA", ""), "Skyline", "PhotoMesh", "Wizard", "config.json"
)

# Installed Wizard config (official path per manual)
WIZARD_INSTALL_CFG = r"C:\Program Files\Skyline\PhotoMeshWizard\config.json"

# PhotoMesh Wizard executable
WIZARD_EXE = r"C:\Program Files\Skyline\PhotoMeshWizard\PhotoMeshWizard.exe"

# Load shared configuration for network fuser settings
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")
_cfg = configparser.ConfigParser()
_cfg.read(CONFIG_PATH)

WORKING_FOLDER_HOST = _cfg.get("Fusers", "working_folder_host", fallback="HAMMERKIT1-4")
NETWORK_WORKING_FOLDER = fr"\\{WORKING_FOLDER_HOST}\SharedMeshDrive\WorkingFuser"

# Default preset name used by Wizard
DEFAULT_WIZARD_PRESET = "CPP&OBJ"

# Legacy constant kept for compatibility with existing helpers
PRESET_NAME = DEFAULT_WIZARD_PRESET

PRESET_XML = """<?xml version="1.0" encoding="utf-8"?>
<BuildParametersPreset xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
  <SerializableVersion>8.0.4.50513</SerializableVersion>
  <Version xmlns:d2p1="http://schemas.datacontract.org/2004/07/System">
    <d2p1:_Build>4</d2p1:_Build>
    <d2p1:_Major>8</d2p1:_Major>
    <d2p1:_Minor>0</d2p1:_Minor>
    <d2p1:_Revision>50513</d2p1:_Revision>
  </Version>
  <BuildParameters>
    <SerializableVersion>8.0.4.50513</SerializableVersion>
    <Version xmlns:d3p1="http://schemas.datacontract.org/2004/07/System">
      <d3p1:_Build>4</d3p1:_Build>
      <d3p1:_Major>8</d3p1:_Major>
      <d3p1:_Minor>0</d3p1:_Minor>
      <d3p1:_Revision>50513</d3p1:_Revision>
    </Version>
    <AddWalls>false</AddWalls>
    <CenterModelsToProject>true</CenterModelsToProject>
    <DsmSettings />
    <FillInGround>true</FillInGround>
    <FocalLengthAccuracy>-1</FocalLengthAccuracy>
    <HorizontalAccuracyFactor>0.1</HorizontalAccuracyFactor>
    <IgnoreOrientation>false</IgnoreOrientation>
    <OrthoSettings />
    <OutputFormats xmlns:d3p1="http://schemas.microsoft.com/2003/10/Serialization/Arrays">
      <d3p1:string>OBJ</d3p1:string>
    </OutputFormats>
    <PointCloudFormat>LAS</PointCloudFormat>
    <PrincipalPointAccuracy>-1</PrincipalPointAccuracy>
    <RadialAccuracy>false</RadialAccuracy>
    <TangentialAccuracy>false</TangentialAccuracy>
    <TileSplitMethod>Simple</TileSplitMethod>
    <VerticalAccuracyFactor>0.1</VerticalAccuracyFactor>
    <VerticalBias>false</VerticalBias>
  </BuildParameters>
  <Description>saves as center piviot</Description>
  <IsDefault>false</IsDefault>
  <IsLastUsed>false</IsLastUsed>
  <IsSystem>false</IsSystem>
  <IsSystemDefault>false</IsSystemDefault>
  <PresetFileName i:nil="true" />
  <PresetName>CPP&amp;OBJ</PresetName>
</BuildParametersPreset>
"""


def ensure_wizard_user_defaults(
    preset: str = DEFAULT_WIZARD_PRESET, autostart: bool = True
) -> None:
    """Ensure the PhotoMesh Wizard user config selects *preset* and auto-builds."""

    os.makedirs(os.path.dirname(WIZARD_USER_CFG), exist_ok=True)
    cfg = {
        "SelectedPreset": preset,
        "OverrideSettings": True,
        "AutoBuild": bool(autostart),
    }
    with open(WIZARD_USER_CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def ensure_wizard_install_defaults() -> None:
    """Patch the installed Wizard config for OBJ export and network settings."""

    path = WIZARD_INSTALL_CFG
    if not os.path.isfile(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        try:
            cfg = json.load(f)
        except Exception:
            cfg = {}

    cfg.setdefault("UseMinimize", True)
    cfg.setdefault("ClosePMWhenDone", False)
    cfg.setdefault("OutputWaitTimerSeconds", 10)

    cfg["NetworkWorkingFolder"] = NETWORK_WORKING_FOLDER

    ui = cfg.setdefault("DefaultPhotoMeshWizardUI", {})
    formats = ui.setdefault("Model3DFormats", {})
    formats["OBJ"] = True
    formats["3DML"] = False

    ui.setdefault("ProcessingLevel", "Standard")
    ui.setdefault("StopOnError", True)
    ui.setdefault("MaxProcessing", False)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def launch_wizard_cli(project_name: str, project_path: str, folders: List[str]) -> None:
    """Launch the PhotoMesh Wizard with prepared sources via CLI."""

    if not os.path.isfile(WIZARD_EXE):
        from tkinter import messagebox

        messagebox.showerror(
            "PhotoMesh Wizard", "PhotoMeshWizard.exe not found.\nCheck installation path."
        )
        return

    args = [WIZARD_EXE, "--projectName", project_name, "--projectPath", project_path]
    for fld in folders:
        args += ["--folder", fld]

    ensure_wizard_user_defaults(DEFAULT_WIZARD_PRESET, autostart=True)
    ensure_wizard_install_defaults()

    try:
        subprocess.Popen(args, cwd=os.path.dirname(WIZARD_EXE))
    except Exception as e:
        from tkinter import messagebox

        messagebox.showerror("PhotoMesh Wizard", f"Failed to launch Wizard:\n{e}")

def ensure_preset_exists() -> str:
    """Write the CPP&OBJ preset file and return its path."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise EnvironmentError("%APPDATA% is not set")

    preset_dir = os.path.join(appdata, "Skyline", "PhotoMesh", "Presets")
    preset_path = os.path.join(preset_dir, f"{PRESET_NAME}.preset")
    os.makedirs(preset_dir, exist_ok=True)
    with open(preset_path, "w", encoding="utf-8") as f:
        f.write(PRESET_XML)


    return preset_path

def ensure_config_json() -> str:
    """Create Wizard config.json pointing to the preset and return its path."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise EnvironmentError("%APPDATA% is not set")

    wizard_dir = os.path.join(appdata, "Skyline", "PhotoMesh", "Wizard")
    os.makedirs(wizard_dir, exist_ok=True)
    config_path = os.path.join(wizard_dir, "config.json")

    data = {
        "SelectedPreset": PRESET_NAME,
        "OverrideSettings": True,
        "AutoBuild": True,
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return config_path


def launch_photomesh_with_preset(
    project_name: str,
    project_path: str,
    image_folders: Iterable[str],
) -> subprocess.Popen:
    """Launch PhotoMeshWizard.exe using the CPP&OBJ preset."""
    if not os.path.isfile(WIZARD_EXE):
        raise FileNotFoundError(f"PhotoMeshWizard.exe not found: {WIZARD_EXE}")

    ensure_preset_exists()
    ensure_config_json()

def set_photomesh_preset(preset_xml: str) -> None:
    """Write the preset and update all PhotoMesh configuration files."""

    pm_config_path = r"C:\Program Files\Skyline\PhotoMeshWizard\config.json"
    data = {}
    if os.path.isfile(pm_config_path):
        try:
            with open(pm_config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    data.setdefault("DefaultPhotoMeshWizardUI", {})["Preset"] = PRESET_NAME
    data["LastUsedPreset"] = PRESET_NAME

    try:
        with open(pm_config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except PermissionError:
        pass

def launch_photomesh_with_preset(project_name: str, project_path: str, image_folders: Iterable[str]) -> subprocess.Popen:
    """Launch PhotoMeshWizard.exe with the CPP&OBJ preset."""
    if not os.path.isfile(WIZARD_EXE):
        raise FileNotFoundError(f"PhotoMeshWizard.exe not found: {WIZARD_EXE}")

    ensure_preset_exists()

    parts = [
        f'"{WIZARD_EXE}"',
        f'--projectName "{project_name}"',
        f'--projectPath "{project_path}"',
        f'--preset "{PRESET_NAME}"',
        "--overrideSettings",
    ]
    for folder in image_folders:
        parts.append(f'--folder "{folder}"')
    cmd = " ".join(parts)

    print("Running command:")
    print(cmd)

    creationflags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags = subprocess.CREATE_NO_WINDOW
    try:
        return subprocess.Popen(cmd, shell=True, creationflags=creationflags)
    except Exception as exc:
        raise RuntimeError(f"Failed to launch PhotoMeshWizard: {exc}") from exc