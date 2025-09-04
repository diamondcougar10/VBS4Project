# =============================================================================
# Project: VBS4Project
# File: photomesh_launcher.py
# Purpose: Helpers for configuring and launching PhotoMesh/Wizard utilities
# =============================================================================
# Table of Contents
#   1) Imports
#   2) Constants & Configuration
#   3) Paths & Environment
#   4) Data Models / Types (if any)
#   5) Utilities (pure helpers, no I/O)
#   6) File I/O & JSON helpers
#   7) Wizard Config (read/patch install config)
#   8) Network / UNC resolution
#   9) Launch / CLI argument builders
#  10) GUI / Tkinter handlers
#  11) Logging & Error handling
#  12) Main entry point
# =============================================================================

# region Imports
from __future__ import annotations

import configparser
import ctypes
import json
import os
import socket
import subprocess
import sys
import time
from typing import Iterable, List

try:  # pragma: no cover - optional dependency
    import requests  # type: ignore
except Exception:  # pragma: no cover - requests may be absent in minimal environments
    requests = None  # type: ignore

try:  # pragma: no cover - psutil may not be installed
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None  # type: ignore

try:  # pragma: no cover - tkinter may not be available
    from tkinter import messagebox
except Exception:  # pragma: no cover - headless/test environments
    messagebox = None
# endregion

# region Constants & Configuration
# Authoritative Wizard locations
WIZARD_DIR = r"C:\\Program Files\\Skyline\\PhotoMeshWizard"
WIZARD_EXE = rf"{WIZARD_DIR}\\PhotoMeshWizard.exe"

# PhotoMesh Wizard install config (read by Wizard at startup)
WIZ_CFG_PATHS = [
    r"C:\\Program Files\\Skyline\\PhotoMeshWizard\\config.json",
    r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard\\config.json",
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")

# Queue endpoints and working directory used by the PhotoMesh engine
QUEUE_API_URL = "http://127.0.0.1:8087/ProjectQueue/"
QUEUE_SSE_URL = "http://127.0.0.1:8087/ProjectQueue/events"
QUEUE_HOST = "127.0.0.1"
QUEUE_PORT = 8087
WORKING_FOLDER = r"C:\\WorkingFolder"

PHOTOMESH_EXE = r"C:\\Program Files\\Skyline\\PhotoMesh\\PhotoMesh.exe"
QUEUE_READY_TIMEOUT_SEC = 90

# Off-line connection hint shown when UNC paths fail
OFFLINE_ACCESS_HINT = (
    "Cannot access the shared working folder.\n\n"
    "Connect all PCs to the same switch, assign static IPs (e.g., host 192.168.50.10, "
    "clients 192.168.50.11-13, mask 255.255.255.0), ensure the same Workgroup "
    "(e.g., WORKGROUP), share the local_data_root on the host as share_name with "
    "read/write permissions, and if name resolution fails, enable use_ip_unc or add "
    "host_name to C:\\Windows\\System32\\drivers\\etc\\hosts."
)
# endregion

# region Paths & Environment
# Shared configuration for network fuser settings
config = configparser.ConfigParser()
config.read(CONFIG_PATH)
# endregion

# region Data Models / Types
# None defined.
# endregion

# region Utilities
def is_windows() -> bool:
    """Return ``True`` if running on a Windows platform."""
    return os.name == "nt"


def is_admin() -> bool:
    """Check if the current process has administrative privileges."""
    if not is_windows():
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def _program_files_candidates():
    """Yield possible Program Files roots (32 & 64-bit)."""
    pf = os.environ.get("ProgramFiles")
    pf86 = os.environ.get("ProgramFiles(x86)")
    for base in (pf, pf86):
        if base:
            yield base
# endregion

# region File I/O & JSON helpers
def _load_json(path: str) -> dict:
    """Load JSON data from *path* or return an empty dict on error."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json(path: str, data: dict) -> None:
    """Atomically write JSON *data* to *path*."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _save_config() -> None:
    """Persist the in-memory config.ini to disk."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)


def get_projects_root() -> str:
    """Return the configured projects_root path or an empty string."""
    try:
        root = config.get("Paths", "projects_root", fallback="").strip()
        return root
    except Exception:
        return ""


def set_projects_root(path: str) -> None:
    """Update the projects_root path in config.ini."""
    if not config.has_section("Paths"):
        config.add_section("Paths")
    config.set("Paths", "projects_root", path)
    _save_config()
# endregion

# region Wizard Config
def apply_minimal_wizard_defaults() -> None:
    """
    Ensure install-level Wizard defaults enable 3D model OBJ (+3DML).
    Non-destructive: only sets required keys; no presets touched.
    """
    for cfg_path in WIZ_CFG_PATHS:
        if not os.path.isfile(cfg_path):
            continue
        cfg = _load_json(cfg_path)
        ui = cfg.setdefault("DefaultPhotoMeshWizardUI", {})
        ui.setdefault("OutputProducts", {}).update({"Model3D": True})
        m3d = ui.setdefault("Model3DFormats", {})
        m3d["3DML"] = True
        m3d["OBJ"] = True
        # Optional:
        # m3d["LAS"] = True
        _save_json(cfg_path, cfg)
        print(f"[Wizard] Ensured Model3D/OBJ/3DML enabled -> {cfg_path}")
# endregion

# region Network / UNC resolution
def _read_photomesh_host() -> str:
    """Resolve the PhotoMesh host from config.ini settings."""
    try:
        config.read(CONFIG_PATH)
        if config.has_section("Offline"):
            for key in (
                "working_fuser_host",
                "host_name",
                "network_host",
                "fuser_host",
            ):
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
    """UNC path to the WorkingFuser subfolder."""
    return os.path.join(working_share_root(), "WorkingFuser")


def _is_offline_enabled() -> bool:
    """Return True if offline mode is enabled in config.ini."""
    try:
        config.read(CONFIG_PATH)
        return config.getboolean("Offline", "enabled", fallback=False)
    except Exception:
        return False


def get_offline_cfg() -> dict:
    """Return Offline section settings with defaults applied."""
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
        "local_data_root": os.path.normpath(
            o.get("local_data_root", r"D:\\SharedMeshDrive")
        ),
        "working_fuser_subdir": o.get("working_fuser_subdir", "WorkingFuser").strip(),
        "use_ip_unc": o.getboolean("use_ip_unc", False),
    }


def build_unc_from_cfg(o: dict) -> str:
    """Build a UNC path to the shared drive from offline config dict *o*."""
    host = o["host_ip"] if o.get("use_ip_unc") else o["host_name"]
    return rf"\\\\{host}\\{o['share_name']}"


def working_fuser_unc_from_cfg(o: dict) -> str:
    """Return UNC path to WorkingFuser based on offline config dict *o*."""
    return os.path.join(build_unc_from_cfg(o), o["working_fuser_subdir"])


def resolve_network_working_folder_from_cfg(o: dict) -> str:
    """Resolve the network working folder UNC from config dict *o*."""
    base = o["host_ip"] if o.get("use_ip_unc") else o["host_name"]
    return rf"\\{base}\{o['share_name']}\{o['working_fuser_subdir']}"


def ensure_offline_share_exists(log=print) -> None:
    """Ensure the offline share exists and firewall rules allow access."""
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
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            check=False,
        )
        log(f"Offline share ensured: \\\\{o['host_name']}\\{share}  ({root})")
    except Exception as e:
        log(
            f"Could not run PowerShell to ensure share: {e}\nPlease share {root} as '{share}' manually."
        )


def can_access_unc(path: str) -> bool:
    """Return True if *path* is an accessible directory."""
    try:
        return os.path.isdir(path) and os.listdir(path) is not None
    except Exception:
        return False


def replace_share_in_unc_path(p: str, old_share: str, new_share: str) -> str:
    """Replace ``old_share`` with ``new_share`` in UNC path *p* if present."""
    if not p or not p.startswith("\\\\"):
        return p
    parts = p.split("\\")
    if len(parts) >= 4 and parts[3].lower() == old_share.lower():
        parts[3] = new_share
        return "\\".join(parts)
    return p


def propagate_share_rename_in_config(old_share: str, new_share: str) -> None:
    """Update config.ini entries to replace *old_share* with *new_share*."""
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


def enforce_photomesh_settings(autostart: bool = True, log=print) -> None:
    """Compatibility placeholder for enforcing PhotoMesh settings."""
    del autostart  # compatibility placeholder
    del log  # no-op; network/host propagation handled elsewhere
# endregion

# region Launch / CLI argument builders
def launch_wizard_new_project(
    project_name: str, project_path: str, folders, log=print
) -> subprocess.Popen:
    """
    Launch Wizard for a new project.
    - No presets passed.
    - Uses --overrideSettings so Build Settings honor our defaults.
    - *folders*: iterable of image folder paths.
    """
    args = [
        WIZARD_EXE,
        "--projectName",
        project_name,
        "--projectPath",
        project_path,
        "--autostart",
        "--overrideSettings",
    ]
    for f in folders or []:
        args += ["--folder", f]
    log(f"[Wizard] {' '.join(args)}")
    return subprocess.Popen(args, close_fds=False)


def find_wizard_exe() -> str:
    """Locate PhotoMesh Wizard executable under Program Files."""
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if not base:
            continue
        p = os.path.join(base, "Skyline", "PhotoMeshWizard", "PhotoMeshWizard.exe")
        if os.path.isfile(p):
            return p
        p2 = os.path.join(
            base, "Skyline", "PhotoMesh", "Tools", "PhotomeshWizard", "PhotoMeshWizard.exe"
        )
        if os.path.isfile(p2):
            return p2
    raise FileNotFoundError("PhotoMesh Wizard executable not found.")


def relaunch_self_as_admin() -> None:
    """Relaunch the current script with admin rights (UAC prompt)."""
    if not is_windows():
        return
    params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, f'"{sys.argv[0]}" {params}', None, 1
    )
    if rc <= 32:
        raise RuntimeError(f"Elevation failed, ShellExecuteW code: {rc}")


def run_exe_as_admin(
    exe_path: str, args: list[str] | None = None, cwd: str | None = None
):
    """Launch an external EXE with admin rights via ShellExecuteW('runas')."""
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
    """Run elevated process and wait for completion via PowerShell Start-Process."""
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


def launch_photomesh_admin() -> None:
    """Launch PhotoMesh.exe elevated without arguments."""
    pm_exe = r"C:\\Program Files\\Skyline\\PhotoMesh\\PhotoMesh.exe"
    run_exe_as_admin(pm_exe, [])


def find_photomesh_exe() -> str:
    """Locate PhotoMesh.exe (engine GUI)."""
    for base in _program_files_candidates():
        exe = os.path.join(base, "Skyline", "PhotoMesh", "PhotoMesh.exe")
        if os.path.isfile(exe):
            return exe
    raise FileNotFoundError("PhotoMesh.exe not found under Program Files.")


def queue_alive(timeout: float = 2.0) -> bool:
    """Return True if the Project Queue endpoint responds within *timeout*."""
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
    project_name: str, project_dir: str, image_folders: Iterable[str]
) -> list[dict]:
    """Build a Project Queue payload for *project_name* in *project_dir*."""
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
    """Submit *payload* to the Project Queue and start the build."""
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


def poll_queue_until_done(
    poll_every: int = 5, max_minutes: int = 120, log=print
) -> None:
    """Poll the Project Queue until completion or *max_minutes* expires."""
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

# =============================================================================
# PhotoMesh Project Queue integration (no Wizard)
# =============================================================================


def _is_listening(host: str, port: int, timeout_sec: float = 0.5) -> bool:
    """Return True if *host:port* accepts a TCP connection."""
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def _is_photomesh_running() -> bool:
    """Check whether PhotoMesh.exe is already running."""
    try:
        if psutil:
            for p in psutil.process_iter(["name", "exe"]):
                nm = (p.info.get("name") or "").lower()
                if nm == "photomesh.exe":
                    return True
    except Exception:
        pass
    try:
        out = subprocess.check_output(["tasklist"], text=True, stderr=subprocess.DEVNULL)
        return "PhotoMesh.exe" in out
    except Exception:
        return False


def launch_photomesh_main() -> subprocess.Popen | None:
    """Start PhotoMesh.exe if it isn't already running."""
    if _is_photomesh_running():
        return None
    if not os.path.isfile(PHOTOMESH_EXE):
        raise FileNotFoundError(f"PhotoMesh.exe not found at {PHOTOMESH_EXE}")
    return subprocess.Popen([PHOTOMESH_EXE], cwd=os.path.dirname(PHOTOMESH_EXE))


def wait_for_queue_ready(max_wait_sec: int = QUEUE_READY_TIMEOUT_SEC) -> bool:
    """Wait until the Project Queue TCP port is listening."""
    start = time.time()
    while time.time() - start < max_wait_sec:
        if _is_listening(QUEUE_HOST, QUEUE_PORT):
            return True
        time.sleep(1.0)
    return False


def make_source_path_from_folders(folders: List[str]) -> List[dict]:
    """
    Build the 'sourcePath' list for /project/add from the already-selected image folders.
    If subfolders contain JPG/JPEG, treat each subfolder as a collection; else use folder.
    """
    out: List[dict] = []
    for folder in folders or []:
        if not os.path.isdir(folder):
            continue
        subdirs = [d for d in os.listdir(folder) if os.path.isdir(os.path.join(folder, d))]
        collections = []
        if subdirs:
            for s in subdirs:
                p = os.path.join(folder, s)
                try:
                    has_jpg = any(fn.lower().endswith((".jpg", ".jpeg")) for fn in os.listdir(p))
                except Exception:
                    has_jpg = False
                if has_jpg:
                    collections.append({"name": s, "path": p, "properties": ""})
        if not collections:
            collections = [{"name": "RGB", "path": folder, "properties": ""}]
        out.extend(collections)
    return out


def build_queue_payload(
    project_name: str,
    project_dir: str,
    source_path: List[dict],
    working_folder: str,
    preset_name: str | None = None,
) -> list[dict]:
    """
    Create /project/add payload. If preset_name is None/empty, engine defaults apply.
    """
    os.makedirs(project_dir, exist_ok=True)
    project_xml = os.path.join(project_dir, f"{project_name}.PhotoMeshXML")
    return [{
        "comment": f"Auto project: {project_name}",
        "action": 0,
        "projectPath": project_xml,
        "buildFrom": 1,
        "buildUntil": 6,
        "inheritBuild": "",
        "preset": preset_name or "",
        "workingFolder": working_folder,
        "MaxLocalFusers": 10,
        "MaxAWSFusers": 0,
        "AWSFuserStartupScript": "",
        "AWSBuildConfigurationName": "",
        "AWSBuildConfigurationJsonPath": "",
        "sourceType": 0,
        "sourcePath": source_path
    }]


def submit_project_to_queue(payload: list[dict], log=print) -> None:
    """POST /project/add and raise on failure."""
    if not requests:
        raise RuntimeError("requests library is required for queue submission")
    r = requests.post(QUEUE_API_URL + "project/add", json=payload, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"/project/add failed [{r.status_code}]: {r.text}")
    log("Submitted project to Project Queue.")


def start_build(log=print) -> None:
    """GET /Build/Start and raise on failure."""
    if not requests:
        raise RuntimeError("requests library is required for queue submission")
    r = requests.get(QUEUE_API_URL + "Build/Start", timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"/Build/Start failed [{r.status_code}]: {r.text}")
    log("Build started.")


# =============================================================================
# Optional: engine preset staging (only if you WANT to use a preset by name)
# =============================================================================
import shutil
import xml.etree.ElementTree as ET

ENGINE_PRESET_DIR = r"C:\\Program Files\\Skyline\\PhotoMesh\\Presets"


def _read_preset_name(pmpreset_path: str) -> str:
    try:
        root = ET.parse(pmpreset_path).getroot()
        n = root.find(".//PresetName")
        if n is not None and (n.text or "").strip():
            return n.text.strip()
    except Exception:
        pass
    return os.path.splitext(os.path.basename(pmpreset_path))[0]


def install_engine_preset(pmpreset_path: str, log=print) -> str:
    """Copy .PMPreset into engine Presets so 'preset' resolves by name in /project/add."""
    if not os.path.isfile(pmpreset_path):
        raise FileNotFoundError(pmpreset_path)
    if not pmpreset_path.lower().endswith(".pmpreset"):
        raise ValueError("Expected a .PMPreset file")

    name = _read_preset_name(pmpreset_path)
    dst = os.path.join(ENGINE_PRESET_DIR, f"{name}.PMPreset")

    try:
        os.makedirs(ENGINE_PRESET_DIR, exist_ok=True)
        if not os.path.isfile(dst) or os.path.getmtime(pmpreset_path) > os.path.getmtime(dst):
            shutil.copy2(pmpreset_path, dst)
            log(f"Installed engine preset → {dst}")
        else:
            log(f"Engine preset already up to date → {dst}")
    except PermissionError as e:
        raise PermissionError(
            f"Cannot copy preset to '{ENGINE_PRESET_DIR}'. "
            f"Run once as Administrator or copy manually."
        ) from e
    return name


def queue_build_from_gui_selection(
    project_name: str,
    project_dir: str,
    image_folders: List[str],
    working_folder: str,
    preset_src: str | None = None,
    log=print,
) -> None:
    """
    Do not change GUI. Build payload from current selection, submit, and start build.
    Assumes PhotoMesh is already running and the Project Queue is ready.
    """
    src = make_source_path_from_folders(image_folders)
    if not src:
        raise ValueError("No valid imagery found for sourcePath.")

    preset_name = None
    if preset_src:
        preset_name = install_engine_preset(preset_src, log=log)

    payload = build_queue_payload(project_name, project_dir, src, working_folder, preset_name)
    submit_project_to_queue(payload, log=log)
    start_build(log=log)
# endregion

# region GUI / Tkinter handlers
def open_in_explorer(path: str) -> None:
    """Open *path* in Windows Explorer; show a messagebox on failure."""
    try:
        os.startfile(path)
    except Exception as e:
        if messagebox:
            messagebox.showerror("Open Folder", f"Failed to open:\n{path}\n\n{e}")
# endregion

# region Logging & Error handling
# No centralized logging helpers defined.
# endregion

# region Main entry point
# No executable entry point in this module.
# endregion

__all__ = [
    "set_wizard_defaults_exact",
    "launch_wizard_new_project",
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
    "submit_queue_build",
    "poll_queue_until_done",
    "queue_build_from_gui_selection",
    "launch_photomesh_main",
    "wait_for_queue_ready",
    "make_source_path_from_folders",
    "build_queue_payload",
    "submit_project_to_queue",
    "start_build",
    "install_engine_preset",
]

# =============================================================================
# Refactor Notes
# - Reorganized functions into labeled sections with docstrings.
# - Added table of contents and region markers for editor folding.
# =============================================================================

