from __future__ import annotations
import os, sys, json, shutil, subprocess, tempfile, configparser, ctypes, time, uuid, socket
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
config = configparser.ConfigParser()
config.read(CONFIG_PATH)

# ---------- Host / UNC helpers (read from GUI Settings) ----------
def _read_photomesh_host() -> str:
    """
    Resolve the PhotoMesh 'host' from config.ini written by your GUI Settings.
    Checked keys (first one that exists & non-empty wins):
      [Offline] working_fuser_host | host_name | network_host | fuser_host
      [Network] host
    Fallback: 'KIT1-1'
    """
    try:
        config.read(CONFIG_PATH)
        if config.has_section("Offline"):
            for key in ("working_fuser_host", "host_name", "network_host", "fuser_host"):
                if config.has_option("Offline", key):
                    v = config.get("Offline", key).strip()
                    if v:
                        return v
        if config.has_section("Network") and config.has_option("Network", "host"):
            v = config.get("Network", "host").strip()
            if v:
                return v
    except Exception:
        pass
    return "KIT1-1"


def working_share_root() -> str:
    """UNC to the root share on the host (no hardcoded name)."""
    return rf"\\{_read_photomesh_host()}\SharedMeshDrive"


def working_fuser_unc() -> str:
    """UNC to the WorkingFuser subfolder (common pattern in your code)."""
    return os.path.join(working_share_root(), "WorkingFuser")

# NOTE: If you still have any old helpers that used COMPUTERNAME to build a UNC,
# delete them and use working_share_root()/working_fuser_unc() instead.

# Queue endpoints and working directory used by the PhotoMesh engine
QUEUE_API_URL = "http://127.0.0.1:8087/ProjectQueue/"
QUEUE_SSE_URL = "http://127.0.0.1:8087/ProjectQueue/events"
WORKING_FOLDER = r"C:\\WorkingFolder"

# PhotoMesh Wizard (fixed install path per environment)
WIZARD_EXE         = r"C:\\Program Files\\Skyline\\PhotoMeshWizard\\PhotoMeshWizard.exe"
WIZARD_INSTALL_CFG = r"C:\\Program Files\\Skyline\\PhotoMeshWizard\\config.json"
WIZARD_INSTALL_CFGS = [
    WIZARD_INSTALL_CFG,
    r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard\\config.json",
]


def _user_cfg_paths():
    paths = []
    app = os.environ.get("APPDATA", "")
    if app:
        paths.append(os.path.join(app, "Skyline", "PhotoMesh", "Wizard", "config.json"))
        paths.append(os.path.join(app, "Skyline", "PhotoMesh", "PhotomeshWizard", "config.json"))
    la = os.environ.get("LOCALAPPDATA", "")
    if la:
        paths.append(os.path.join(la, "Skyline", "PhotoMesh", "PhotomeshWizard", "config.json"))
    for p in paths:
        os.makedirs(os.path.dirname(p), exist_ok=True)
    return paths


def _ensure_dict(root: dict, key: str) -> dict:
    node = root.get(key)
    if not isinstance(node, dict):
        node = {}
        root[key] = node
    return node


def _load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _atomic_write_json(path: str, data: dict) -> None:
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".pmcfg.", dir=d, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise


STICKY_PRESET_KEYS = (
    "SelectedPreset",
    "SelectedPresets",
    "PresetStack",
    "LastUsedPreset",
    "PresetOverrides",
    "Preset",
)


def force_obj_defaults_and_clear_overrides(log=print) -> list[str]:
    """Write strict defaults and remove preset stickiness for the Wizard."""
    touched: list[str] = []
    targets = [p for p in WIZARD_INSTALL_CFGS if os.path.isfile(p)] + _user_cfg_paths()
    for cfg_path in targets:
        try:
            cfg = _load_json(cfg_path)

            removed_any = False
            for k in STICKY_PRESET_KEYS:
                if k in cfg:
                    cfg.pop(k, None)
                    removed_any = True

            ui = _ensure_dict(cfg, "DefaultPhotoMeshWizardUI")
            outs = _ensure_dict(ui, "OutputProducts")
            fmts = _ensure_dict(ui, "Model3DFormats")

            outs["Model3D"] = True
            outs["3DModel"] = True
            outs["Ortho"] = False
            outs["DSM"] = False
            outs["DTM"] = False
            outs["LAS"] = True

            fmts["OBJ"] = True
            fmts["3DML"] = True

            ui["CenterPivotToProject"] = True
            ui["CenterModelsToProject"] = True
            ui["ReprojectToEllipsoid"] = True

            cfg["NetworkWorkingFolder"] = working_fuser_unc()

            lower_app = os.environ.get("APPDATA", "").lower()
            lower_la = os.environ.get("LOCALAPPDATA", "").lower()
            if cfg_path.lower().startswith((lower_app, lower_la)):
                cfg["OverrideSettings"] = True
                cfg.setdefault("AutoBuild", True)

            _atomic_write_json(cfg_path, cfg)
            log(f"✅ Patched Wizard config → {cfg_path} (removed presets: {removed_any})")
            touched.append(cfg_path)
        except PermissionError as e:
            log(f"⚠️ Permission denied writing {cfg_path} (run as Admin). {e}")
        except Exception as e:
            log(f"⚠️ Failed writing {cfg_path}: {e}")
    return touched


def find_wizard_exe() -> str:
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if not base:
            continue
        p = os.path.join(base, "Skyline", "PhotoMeshWizard", "PhotoMeshWizard.exe")
        if os.path.isfile(p):
            return p
        p2 = os.path.join(base, "Skyline", "PhotoMesh", "Tools", "PhotomeshWizard", "PhotoMeshWizard.exe")
        if os.path.isfile(p2):
            return p2
    raise FileNotFoundError("PhotoMesh Wizard executable not found.")


def launch_wizard_with_defaults(
    project_name: str,
    project_path: str,
    folders: list[str],
    *,
    autostart: bool = True,
    log=print,
):
    force_obj_defaults_and_clear_overrides(log=log)
    exe = WIZARD_EXE
    args = [exe, "--projectName", project_name, "--projectPath", project_path, "--overrideSettings"]
    if autostart:
        args.append("--autostart")
    for f in folders:
        args += ["--folder", f]
    log("[Wizard] " + " ".join(f'\"{a}\"' if " " in a else a for a in args))
    return subprocess.Popen(args, cwd=os.path.dirname(exe), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def launch_photomesh_wizard(project_name: str, project_path: str, folders: Iterable[str]) -> subprocess.Popen:
    """Launch PhotoMesh Wizard with enforced OBJ defaults."""
    h = _read_photomesh_host()
    print(f"[PhotoMesh] Host from Settings: {h}")
    print(f"[PhotoMesh] WorkingFuser UNC: {working_fuser_unc()}")
    return launch_wizard_with_defaults(project_name, project_path, list(folders), autostart=True, log=print)

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

def build_unc_from_cfg(o: dict) -> str:
    host = o["host_ip"] if o.get("use_ip_unc") else o["host_name"]
    return rf"\\\\{host}\\{o['share_name']}"

def working_fuser_unc_from_cfg(o: dict) -> str:
    return os.path.join(build_unc_from_cfg(o), o["working_fuser_subdir"])

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
    for cfg_path in WIZARD_INSTALL_CFGS:
        wiz = _load_json(cfg_path)
        if wiz:
            nwf = wiz.get("NetworkWorkingFolder", "")
            if isinstance(nwf, str) and nwf.startswith("\\\\"):
                new_nwf = replace_share_in_unc_path(nwf, old_share, new_share)
                if new_nwf != nwf:
                    wiz["NetworkWorkingFolder"] = new_nwf
                    _atomic_write_json(cfg_path, wiz)


def enforce_photomesh_settings(autostart: bool = True, log=print) -> None:
    force_obj_defaults_and_clear_overrides(log=log)


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
    del want_ortho  # legacy param unused
    folders = list(imagery_folders or [])
    return launch_wizard_with_defaults(
        project_name,
        project_path,
        folders,
        autostart=autostart,
        log=log,
    )


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
    "force_obj_defaults_and_clear_overrides",
    "launch_wizard_with_defaults",
    "launch_photomesh_wizard",
    "launch_wizard",
    "working_share_root",
    "working_fuser_unc",
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
]

