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
import subprocess
import sys
import time
from typing import Iterable
import re

try:  # pragma: no cover - optional Win32 API
    import win32api  # type: ignore
except Exception:  # pragma: no cover - win32api may be absent off Windows
    win32api = None  # type: ignore

try:  # pragma: no cover - optional dependency
    import requests  # type: ignore
except Exception:  # pragma: no cover - requests may be absent in minimal environments
    requests = None  # type: ignore

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
WORKING_FOLDER = r"C:\\WorkingFolder"

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
    """Ensure the offline share exists, firewall rules allow access, and a sentinel file is present."""
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
    _touch(os.path.join(root, "Datatarget.txt"))


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


# --- Easy Shared Drive Mapping ------------------------------------------------

def list_remote_shares(host: str) -> list[str]:
    r"""Return share names available on ``\\\{host}``.

    Uses ``net view`` first, falling back to PowerShell ``Get-SmbShare``. Any
    errors are swallowed and an empty list is returned if the host cannot be
    queried. Duplicate names are removed case-insensitively.
    """
    if not is_windows():
        return []
    names: list[str] = []
    try:
        r = subprocess.run(
            ["cmd", "/c", "net", "view", rf"\\\\{host}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in r.stdout.splitlines():
            m = re.match(r"^\s{2}([A-Za-z0-9$._-]+)\s", line)
            if m:
                names.append(m.group(1))
    except Exception:
        pass
    if not names:
        try:
            ps = (
                f"try{{(Get-SmbShare -CimSession '{host}' | Select-Object -ExpandProperty Name) -join ','}}catch{{''}}"
            )
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.stdout.strip():
                names.extend([n.strip() for n in r.stdout.strip().split(",") if n.strip()])
        except Exception:
            pass
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        k = n.lower()
        if k not in seen:
            seen.add(k)
            out.append(n)
    return out


def pick_mesh_share(
    host: str,
    share_hint: str,
    working_subdir: str,
    sentinels: tuple[str, ...] = ("Datatarget.txt",),
) -> str | None:
    """Return the most plausible mesh share name on *host* or ``None``."""
    candidates: list[str] = []
    if share_hint:
        candidates.append(share_hint)
    candidates += ["SharedMeshDrive", "Mesh", "Shared", "Data"]
    candidates += list_remote_shares(host)

    tried: set[str] = set()
    for share in candidates:
        if not share or share.lower() in tried:
            continue
        tried.add(share.lower())
        unc = rf"\\\\{host}\\{share}"
        if not can_access_unc(unc):
            continue
        try:
            if any(os.path.isfile(os.path.join(unc, s)) for s in sentinels):
                return share
            if os.path.isdir(os.path.join(unc, working_subdir)):
                return share
            if os.path.isdir(os.path.join(unc, "WorkingFuser")):
                return share
        except Exception:
            continue
    return None


def auto_fix_share_name(log=print) -> bool:
    """Attempt to repair the Offline.share_name if the current UNC is unreachable."""
    o = get_offline_cfg()
    base = o["host_ip"] if o.get("use_ip_unc") else o["host_name"]
    current_unc = resolve_network_working_folder_from_cfg(o)
    if can_access_unc(current_unc):
        return False

    new_share = pick_mesh_share(base, o["share_name"], o["working_fuser_subdir"])
    if new_share and new_share.lower() != o["share_name"].lower():
        old_share = o["share_name"]
        try:
            config.read(CONFIG_PATH)
            if "Offline" not in config:
                config["Offline"] = {}
            config["Offline"]["share_name"] = new_share
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                config.write(f)
            propagate_share_rename_in_config(old_share, new_share)
            log(f"[Offline] Share repaired: {old_share} -> {new_share}")
            return True
        except Exception as e:
            log(f"[Offline] Failed to write repaired share: {e}")
    return False


def _touch(path: str) -> None:
    """Create *path* if it doesn't exist."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8"):
            pass
    except Exception:
        pass


def choose_drive_letter(preferred: str = "M:") -> str | None:
    """Return ``preferred`` or the next free drive letter on Windows."""
    if not is_windows():
        return preferred
    try:
        used = {
            d[:2].upper()
            for d in (win32api.GetLogicalDriveStrings().split("\x00") if win32api else [])
            if d
        }
    except Exception:
        used = set()
    pref = preferred.upper()
    if pref not in used:
        return pref
    for c in "MNOPQRSTUVWXYZ":
        if f"{c}:" not in used:
            return f"{c}:"
    return None


def map_network_drive(letter: str, unc: str, persistent: bool = True) -> bool:
    """Map *unc* to drive *letter* for the current user."""
    if not is_windows():
        return False
    try:
        subprocess.run(
            ["cmd", "/c", "net", "use", letter, "/delete", "/y"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        args = ["cmd", "/c", "net", "use", letter, unc]
        args.append("/persistent:yes" if persistent else "/persistent:no")
        r = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def unmap_drive(letter: str) -> None:
    if not is_windows():
        return
    try:
        subprocess.run(
            ["cmd", "/c", "net", "use", letter, "/delete", "/y"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        pass


def ensure_mapped_drive_from_cfg(o: dict, preferred: str = "M:") -> str | None:
    r"""Map ``\\host\share`` from offline config *o* and return the drive letter."""
    if not is_windows():
        return None
    unc = build_unc_from_cfg(o)
    letter = choose_drive_letter(preferred) or preferred
    if not can_access_unc(unc):
        return None
    if map_network_drive(letter, unc, persistent=True):
        return letter
    return None


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
]

# =============================================================================
# Refactor Notes
# - Reorganized functions into labeled sections with docstrings.
# - Added table of contents and region markers for editor folding.
# =============================================================================

