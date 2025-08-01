from pathlib import Path
import os
import json
import subprocess
from typing import Iterable

# Constants
PRESET_NAME = "CPP&OBJ"
WIZARD_EXE = r"C:\Program Files\Skyline\PhotoMeshWizard\PhotoMeshWizard.exe"
PHOTOMESH_CONFIG = r"C:\Program Files\Skyline\PhotoMesh\Tools\PhotomeshWizard\config.json"

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