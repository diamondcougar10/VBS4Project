from __future__ import annotations
import os, json, shutil, subprocess, tempfile, configparser
from typing import Iterable, Optional

try:  # pragma: no cover - tkinter may not be available
    from tkinter import messagebox
except Exception:  # pragma: no cover - headless/test environments
    messagebox = None

# -------------------- Wizard detection --------------------
def _detect_wizard_dir() -> str:
    candidates = [
        r"C:\\Program Files\\Skyline\\PhotoMeshWizard",                 # new (8.0.4.150+)
        r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard", # legacy
    ]
    for d in candidates:
        if os.path.isdir(d):
            return d
    for dp, _dn, files in os.walk(r"C:\\Program Files\\Skyline"):
        if "PhotoMeshWizard.exe" in files or "WizardGUI.exe" in files:
            return dp
    raise FileNotFoundError("PhotoMesh Wizard folder not found")

try:  # pragma: no cover - environment specific
    WIZARD_DIR = _detect_wizard_dir()
except FileNotFoundError:  # pragma: no cover - missing install
    WIZARD_DIR = r"C:\\Program Files\\Skyline\\PhotoMeshWizard"
WIZARD_INSTALL_CFG = os.path.join(WIZARD_DIR, "config.json")

def _find_wizard_exe() -> str:
    for exe in ("PhotoMeshWizard.exe", "WizardGUI.exe"):
        p = os.path.join(WIZARD_DIR, exe)
        if os.path.isfile(p):
            return p
    raise FileNotFoundError("PhotoMesh Wizard executable not found")

try:  # pragma: no cover - environment specific
    WIZARD_EXE = _find_wizard_exe()
except FileNotFoundError:  # pragma: no cover - missing install
    WIZARD_EXE = os.path.join(WIZARD_DIR, "PhotoMeshWizard.exe")

# -------------------- tiny JSON helpers --------------------
def _load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _atomic_write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path), suffix=".tmp",
                               dir=os.path.dirname(path))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)

def _save_json(path: str, obj: dict) -> None:
    _atomic_write(path, json.dumps(obj, indent=2))

# -------------------- Offline / network configuration --------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")
config = configparser.ConfigParser()
config.read(CONFIG_PATH)

WIZARD_USER_CFG = os.path.join(
    os.environ.get("APPDATA", ""), "Skyline", "PhotoMesh", "Wizard", "config.json"
)

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

def get_offline_cfg() -> dict:
    try:
        config.read(CONFIG_PATH)
    except Exception:
        pass
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
    host = o["host_ip"] if o.get("use_ip_unc") else o["host_name"]
    return rf"\\\\{host}\\{o['share_name']}"

def working_fuser_unc(o: dict) -> str:
    return os.path.join(build_unc(o), o["working_fuser_subdir"])

def resolve_network_working_folder_from_cfg(o: dict) -> str:
    base = o["host_ip"] if o.get("use_ip_unc") else o["host_name"]
    return rf"\\{base}\{o['share_name']}\{o['working_fuser_subdir']}"

def ensure_offline_share_exists(log=print) -> None:
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
Get-NetFirewallRule -DisplayGroup 'File and Printer Sharing' | Where-Object {{$_ .Profile -like '*Private*'}} | Enable-NetFirewallRule | Out-Null
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

def open_in_explorer(path: str) -> None:
    try:
        os.startfile(path)
    except Exception as e:
        if messagebox:
            messagebox.showerror("Open Folder", f"Failed to open:\n{path}\n\n{e}")

def replace_share_in_unc_path(p: str, old_share: str, new_share: str) -> str:
    if not p or not p.startswith("\\\\"):
        return p
    parts = p.split("\\")
    if len(parts) >= 4 and parts[3].lower() == old_share.lower():
        parts[3] = new_share
        return "\\".join(parts)
    return p

def propagate_share_rename_in_config(old_share: str, new_share: str) -> None:
    changed = False
    try:
        config.read(CONFIG_PATH)
    except Exception:
        pass
    for sect in config.sections():
        for key, val in list(config[sect].items()):
            if isinstance(val, str) and val.startswith("\\\\"):
                new_val = replace_share_in_unc_path(val, old_share, new_share)
                if new_val != val:
                    config[sect][key] = new_val
                    changed = True
    if changed:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            config.write(f)
    wiz = _load_json(WIZARD_INSTALL_CFG)
    if wiz:
        nwf = wiz.get("NetworkWorkingFolder", "")
        if isinstance(nwf, str) and nwf.startswith("\\\\"):
            new_nwf = replace_share_in_unc_path(nwf, old_share, new_share)
            if new_nwf != nwf:
                wiz["NetworkWorkingFolder"] = new_nwf
                _save_json(WIZARD_INSTALL_CFG, wiz)

# -------------------- “modify only if key exists” patcher --------------------
def _patch_existing(d: dict, path: list[str], value) -> bool:
    """
    Follow 'path' without creating new keys; set the leaf only if it exists.
    Returns True if a change was applied.
    """
    cur = d
    for k in path[:-1]:
        if not isinstance(cur, dict) or k not in cur or not isinstance(cur[k], dict):
            return False
        cur = cur[k]
    leaf = path[-1]
    if isinstance(cur, dict) and leaf in cur and cur[leaf] != value:
        cur[leaf] = value
        return True
    return False

# -------------------- Write Wizard config (minimal, no new keys) --------------------
def enforce_wizard_install_config(
    *, model3d: bool = True, obj: bool = True, d3dml: bool = False, ortho_ui: bool = True,
    center_pivot: bool = True, ellipsoid: bool = True, fuser_unc: Optional[str] = None, log=print
) -> None:
    """
    Edit ONLY existing keys in <Wizard>\\config.json:
      DefaultPhotoMeshWizardUI.OutputProducts.Model3D = True
      DefaultPhotoMeshWizardUI.OutputProducts.Ortho   = ortho_ui (UI-only)
      DefaultPhotoMeshWizardUI.Model3DFormats.OBJ     = obj
      DefaultPhotoMeshWizardUI.Model3DFormats.3DML    = d3dml
      DefaultPhotoMeshWizardUI.CenterPivotToProject   = center_pivot
      DefaultPhotoMeshWizardUI.ReprojectToEllipsoid   = ellipsoid
      NetworkWorkingFolder = fuser_unc (if provided)
    """
    cfg = _load_json(WIZARD_INSTALL_CFG)
    changed = False
    changed |= _patch_existing(cfg, ["DefaultPhotoMeshWizardUI","OutputProducts","Model3D"], bool(model3d))
    changed |= _patch_existing(cfg, ["DefaultPhotoMeshWizardUI","OutputProducts","Ortho"],   bool(ortho_ui))
    changed |= _patch_existing(cfg, ["DefaultPhotoMeshWizardUI","Model3DFormats","OBJ"],     bool(obj))
    changed |= _patch_existing(cfg, ["DefaultPhotoMeshWizardUI","Model3DFormats","3DML"],    bool(d3dml))
    changed |= _patch_existing(cfg, ["DefaultPhotoMeshWizardUI","CenterPivotToProject"],     bool(center_pivot))
    changed |= _patch_existing(cfg, ["DefaultPhotoMeshWizardUI","ReprojectToEllipsoid"],     bool(ellipsoid))

    if fuser_unc and isinstance(cfg, dict):
        # Allow write if the key exists at root (don’t inject new trees)
        if "NetworkWorkingFolder" in cfg and cfg["NetworkWorkingFolder"] != fuser_unc:
            cfg["NetworkWorkingFolder"] = fuser_unc
            changed = True

    if changed:
        _save_json(WIZARD_INSTALL_CFG, cfg)
        log(f"Wizard config updated: {WIZARD_INSTALL_CFG}")

# -------------------- Preset staging (Program Files + Wizard) --------------------
def stage_install_preset(repo_preset_path: str, preset_name: str, log=print) -> None:
    """
    Copy a .PMPreset to both Program Files preset folders and AppData fallback.
    No XML rewriting here; assume repo preset already encodes OBJ-only + pivot + ellipsoid.
    """
    if not os.path.isfile(repo_preset_path):
        raise FileNotFoundError(repo_preset_path)

    if not repo_preset_path.lower().endswith(".pmpreset"):
        raise ValueError("Preset must be a .PMPreset")

    targets = [
        os.path.join(r"C:\\Program Files\\Skyline\\PhotoMesh\\Presets", f"{preset_name}.PMPreset"),
        os.path.join(WIZARD_DIR, "Presets", f"{preset_name}.PMPreset"),  # Wizard Presets
        os.path.join(os.environ.get("APPDATA",""), "Skyline","PhotoMesh","Presets", f"{preset_name}.PMPreset"),
    ]
    for dst in targets:
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(repo_preset_path, dst)
            log(f"Staged preset -> {dst}")
        except Exception as e:
            log(f"Skipping preset copy to {dst}: {e}")

# -------------------- User config helpers --------------------
def ensure_wizard_user_defaults(preset: str = "", autostart: bool = True) -> None:
    cfg = {
        "SelectedPreset": preset,
        "OverrideSettings": True,
        "AutoBuild": bool(autostart),
    }
    _save_json(WIZARD_USER_CFG, cfg)

def enforce_photomesh_settings(preset: str = "", autostart: bool = True) -> None:
    o = get_offline_cfg()
    fuser_unc = resolve_network_working_folder_from_cfg(o)
    enforce_wizard_install_config(fuser_unc=fuser_unc)
    ensure_wizard_user_defaults(preset=preset, autostart=autostart)

# -------------------- Launch Wizard with preset --------------------
def launch_wizard_with_preset(
    project_name: str,
    project_path: str,
    imagery_folders: Iterable[str],
    *,
    preset: Optional[str] = None,
    autostart: bool = True,
    fuser_unc: Optional[str] = None,
    log=print,
) -> subprocess.Popen:
    """
    Start PhotoMesh Wizard with --overrideSettings, optional --preset and --autostart.
    Before launch, ensure UI seeds won’t block startup (Ortho ON in UI; 3DML OFF; OBJ ON).
    """
    try:
        enforce_wizard_install_config(
            model3d=True, obj=True, d3dml=False, ortho_ui=True,
            center_pivot=True, ellipsoid=True, fuser_unc=fuser_unc, log=log
        )
    except PermissionError:
        log("⚠️ Could not update install config (permission). Continuing.")

    args = [
        WIZARD_EXE,
        "--projectName", project_name,
        "--projectPath", project_path,
        "--overrideSettings",
    ]
    if preset:
        args += ["--preset", preset]
    if autostart:
        args += ["--autostart"]
    for f in imagery_folders or []:
        args += ["--folder", f]

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(args, cwd=WIZARD_DIR, creationflags=creationflags)
