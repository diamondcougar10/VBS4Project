import json
import os
import subprocess
from typing import Iterable

PRESET_NAME = "CPP&OBJ"
def write_cpp_obj_preset() -> str:
    """Return the XML for the CPP&OBJ build preset."""

    return f"""<?xml version="1.0" encoding="utf-8"?>
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
  <Description>Center Pivot & OBJ Export Preset</Description>
  <IsDefault>true</IsDefault>
  <IsLastUsed>true</IsLastUsed>
  <IsSystem>false</IsSystem>
  <IsSystemDefault>false</IsSystemDefault>
  <PresetFileName i:nil="true" />
  <PresetName>{PRESET_NAME}</PresetName>
</BuildParametersPreset>
"""

WIZARD_EXE = r"C:\Program Files\Skyline\PhotoMeshWizard\PhotoMeshWizard.exe"


def ensure_preset_exists(preset_xml: str) -> str:
    """Write ``preset_xml`` to the preset folder and remove other presets."""

    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise EnvironmentError("%APPDATA% is not set")

    preset_dir = os.path.join(appdata, "Skyline", "PhotoMesh", "Presets")
    os.makedirs(preset_dir, exist_ok=True)
    preset_path = os.path.join(preset_dir, f"{PRESET_NAME}.preset")

    # Remove other presets so only ours is available
    for file in os.listdir(preset_dir):
        if file.endswith(".preset") and file != f"{PRESET_NAME}.preset":
            os.remove(os.path.join(preset_dir, file))

    # Write our preset
    with open(preset_path, "w", encoding="utf-8") as f:
        f.write(preset_xml)

    return preset_xml


def ensure_config_json(preset_xml: str) -> str:
    """Ensure the Wizard config selects our preset."""

    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise EnvironmentError("%APPDATA% is not set")

    wizard_dir = os.path.join(appdata, "Skyline", "PhotoMesh", "Wizard")
    os.makedirs(wizard_dir, exist_ok=True)
    config_path = os.path.join(wizard_dir, "config.json")

    data = {}
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    data["SelectedPreset"] = PRESET_NAME
    data["OverrideSettings"] = True
    data["AutoBuild"] = True

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return config_path


def set_photomesh_preset(preset_xml: str) -> None:
    """Write the preset and update all PhotoMesh configuration files."""

    # Ensure the preset file itself exists
    ensure_preset_exists(preset_xml)

    # Update the Wizard configuration stored in the user profile
    ensure_config_json(preset_xml)

    # Also update the global PhotoMeshWizard configuration so new
    # projects default to this preset when launched via the UI.
    pm_config_path = r"C:\Program Files\Skyline\PhotoMeshWizard\config.json"

    data = {}
    if os.path.isfile(pm_config_path):
        try:
            with open(pm_config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    data.setdefault("DefaultPhotoMeshWizardUI", {})["Preset"] = PRESET_NAME

    try:
        with open(pm_config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except PermissionError:
        # Access may be denied if the user is not elevated.  Fail silently
        # to allow the Wizard to still run with the preset written to the
        # user profile.
        pass


def launch_photomesh_with_preset(
    project_name: str,
    project_path: str,
    image_folders: Iterable[str],
) -> subprocess.Popen:
    """Launch PhotoMeshWizard with the custom preset."""
    if not os.path.isfile(WIZARD_EXE):
        raise FileNotFoundError(f"PhotoMeshWizard.exe not found: {WIZARD_EXE}")

    preset_xml = write_cpp_obj_preset()
    set_photomesh_preset(preset_xml)

    cmd = [
        WIZARD_EXE,
        "--projectName", project_name,
        "--projectPath", project_path,
    ]
    for folder in image_folders:
        cmd.extend(["--folder", folder])

    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
        startupinfo.wShowWindow = getattr(subprocess, "SW_SHOWMINIMIZED", 2)

    try:
        return subprocess.Popen(cmd, startupinfo=startupinfo)
    except Exception as exc:
        raise RuntimeError(f"Failed to launch PhotoMeshWizard: {exc}") from exc
