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

# Installed Wizard config; attempt to detect actual install folder


def _detect_wizard_dir() -> str:
    candidates = [
        r"C:\\Program Files\\Skyline\\PhotoMeshWizard",
        r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard",
    ]
    for d in candidates:
        if os.path.isdir(d):
            return d
    root = r"C:\\Program Files\\Skyline"
    for dp, dn, fn in os.walk(root):
        if "PhotoMeshWizard.exe" in fn or "WizardGUI.exe" in fn:
            return dp
    raise FileNotFoundError("PhotoMesh Wizard folder not found.")


WIZARD_DIR = _detect_wizard_dir()
WIZARD_INSTALL_CFG = os.path.join(WIZARD_DIR, "config.json")


def _find_wizard_exe():
    for exe in ("PhotoMeshWizard.exe", "WizardGUI.exe"):
        p = os.path.join(WIZARD_DIR, exe)
        if os.path.isfile(p):
            return p
    raise FileNotFoundError("PhotoMesh Wizard executable not found.")


# PhotoMesh Wizard executable
WIZARD_EXE = _find_wizard_exe()
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


def _is_offline_enabled() -> bool:
    try:
        config.read(CONFIG_PATH)
        return config.getboolean("Offline", "enabled", fallback=False)
    except Exception:
        return False

def get_offline_cfg():
    if "Offline" not in config:
        config["Offline"] = {}
    o = config["Offline"]
    return {
        "enabled": o.getboolean("enabled", False),
        "host_name": o.get("host_name", "KIT-HOST").strip(),
        "host_ip": o.get("host_ip", "192.168.50.10").strip(),
        "share_name": o.get("share_name", "SharedMeshDrive").strip(),
        "local_data_root": os.path.normpath(o.get("local_data_root", r"D:\\SharedMeshDrive")),
        "working_fuser_subdir": o.get("working_fuser_subdir", "WorkingFuser").strip(),
        "use_ip_unc": o.getboolean("use_ip_unc", False),
    }


def build_unc(o: dict) -> str:
    host = o["host_ip"] if o["use_ip_unc"] else o["host_name"]
    return rf"\\{host}\{o['share_name']}"


def working_fuser_unc(o: dict) -> str:
    return os.path.join(build_unc(o), o["working_fuser_subdir"])


def resolve_network_working_folder_from_cfg(o: dict) -> str:
    base = o["host_ip"] if o.get("use_ip_unc") else o["host_name"]
    return rf"\\{base}\{o['share_name']}\{o['working_fuser_subdir']}"


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
        log(f"Offline share ensured: \\\\{o['host_name']}\\{share}  ({root})")
    except Exception as e:
        log(
            f"Could not run PowerShell to ensure share: {e}\nPlease share {root} as '{share}' manually."
        )


def can_access_unc(path: str) -> bool:
    try:
        return os.path.isdir(path) and os.listdir(path) is not None
    except Exception:
        return False



def _load_json_safe(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json_safe(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _update_wizard_network_mode(cfg: dict) -> None:
    """
    Always write NetworkWorkingFolder so the Wizard UI shows Network fusers,
    but we only ENFORCE reachability when Offline Mode is ON.
    """
    try:
        config.read(CONFIG_PATH)
    except Exception:
        pass
    o = get_offline_cfg()
    cfg["NetworkWorkingFolder"] = resolve_network_working_folder_from_cfg(o)


def _bool_map_all_false(d: dict) -> None:
    for k in list(d.keys()):
        if isinstance(d[k], bool):
            d[k] = False


def enforce_install_cfg_ui_only() -> None:
    cfg = _load_json_safe(WIZARD_INSTALL_CFG)
    ui = cfg.setdefault("DefaultPhotoMeshWizardUI", {})

    outputs = ui.setdefault("OutputProducts", {})
    outputs["3DModel"] = True
    outputs["Ortho"] = False
    outputs.pop("Orthophoto", None)

    m3d = ui.setdefault("Model3DFormats", {})
    _bool_map_all_false(m3d)
    m3d["OBJ"] = True
    m3d["3DML"] = False

    ui["CenterPivotToProject"] = True
    ui["CenterModelsToProject"] = True
    ui["ReprojectToEllipsoid"] = True

    cfg.setdefault("UseMinimize", True)
    cfg.setdefault("ClosePMWhenDone", False)
    cfg.setdefault("OutputWaitTimerSeconds", 10)

    _update_wizard_network_mode(cfg)

    _save_json_safe(WIZARD_INSTALL_CFG, cfg)


def enforce_user_cfg_no_preset(autostart: bool = True) -> None:
    cfg = _load_json_safe(WIZARD_USER_CFG)
    cfg["OverrideSettings"] = True
    cfg["AutoBuild"] = bool(autostart)
    cfg.pop("SelectedPreset", None)
    cfg.pop("LastUsedPreset", None)
    _save_json_safe(WIZARD_USER_CFG, cfg)


def launch_wizard_no_preset(project_name: str, project_path: str, folders: List[str]) -> subprocess.Popen:
    enforce_install_cfg_ui_only()
    enforce_user_cfg_no_preset(autostart=True)

    verify_effective_settings()

    args = [
        WIZARD_EXE,
        "--projectName",
        project_name,
        "--projectPath",
        project_path,
        "--overrideSettings",
    ]
    for fld in folders:
        args += ["--folder", fld]

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(args, cwd=os.path.dirname(WIZARD_EXE), creationflags=creationflags)


def enforce_photomesh_settings() -> None:
    enforce_install_cfg_ui_only()
    enforce_user_cfg_no_preset()


def launch_wizard_cli(project_name: str, project_path: str, folders: List[str]) -> subprocess.Popen | None:
    try:
        return launch_wizard_no_preset(project_name, project_path, folders)
    except Exception as e:
        from tkinter import messagebox
        messagebox.showerror("PhotoMesh Wizard", f"Failed to launch Wizard:\n{e}")
        return None


def verify_effective_settings() -> None:
    """Print a checklist of critical Wizard settings from both configs."""
    o = get_offline_cfg()
    print("Offline enabled:", o["enabled"])
    install = _load_json_safe(WIZARD_INSTALL_CFG)
    print("Wizard NetworkWorkingFolder:", install.get("NetworkWorkingFolder", "(none)"))
    user = _load_json_safe(WIZARD_USER_CFG)

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

