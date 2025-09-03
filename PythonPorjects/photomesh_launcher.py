from __future__ import annotations
import os, sys, json, subprocess, tempfile, configparser, ctypes, time, uuid, socket
from typing import Iterable

try:  # pragma: no cover - optional dependency
    import requests  # type: ignore
except Exception:  # pragma: no cover - requests may be absent in minimal environments
    requests = None  # type: ignore

try:  # pragma: no cover - tkinter may not be available
    from tkinter import messagebox
except Exception:  # pragma: no cover - headless/test environments
    messagebox = None

# Load shared configuration for network fuser settings
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")

# Queue endpoints and working directory used by the PhotoMesh engine
QUEUE_API_URL = "http://127.0.0.1:8087/ProjectQueue/"
QUEUE_SSE_URL = "http://127.0.0.1:8087/ProjectQueue/events"
WORKING_FOLDER = r"C:\\WorkingFolder"

# --- Wizard helpers ---------------------------------------------------------
def find_wizard_dir() -> str:
    candidates = [
        r"C:\\Program Files\\Skyline\\PhotoMeshWizard",
        r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard",
    ]
    for d in candidates:
        if os.path.isdir(d):
            return d
    return candidates[0]


def find_wizard_exe() -> str:
    d = find_wizard_dir()
    for exe in ("PhotoMeshWizard.exe", "WizardGUI.exe"):
        p = os.path.join(d, exe)
        if os.path.isfile(p):
            return p
    raise FileNotFoundError("PhotoMesh Wizard executable not found.")


def user_wizard_config_path() -> str:
    la = os.environ.get("LOCALAPPDATA", "")
    path = os.path.join(la, "Skyline", "PhotoMesh", "PhotomeshWizard", "config.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _set_bool(d: dict, key: str, value: bool):
    d[key] = bool(value)


def _ensure_dict(root: dict, key: str) -> dict:
    node = root.get(key)
    if not isinstance(node, dict):
        node = {}
        root[key] = node
    return node


def get_host_from_ini(config_ini_path: str) -> str:
    import configparser, os
    host = "KIT1-1"
    cfg = configparser.ConfigParser()
    try:
        if os.path.isfile(config_ini_path):
            cfg.read(config_ini_path)
            if cfg.has_option("Fusers", "working_folder_host"):
                host = cfg.get("Fusers", "working_folder_host").strip() or host
            elif cfg.has_option("General", "host"):
                host = cfg.get("General", "host").strip() or host
    except Exception:
        pass
    return host


def merge_wizard_defaults(config_ini_path: str, log=print) -> list[str]:
    """
    Non-destructive (merge-only) update of Wizard config.json:
      - Force OutputProducts / Model3DFormats to desired values
      - Enable center-to-project + ellipsoid flags
      - Set NetworkWorkingFolder from host/config.ini
    Writes to:
      * Install-level config (if present & writable)
      * Per-user config in %LOCALAPPDATA%
    No .bak/.bk files are created; atomic replace is used.
    Returns: list of config paths updated.
    """
    # Targets: install (new + legacy) + per-user
    targets = []
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            p1 = os.path.join(base, "Skyline", "PhotoMeshWizard", "config.json")
            p2 = os.path.join(base, "Skyline", "PhotoMesh", "Tools", "PhotomeshWizard", "config.json")
            if os.path.isfile(p1): targets.append(p1)
            if os.path.isfile(p2): targets.append(p2)
    la = os.environ.get("LOCALAPPDATA", "")
    if la:
        user_cfg = os.path.join(la, "Skyline", "PhotoMesh", "PhotomeshWizard", "config.json")
        os.makedirs(os.path.dirname(user_cfg), exist_ok=True)
        targets.append(user_cfg)

    # Resolve network working folder from config.ini / hostname
    host = get_host_from_ini(config_ini_path) or (os.environ.get("COMPUTERNAME") or socket.gethostname())
    nwf  = rf"\\{host}\SharedMeshDrive\WorkingFuser"

    updated = []
    for path in targets:
        try:
            cfg = _load_json(path)

            ui   = _ensure_dict(cfg, "DefaultPhotoMeshWizardUI")
            outs = _ensure_dict(ui,  "OutputProducts")
            fmts = _ensure_dict(ui,  "Model3DFormats")

            # Force the few keys we care about
            _set_bool(outs, "Model3D", True)
            _set_bool(outs, "Ortho",   False)
            _set_bool(outs, "DSM",     False)
            _set_bool(outs, "DTM",     False)
            _set_bool(outs, "LAS",     True)

            # Skyline advised: keep 3DML ON so OBJ exports with center-to-project applied
            _set_bool(fmts, "3DML", True)
            _set_bool(fmts, "OBJ",  True)
            # Optional: keep SLPK as you prefer; leave untouched if already present

            _set_bool(ui, "CenterPivotToProject", True)
            _set_bool(ui, "CenterModelsToProject", True)
            _set_bool(ui, "ReprojectToEllipsoid", True)

            # Set NWF (top-level)
            cfg["NetworkWorkingFolder"] = nwf

            _atomic_write_json(path, cfg)
            log(f"✅ Wizard config merged → {path}")
            updated.append(path)
        except PermissionError as e:
            log(f"⚠️ Permission denied writing {path} (run as Admin). {e}")
        except Exception as e:
            log(f"⚠️ Failed merging {path}: {e}")
    if not updated:
        log("❌ No wizard config updated; run elevated and ensure Wizard is closed.")
    return updated


def clear_user_overrides(log=print):
    p = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Skyline", "PhotoMesh", "PhotomeshWizard", "config.json")
    if not os.path.isfile(p):
        return
    try:
        with open(p, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k in (
            "SelectedPreset",
            "SelectedPresets",
            "Selected Presets",
            "PresetOverrides",
            "LastPresetOverrides",
            "PresetStack",
            "SelectedPresetNames",
            "OverrideSettings",
        ):
            if k in cfg:
                cfg.pop(k, None)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        log("🧹 Cleared per-user override history.")
    except Exception as e:
        log(f"⚠️ Could not clear user overrides: {e}")

def launch_wizard_ui_override(project_name, project_path, image_folders, autostart=True, log=print):
    wd = find_wizard_exe()
    os.makedirs(project_path, exist_ok=True)
    args = [wd, "--projectName", project_name, "--projectPath", project_path, "--overrideSettings"]
    if autostart:
        args.append("--autostart")
    for folder in image_folders:
        args += ["--folder", folder]
    log("[Wizard] Launch with UI overrides:\n" + " ".join([f'\"{a}\"' if " " in a else a for a in args]))
    import subprocess
    return subprocess.Popen(args, close_fds=False)


def _atomic_write_json(path: str, data: dict):
    tmp = f"{path}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)

def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def _files_equal_text(existing_path: str, new_text: str) -> bool:
    try:
        if not os.path.isfile(existing_path):
            return False
        with open(existing_path, "rb") as f:
            current = f.read()
        return current == new_text.encode("utf-8")
    except Exception:
        return False

# -------------------- Admin helpers --------------------
def is_windows() -> bool:
    return os.name == "nt"


def is_admin() -> bool:
    if not is_windows():
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def relaunch_self_as_admin() -> None:
    """
    Relaunch the current Python script with admin rights (UAC prompt).
    Returns immediately in the parent process; elevated child will start the GUI.
    """
    if not is_windows():
        return
    params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, f'"{sys.argv[0]}" {params}', None, 1
    )
    if rc <= 32:
        raise RuntimeError(f"Elevation failed, ShellExecuteW code: {rc}")


def run_exe_as_admin(exe_path: str, args: list[str] | None = None, cwd: str | None = None):
    """
    Launch an external EXE with admin rights. Uses ShellExecuteW('runas').
    Returns immediately (non-blocking).
    """
    if not is_windows():
        raise RuntimeError("Admin launch is only supported on Windows.")
    args = args or []
    argline = " ".join([f'"{a}"' for a in args])
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", exe_path, argline, cwd or None, 1
    )
    if rc <= 32:
        raise RuntimeError(f"Admin launch failed, ShellExecuteW code: {rc}")


def run_exe_as_admin_blocking(
    exe_path: str, args: list[str] | None = None, cwd: str | None = None
):
    """Alternative: run elevated and wait for completion via PowerShell Start-Process -Verb RunAs."""
    args = args or []
    argline = " ".join([f'"{a}"' for a in args])
    ps = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "Start-Process",
        f'"{exe_path}"',
        "-ArgumentList",
        f'"{argline}"',
        "-Verb",
        "RunAs",
        "-Wait",
    ]
    subprocess.run(ps, check=True, cwd=cwd or None)


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

# -------------------- User config helpers --------------------
def ensure_wizard_user_defaults(autostart: bool = True) -> None:
    cfg = {
        "AutoBuild": bool(autostart),
    }
    _save_json(WIZARD_USER_CFG, cfg)

def enforce_photomesh_settings(autostart: bool = True, log=print) -> None:
    merge_wizard_defaults(CONFIG_PATH, log=log)
    ensure_wizard_user_defaults(autostart=autostart)


# -------------------- Launch Wizard --------------------
def launch_wizard(
    project_name: str,
    project_path: str,
    imagery_folders: Iterable[str],
    *,
    autostart: bool = True,
    want_ortho: bool = False,
    log=print,
) -> subprocess.Popen:
    # Merge our minimal defaults before launch (no backups)
    merge_wizard_defaults(CONFIG_PATH, log=log)

    args = [WIZARD_EXE, "--projectName", project_name, "--projectPath", project_path, "--overrideSettings"]
    if autostart:
        args.append("--autostart")
    for f in imagery_folders or []:
        args += ["--folder", f]

    log(f"[Wizard] WIZARD_DIR: {WIZARD_DIR}")
    log(f"[Wizard] WIZARD_EXE: {WIZARD_EXE}")
    log(f"[Wizard] Launch cmd: {args}")

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(args, cwd=WIZARD_DIR, creationflags=creationflags)


def launch_photomesh_admin() -> None:
    """Launch PhotoMesh.exe elevated without arguments."""
    pm_exe = r"C:\\Program Files\\Skyline\\PhotoMesh\\PhotoMesh.exe"
    run_exe_as_admin(pm_exe, [])


# -------------------- Project Queue helpers --------------------
def _program_files_candidates():
    pf = os.environ.get("ProgramFiles")
    pf86 = os.environ.get("ProgramFiles(x86)")
    for base in (pf, pf86):
        if base:
            yield base


def find_photomesh_exe() -> str:
    """Locate PhotoMesh.exe (engine GUI)."""
    for base in _program_files_candidates():
        exe = os.path.join(base, "Skyline", "PhotoMesh", "PhotoMesh.exe")
        if os.path.isfile(exe):
            return exe
    raise FileNotFoundError("PhotoMesh.exe not found under Program Files.")



def queue_alive(timeout: float = 2.0) -> bool:
    """Check if the Project Queue endpoint is reachable."""
    if not requests:
        return False
    try:
        r = requests.get(QUEUE_API_URL, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def ensure_photomesh_queue_running(log=print, wait_seconds: int = 45) -> None:
    """Ensure PhotoMesh is running (as admin) and its Project Queue is alive."""
    if queue_alive():
        log("[Queue] Project Queue already reachable.")
        return

    exe = find_photomesh_exe()
    log(f"[PhotoMesh] Launching as Administrator: {exe}")
    try:
        run_exe_as_admin(exe, [])
    except Exception as e:
        raise RuntimeError(f"Failed to start PhotoMesh as admin: {e}")

    start = time.time()
    while time.time() - start < wait_seconds:
        if queue_alive():
            log("[Queue] Project Queue is up.")
            return
        time.sleep(1.5)
    raise TimeoutError(
        "Project Queue did not come up within the wait window. Open PhotoMesh and ensure the Queue service is enabled."
    )


def queue_payload(
    project_name: str,
    project_dir: str,
    image_folders: Iterable[str],
) -> list[dict]:
    project_xml = os.path.join(project_dir, f"{project_name}.PhotoMeshXML")
    os.makedirs(project_dir, exist_ok=True)
    source_path = [
        {"name": os.path.basename(p.rstrip(r"\\/")), "path": p, "properties": ""}
        for p in image_folders
    ]
    return [
        {
            "comment": f"Auto project: {project_name}",
            "action": 0,
            "projectPath": project_xml,
            "buildFrom": 1,
            "buildUntil": 6,
            "inheritBuild": "",
            "workingFolder": WORKING_FOLDER,
            "MaxLocalFusers": 8,
            "MaxAWSFusers": 0,
            "AWSFuserStartupScript": "",
            "AWSBuildConfigurationName": "",
            "AWSBuildConfigurationJsonPath": "",
            "sourceType": 0,
            "sourcePath": source_path,
        }
    ]


def submit_queue_build(payload: list[dict], log=print) -> None:
    if not requests:
        raise RuntimeError("requests library is required for queue submission")
    r = requests.post(f"{QUEUE_API_URL}project/add", json=payload, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"[Queue] Add failed: {r.status_code} {r.text[:300]}")
    log("[Queue] Project submitted.")

    r = requests.get(f"{QUEUE_API_URL}Build/Start", timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"[Queue] Build/Start failed: {r.status_code} {r.text[:300]}")
    log("[Queue] Build started.")


def poll_queue_until_done(poll_every: int = 5, max_minutes: int = 120, log=print) -> None:
    if not requests:
        log("[Queue] requests module missing; cannot monitor queue.")
        return
    end = time.time() + max_minutes * 60
    last = 0
    while time.time() < end:
        try:
            r = requests.get(f"{QUEUE_API_URL}", timeout=5)
            if r.status_code == 200:
                now = int(time.time())
                if now // 30 != last // 30:
                    log("[Queue] …still building")
                    last = now
        except Exception:
            pass
        time.sleep(poll_every)
    log("[Queue] Monitor window expired.")


__all__ = [
    "clear_user_overrides",
    "launch_wizard_ui_override",
    "get_offline_cfg",
    "ensure_offline_share_exists",
    "can_access_unc",
    "OFFLINE_ACCESS_HINT",
    "_is_offline_enabled",
    "propagate_share_rename_in_config",
    "open_in_explorer",
    "resolve_network_working_folder_from_cfg",
    "enforce_photomesh_settings",
    "find_wizard_exe",
    "merge_wizard_defaults",
]

