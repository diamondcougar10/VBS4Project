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
# Accessing APPDATA directly mirrors expected Windows behaviour and will raise
# a KeyError if missing, which is fine for non-Windows environments.
WIZARD_USER_CFG = os.path.join(
    os.environ["APPDATA"], "Skyline", "PhotoMesh", "Wizard", "config.json"
)

# Installed Wizard config (official path per manual)
WIZARD_INSTALL_CFG = r"C:\Program Files\Skyline\PhotoMeshWizard\config.json"

# PhotoMesh Wizard executable
WIZARD_EXE = r"C:\Program Files\Skyline\PhotoMeshWizard\PhotoMeshWizard.exe"

# Preset configuration
PRESET_NAME = "CPP&OBJ"
DEFAULT_WIZARD_PRESET = PRESET_NAME
PRESET_PATH = os.path.join(
    os.environ["APPDATA"], "Skyline", "PhotoMesh", "Presets", f"{PRESET_NAME}.preset"
)

# Load shared configuration for network fuser settings
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")
config = configparser.ConfigParser()
config.read(CONFIG_PATH)

OFFLINE_ACCESS_HINT = (
    "Cannot access the shared working folder.\n\n"
    "Connect all PCs to the same switch, assign static IPs (e.g., host 192.168.50.10, "
    "clients 192.168.50.11-13, mask 255.255.255.0), ensure the same Workgroup "
    "(e.g., WORKGROUP), share the local_data_root on the host as share_name with "
    "read/write permissions, and if name resolution fails, enable use_ip_unc or add "
    "host_name to C:\\Windows\\System32\\drivers\\etc\\hosts."
)


def get_offline_cfg():
    o = config["Offline"]
    return {
        "enabled": o.getboolean("enabled", False),
        "host_name": o.get("host_name", "KIT-HOST").strip(),
        "host_ip": o.get("host_ip", "192.168.50.10").strip(),
        "share_name": o.get("share_name", "SharedMeshDrive").strip(),
        "local_data_root": os.path.normpath(
            o.get("local_data_root", r"D:\\SharedMeshDrive")
        ),
        "working_fuser_subdir": o.get("working_fuser_subdir", "WorkingFuser").strip(),
        "use_ip_unc": o.getboolean("use_ip_unc", False),
    }


def build_unc(o: dict) -> str:
    host = o["host_ip"] if o["use_ip_unc"] else o["host_name"]
    return rf"\\{host}\{o['share_name']}"


def working_fuser_unc(o: dict) -> str:
    return os.path.join(build_unc(o), o["working_fuser_subdir"])


def _legacy_host() -> str:
    return config.get(
        "Fusers",
        "working_folder_host",
        fallback=config.get("General", "host", fallback="KIT-HOST"),
    ).strip()


def resolve_network_working_folder() -> str:
    o = get_offline_cfg()
    if not o["enabled"]:
        return config.get(
            "PhotoMesh",
            "NetworkWorkingFolder",
            fallback=rf"\\{_legacy_host()}\\SharedMeshDrive\\WorkingFuser",
        )
    return working_fuser_unc(o)


def ensure_offline_share_exists(log=print):
    o = get_offline_cfg()
    root = o["local_data_root"]
    share = o["share_name"]
    try:
        os.makedirs(root, exist_ok=True)
    except Exception as e:
        log(f"Failed to create {root}: {e}")
        return

    ps = fr"""
$ErrorActionPreference='SilentlyContinue'
$share='{share}'
$path='{root}'
if (-not (Get-SmbShare -Name $share)) {{
  New-SmbShare -Name $share -Path $path -FullAccess 'Everyone' | Out-Null
}}
# Enable file & printer sharing rules on Private profile
Get-NetFirewallRule -DisplayGroup 'File and Printer Sharing' | Where-Object {{$_.Profile -like '*Private*'}} | Enable-NetFirewallRule | Out-Null
"""
    try:
        subprocess.run([
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps,
        ], check=False)
        log(f"Offline share ensured: \\{o['host_name']}\{share}  ({root})")
    except Exception as e:
        log(
            f"Could not run PowerShell to ensure share: {e}\nPlease share {root} as '{share}' manually."
        )


def can_access_unc(path: str) -> bool:
    try:
        return os.path.isdir(path) and os.listdir(path) is not None
    except Exception:
        return False

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


def _load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def enforce_install_cfg() -> None:
    """Force required options in the installation-level Wizard config."""
    cfg = _load_json(WIZARD_INSTALL_CFG)
    ui = cfg.setdefault("DefaultPhotoMeshWizardUI", {})

    outputs = ui.setdefault("OutputProducts", {})
    outputs["3DModel"] = True
    outputs["Ortho"] = False
    outputs["Orthophoto"] = False

    m3d = ui.setdefault("Model3DFormats", {})
    for k, v in list(m3d.items()):
        if isinstance(v, bool):
            m3d[k] = False
    m3d["OBJ"] = True
    m3d["3DML"] = False

    ui["CenterModelsToProject"] = True
    ui["CenterPivotToProject"] = True
    ui["ReprojectToEllipsoid"] = True

    cfg.setdefault("UseMinimize", True)
    cfg.setdefault("ClosePMWhenDone", False)
    cfg.setdefault("OutputWaitTimerSeconds", 10)
    cfg["NetworkWorkingFolder"] = resolve_network_working_folder()

    try:
        _save_json(WIZARD_INSTALL_CFG, cfg)
    except PermissionError:
        print(
            "⚠️ Unable to write install config (permission). Continuing with user config."
        )


def enforce_user_cfg() -> None:
    """Write user-level config selecting the preset and enabling auto-build."""
    cfg = {
        "SelectedPreset": PRESET_NAME,
        "OverrideSettings": True,
        "AutoBuild": True,
    }
    _save_json(WIZARD_USER_CFG, cfg)


def enforce_photomesh_settings() -> None:
    """Legacy wrapper to maintain backwards compatibility."""
    enforce_install_cfg()
    enforce_user_cfg()


def ensure_wizard_user_defaults(
    preset: str = PRESET_NAME, autostart: bool = True
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
    """Patch the installed Wizard config with network and basic defaults."""

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

    cfg["NetworkWorkingFolder"] = resolve_network_working_folder()

    ui = cfg.setdefault("DefaultPhotoMeshWizardUI", {})
    ui.setdefault("ProcessingLevel", "Standard")
    ui.setdefault("StopOnError", True)
    ui.setdefault("MaxProcessing", False)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def launch_wizard_cli(project_name: str, project_path: str, folders: List[str]) -> None:
    """Launch the PhotoMesh Wizard with prepared sources via CLI."""
    o = get_offline_cfg()
    if o["enabled"] and not can_access_unc(resolve_network_working_folder()):
        from tkinter import messagebox

        messagebox.showerror("Offline Mode", OFFLINE_ACCESS_HINT)
        return

    if not os.path.isfile(WIZARD_EXE):
        from tkinter import messagebox

        messagebox.showerror(
            "PhotoMesh Wizard", "PhotoMeshWizard.exe not found.\nCheck installation path."
        )
        return

    ensure_preset_exists()
    enforce_install_cfg()
    enforce_user_cfg()
    verify_effective_settings()

    args = [
        WIZARD_EXE,
        "--projectName",
        project_name,
        "--projectPath",
        project_path,
        "--preset",
        PRESET_NAME,
        "--overrideSettings",
    ]
    for fld in folders:
        args += ["--folder", fld]

    try:
        subprocess.Popen(args, cwd=os.path.dirname(WIZARD_EXE))
    except Exception as e:
        from tkinter import messagebox

        messagebox.showerror("PhotoMesh Wizard", f"Failed to launch Wizard:\n{e}")

def ensure_preset_exists() -> str:
    """Ensure the CPP&OBJ preset file exists with the expected content."""
    os.makedirs(os.path.dirname(PRESET_PATH), exist_ok=True)
    try:
        if os.path.isfile(PRESET_PATH):
            with open(PRESET_PATH, "r", encoding="utf-8") as f:
                if f.read() == PRESET_XML:
                    return PRESET_PATH
        with open(PRESET_PATH, "w", encoding="utf-8") as f:
            f.write(PRESET_XML)
    except OSError as e:
        raise RuntimeError(f"Unable to write preset: {e}") from e
    return PRESET_PATH


def verify_effective_settings() -> None:
    """Print a checklist of critical Wizard settings from both configs."""
    install = _load_json(WIZARD_INSTALL_CFG)
    user = _load_json(WIZARD_USER_CFG)

    ui = install.get("DefaultPhotoMeshWizardUI", {})
    outputs = ui.get("OutputProducts", {})
    m3d = ui.get("Model3DFormats", {})

    checks = {
        "OutputProducts.3DModel": outputs.get("3DModel") is True,
        "OutputProducts.Ortho": outputs.get("Ortho") is False,
        "Model3DFormats.OBJ": m3d.get("OBJ") is True,
        "Model3DFormats.3DML": m3d.get("3DML") is False,
        "CenterModelsToProject": ui.get("CenterModelsToProject") is True
        or ui.get("CenterPivotToProject") is True,
        "ReprojectToEllipsoid": ui.get("ReprojectToEllipsoid") is True,
        "User.AutoBuild": user.get("AutoBuild") is True,
    }

    for key, ok in checks.items():
        print(f"{key}: {ok}")
        if not ok:
            print(f"WARNING: {key} not set as expected")

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
    enforce_install_cfg()
    enforce_user_cfg()
    verify_effective_settings()

    args = [
        WIZARD_EXE,
        "--projectName",
        project_name,
        "--projectPath",
        project_path,
        "--preset",
        PRESET_NAME,
        "--overrideSettings",
    ]
    for folder in image_folders:
        args.extend(["--folder", folder])

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.Popen(
            args, cwd=os.path.dirname(WIZARD_EXE), creationflags=creationflags
        )
    except Exception as exc:
        print(f"Failed to launch PhotoMeshWizard: {exc}")
        raise
