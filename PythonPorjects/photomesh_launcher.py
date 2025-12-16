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
#   8) Wizard Presets & Output validation
#   9) Network / UNC resolution
#  10) Launch / CLI argument builders
#  11) GUI / Tkinter handlers
#  12) Logging & Error handling
#  13) Main entry point
# =============================================================================

# region Imports
from __future__ import annotations

import configparser
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import re
import socket
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable
import winreg  
import glob
import logging

try:  
    import requests  # type: ignore
except Exception:  # pragma: no cover - requests may be absent in minimal environments
    requests = None  # type: ignore

try:  # pragma: no cover - tkinter may not be available
    from tkinter import messagebox
except Exception:  # pragma: no cover - headless/test environments
    messagebox = None
# endregion

# Hide consoles for child processes on Windows
NO_WINDOW_FLAG = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def get_primary_ipv4() -> str:
    """Return primary IPv4 without showing any console."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


def migrate_hostname_to_ip_once():
    """
    One-time migration: if host_ip is blank and host_name exists,
    try to resolve hostname -> ip and persist. Set use_ip_unc=True.
    """
    if config is None:
        return  # Config not yet initialized

    o = get_offline_cfg()
    if "Offline" not in config:
        config["Offline"] = {}
    offline = config["Offline"]

    ip = (o.get("host_ip") or "").strip()
    hn = (o.get("host_name") or "").strip()
    changed = False
    if not ip and hn:
        try:
            resolved = socket.gethostbyname(hn)
            if resolved and resolved != "127.0.0.1":
                offline["host_ip"] = resolved
                changed = True
        except Exception:
            pass
    if offline.get("use_ip_unc", "True") != "True":
        offline["use_ip_unc"] = "True"
        changed = True
    if changed:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            config.write(f)

# region Constants & Configuration
# Authoritative Wizard locations
WIZARD_DIR = r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard"
WIZARD_EXE = rf"{WIZARD_DIR}\\PhotoMeshWizard.exe"

# PhotoMesh Wizard install config (read by Wizard at startup)
WIZ_CFG_PATHS = [
    r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard\\config.json",
    r"C:\\Program Files\\Skyline\\PhotoMeshWizard\\config.json",
]

# Accept both modern and legacy Wizard executables / locations
WIZARD_CANDIDATE_NAMES = ("PhotoMeshWizard.exe", "WizardGUI.exe")
WIZARD_CANDIDATE_SUBPATHS = (
    r"Skyline\PhotoMesh\Tools\PhotomeshWizard",
    r"Skyline\PhotoMeshWizard",
)


def _cache_wizard_exe(path: str) -> None:
    """Persist the resolved Wizard EXE to config.ini for next runs."""
    if "General" not in config:
        config["General"] = {}
    config["General"]["photomesh_wizard_exe"] = os.path.normpath(path)
    _save_config()


def _iter_uninstall_install_locations():
    """Yield InstallLocation folders from Uninstall registry entries that match Skyline/PhotoMesh."""
    keys = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key in keys:
            try:
                with winreg.OpenKey(hive, key) as root:
                    subcount = winreg.QueryInfoKey(root)[0]
                    for i in range(subcount):
                        try:
                            subname = winreg.EnumKey(root, i)
                            with winreg.OpenKey(root, subname) as sub:
                                disp = ""
                                loc = ""
                                try:
                                    disp, _ = winreg.QueryValueEx(sub, "DisplayName")
                                except OSError:
                                    pass
                                try:
                                    loc, _ = winreg.QueryValueEx(sub, "InstallLocation")
                                except OSError:
                                    pass
                                dlow = (disp or "").lower()
                                if ("photomesh" in dlow) or ("photo mesh" in dlow) or ("wizard" in dlow):
                                    if loc and os.path.isdir(loc):
                                        yield loc
                        except OSError:
                            continue
            except OSError:
                continue


def _program_files_roots():
    """Both 64/32-bit Program Files roots (covers C: or non-C: installs)."""
    seen = set()
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env, "").strip()
        if base and base not in seen and os.path.isdir(base):
            seen.add(base)
            yield base


def find_wizard_exe() -> str:
    """
    Return the best PhotoMesh Wizard executable path found on this machine.
    Order:
      1) config override (General/photomesh_wizard_exe)
      2) canonical + legacy subpaths in Program Files roots
      3) Uninstall registry InstallLocation
      4) recursive search under Program Files roots (Skyline only)
      5) last-resort hardcoded constant (WIZARD_EXE)
    """
    # 1) explicit override
    cfg = config.get("General", "photomesh_wizard_exe", fallback="").strip()
    if cfg and os.path.isfile(cfg):
        return cfg

    # 2) try canonical/legacy subpaths
    for pf in _program_files_roots():
        for sub in WIZARD_CANDIDATE_SUBPATHS:
            base = os.path.join(pf, sub)
            for name in WIZARD_CANDIDATE_NAMES:
                cand = os.path.join(base, name)
                if os.path.isfile(cand):
                    _cache_wizard_exe(cand)
                    return cand

    # 3) registry InstallLocation(s)
    for loc in _iter_uninstall_install_locations():
        # Look in the location and common subfolder
        search_roots = [loc, os.path.join(loc, r"Tools\PhotomeshWizard")]
        for root in search_roots:
            for name in WIZARD_CANDIDATE_NAMES:
                cand = os.path.join(root, name)
                if os.path.isfile(cand):
                    _cache_wizard_exe(cand)
                    return cand

    # 4) recursive (Skyline-only) search once
    best = ""
    best_mtime = 0.0
    for pf in _program_files_roots():
        for root, _dirs, files in os.walk(pf):
            if "skyline" not in root.lower():
                continue
            for name in WIZARD_CANDIDATE_NAMES:
                if name in files:
                    cand = os.path.join(root, name)
                    mtime = 0.0
                    try:
                        mtime = os.path.getmtime(cand)
                    except OSError:
                        pass
                    if mtime >= best_mtime:
                        best_mtime = mtime
                        best = cand
    if best:
        _cache_wizard_exe(best)
        return best

    # 5) fallback to existing constant (just in case)
    return WIZARD_EXE if os.path.isfile(WIZARD_EXE) else ""


def wizard_config_paths_from_exe(exe_path: str) -> list[str]:
    """Return likely config.json locations based on the resolved Wizard EXE."""
    paths = []
    if exe_path:
        exe_dir = os.path.dirname(exe_path)
        paths.append(os.path.join(exe_dir, "config.json"))
    for p in WIZ_CFG_PATHS:
        if p not in paths:
            paths.append(p)
    return [p for p in paths if os.path.isdir(os.path.dirname(p))]

# CONFIG VARIABLES WILL BE SET BY IMPORTING MODULE
# These will be set by STE_Toolkit.py when this module is imported
BASE_DIR = None
CONFIG_PATH = None
config = None

# Queue endpoints and working directory used by the PhotoMesh engine
QUEUE_API_URL = "http://127.0.0.1:8087/ProjectQueue/"
QUEUE_SSE_URL = "http://127.0.0.1:8087/ProjectQueue/events"
WORKING_FOLDER = r"C:\\WorkingFolder"

# Off-line connection hint shown when UNC paths fail
OFFLINE_ACCESS_HINT = (
    "Cannot access the shared working folder.\n\n"
    "Connect all PCs to the same switch, assign static IPs (e.g., host 192.168.50.10, "
    "clients 192.168.50.11-13, mask 255.255.255.0), ensure the same Workgroup "
    "(e.g., WORKGROUP), and share the local_data_root on the host as share_name "
    "with read/write permissions. Set the Host IP in Settings so UNC paths use "
    "the correct address."
)
RM_LNK_NAME = "Reality Mesh to VBS4.lnk"
RM_INSTALL_SUBDIRS = ["RealityMeshInstall", "ReailityMeshInstall"]
# endregion

# region Paths & Environment
# Shared configuration for network fuser settings
# NOTE: config, CONFIG_PATH, and BASE_DIR are set by the importing module (STE_Toolkit.py)
# config = configparser.ConfigParser()  # Set by importing module
# config.read(CONFIG_PATH)               # Will be done by importing module

_DRIVE_RE = re.compile(r"^\s*(\S+)\s+Disk", re.MULTILINE)
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
    if config is None or CONFIG_PATH is None:
        return  # Config not yet initialized
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)


def _ensure_fuser_defaults() -> None:
    """Ensure ``config.ini`` has sane default fuser counts."""
    if config is None:
        return  # Config not yet initialized
    if "Fusers" not in config:
        config["Fusers"] = {}
    fusers = config["Fusers"]
    changed = False
    if "desired_count" not in fusers:
        fusers["desired_count"] = "3"
        changed = True
    if "host_count" not in fusers:
        fusers["host_count"] = "1"
        changed = True
    if changed:
        _save_config()


# _ensure_fuser_defaults()  # Called by importing module after config is set


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


def get_fuser_counts() -> tuple[int, int]:
    """
    Returns ``(host_count, desired_count)`` from the configuration, with both
    values clamped to the safe range of 0..3.

    Host counts apply when running on the host machine; desired counts are used
    on dedicated fuser computers.
    """

    if "Fusers" not in config:
        config["Fusers"] = {}
    fusers = config["Fusers"]

    def _to_int(value, default):
        try:
            return int(value)
        except Exception:
            return default

    host_ct = _to_int(fusers.get("host_count", "1"), 1)
    desired_ct = _to_int(fusers.get("desired_count", "3"), 3)

    host_ct = max(0, min(3, host_ct))
    desired_ct = max(0, min(3, desired_ct))

    return host_ct, desired_ct
# endregion

# region Reality Mesh helpers

def is_valid_rm_local_root(root: str) -> bool:
    """
    Return True if *root* exists and contains the 'Reality Mesh to VBS4.lnk'
    either directly or somewhere beneath it. No 'Datatarget.txt' check.
    """
    if not root:
        return False
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return False

    direct = os.path.join(root, RM_LNK_NAME)
    if os.path.isfile(direct):
        return True

    for sub in RM_INSTALL_SUBDIRS:
        p = os.path.join(root, sub, RM_LNK_NAME)
        if os.path.isfile(p):
            return True

    target_lower = RM_LNK_NAME.lower()
    try:
        for dp, _ds, fs in os.walk(root):
            for f in fs:
                if f.lower() == target_lower:
                    return True
    except Exception:
        pass

    return False


def find_local_rm_shortcut(root: str) -> str:
    """
    Return the full path to 'Reality Mesh to VBS4.lnk' under *root*.
    Searches direct, common subfolders, then recursively.
    """
    if not root:
        return ''
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return ''

    direct = os.path.join(root, RM_LNK_NAME)
    if os.path.isfile(direct):
        return direct

    for sub in RM_INSTALL_SUBDIRS:
        p = os.path.join(root, sub, RM_LNK_NAME)
        if os.path.isfile(p):
            return os.path.normpath(p)

    target_lower = RM_LNK_NAME.lower()
    try:
        for dp, _ds, fs in os.walk(root):
            for f in fs:
                if f.lower() == target_lower:
                    return os.path.normpath(os.path.join(dp, f))
    except Exception:
        pass

    return ''

# endregion

# region Wizard Config
def apply_minimal_wizard_defaults() -> None:
    """
    Ensure install-level Wizard defaults enable 3D model OBJ (+3DML).
    Non-destructive: only sets required keys; no presets touched.
    """
    exe = find_wizard_exe()
    for cfg_path in wizard_config_paths_from_exe(exe):
        if not os.path.isfile(cfg_path):
            continue
        cfg = _load_json(cfg_path)
        ui = cfg.setdefault("DefaultPhotoMeshWizardUI", {})
        ui.setdefault("OutputProducts", {}).update({"Model3D": True})
        m3d = ui.setdefault("Model3DFormats", {})
        m3d["3DML"] = True
        m3d["OBJ"] = True
        _save_json(cfg_path, cfg)
        # Suppressed verbose log: print(f"[Wizard] Ensured Model3D/OBJ/3DML enabled -> {cfg_path}")


def enforce_wizard_obj_only_defaults(log=print) -> None:
    """
    Wizard 1.5.1: Force OBJ-only so Output-PivotOrigin.json has real values.
    Also set NetworkWorkingFolder to the current WorkingFuser UNC.
    """

    try:
        offline_cfg = get_offline_cfg()
        working_unc = resolve_network_working_folder_from_cfg(offline_cfg)
    except Exception:
        working_unc = ""

    cfg_paths = [
        r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard\\config.json",
        r"C:\\Program Files\\Skyline\\PhotoMeshWizard\\config.json",
    ]

    for base in filter(None, (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"))):
        p1 = os.path.join(base, r"Skyline\PhotoMesh\Tools\PhotomeshWizard\config.json")
        p2 = os.path.join(base, r"Skyline\PhotoMeshWizard\config.json")
        for candidate in (p1, p2):
            if candidate not in cfg_paths:
                cfg_paths.append(candidate)

    try:
        exe_path = find_wizard_exe()
    except Exception:
        exe_path = ""
    if exe_path:
        for derived in wizard_config_paths_from_exe(exe_path):
            if derived not in cfg_paths:
                cfg_paths.append(derived)

    for path in cfg_paths:
        if not os.path.isfile(path):
            continue
        try:
            cfg = _load_json(path) or {}
            ui = cfg.setdefault("DefaultPhotoMeshWizardUI", {})

            # 1) Ensure Model3D output is enabled (OBJ enforced below)
            op = ui.setdefault("OutputProducts", {})
            op["Model3D"] = True

            # 2) Disable Ortho without clobbering unrelated OutputProducts keys.
            for ortho_key in ("Orthophoto", "2DOrtho", "Ortho", "OrthoMap"):
                op.setdefault(ortho_key, False)
                op[ortho_key] = False

            # 3) OBJ-only model formats
            fmts = ui.setdefault("Model3DFormats", {})
            fmts["OBJ"] = True
            fmts["3DML"] = False
            fmts["SLPK"] = False

            ui.setdefault("VerticalDatum", "Ellipsoid")

            if working_unc:
                cfg["NetworkWorkingFolder"] = working_unc

            _save_json(path, cfg)
            # Suppressed verbose log: log(f"[Wizard 1.5.1] OBJ-only/Ortho-off + WorkingFolder set -> {path}")
        except PermissionError:
            log(f"[Wizard 1.5.1] No permission to write {path}. Run as Administrator.")
        except Exception as exc:
            log(f"[Wizard 1.5.1] Failed updating {path}: {exc}")
# endregion

# region Wizard Presets & Output validation

def _pm_presets_dir() -> str:
    """Return the PhotoMesh Wizard presets directory."""
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Skyline", "PhotoMesh", "Presets")


def install_pmpreset(src_path: str, name: str = "STEPRESET", log=print) -> str:
    """Copy *src_path* into the presets dir with a stable *name*.

    Parameters
    ----------
    src_path:
        Source preset file path.
    name:
        Base name for the installed preset (extension will be .PMPreset).
    log:
        Logging function used to report the destination path.
    """
    dst_dir = _pm_presets_dir()
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, f"{name}.PMPreset")
    shutil.copy2(src_path, dst)
    log(f"[Preset] Installed {name} -> {dst}")
    return dst


def list_output_settings_xml(project_root: str) -> list[str]:
    """Return Output-Settings.xml paths under Build_* folders (newest first)."""
    hits: list[tuple[float, str]] = []
    for b in Path(project_root).glob("Build_*"):
        for od in b.glob("outputBuild_*"):
            f = od / "Output-Settings.xml"
            if f.is_file():
                hits.append((f.stat().st_mtime, str(f)))
    hits.sort(reverse=True, key=lambda t: t[0])
    return [p for _, p in hits]


def assert_obj_enabled(output_settings_xml: str) -> None:
    """Raise RuntimeError if *output_settings_xml* lacks OBJ export."""
    tree = ET.parse(output_settings_xml)
    root = tree.getroot()
    text = ET.tostring(root, encoding="unicode").lower()
    want = ("model3d" in text) and ("obj" in text)
    if not want:
        raise RuntimeError(
            f"OBJ not enabled according to {output_settings_xml}. "
            "Please ensure your preset enables OutputProducts->3D Model and Model3DFormats->OBJ."
        )


def assert_preset_settings_name(project_root: str, name: str = "STEPRESET") -> None:
    """Raise RuntimeError if PresetSettings.xml omits *name*.

    If ``PresetSettings.xml`` is missing under *project_root*, no error is raised.
    """
    ps = Path(project_root) / "PresetSettings.xml"
    if not ps.is_file():
        return
    text = ps.read_text(encoding="utf-8", errors="ignore").lower()
    if name.lower() not in text:
        raise RuntimeError(
            f"PresetSettings.xml in {project_root} does not mention preset '{name}'."
        )

# endregion

# region Network / UNC resolution

# ---------- BEGIN: robust UNC resolution & fuser folder helpers ----------

def _cfg_get(section: dict, key: str, default: str = "") -> str:
    if not section:
        return default
    return str(section.get(key, default) or default)

def workingfuser_unc_from_cfg(cfg: dict) -> str:
    """
    Returns the UNC to the WorkingFuser folder, derived strictly from config.
    Prefers Fusers.shared_working_unc; otherwise builds from Offline.* keys.
    """
    fusers = cfg.get('Fusers', {})
    offline = cfg.get('Offline', {})
    explicit = _cfg_get(fusers, 'shared_working_unc')
    if explicit:
        return explicit.rstrip('\\/')
    host = _cfg_get(offline, 'host_ip') or _cfg_get(offline, 'host_name')
    share = _cfg_get(offline, 'share_name', 'SharedMeshDrive')
    sub   = _cfg_get(offline, 'working_fuser_subdir', 'WorkingFuser')
    if not host:
        return ""  # nothing to do
    return fr'\\{host}\{share}\{sub}'

def unc_reachable_quick(unc_path: str, timeout_sec: float = 2.5) -> bool:
    """
    Fast, bounded probe that doesn't hang the UI.
    """
    if not unc_path or not unc_path.startswith('\\\\'):
        return False
    try:
        # Avoid os.path.exists on UNC (can hang with SMB); use cmd dir
        cmd = ['cmd', '/c', 'dir', f'"{unc_path}"']
        p = subprocess.run(cmd, capture_output=True, timeout=timeout_sec, creationflags=NO_WINDOW_FLAG)
        return p.returncode == 0
    except Exception:
        return False

def ensure_localfuser_dirs_on_unc(cfg: dict, desired_count: int) -> list[Path]:
    """
    Ensures LocalFuser[1..N] *on the UNC WorkingFuser* and returns those paths.
    Refuses to fall back to local folder if a Host is configured.
    """
    working_unc = workingfuser_unc_from_cfg(cfg)
    if not working_unc:
        raise RuntimeError("No Host configured yet (working UNC unknown).")

    # Gate: UNC must be reachable quickly; otherwise fail fast.
    if not unc_reachable_quick(working_unc):
        raise RuntimeError(f"WorkingFuser UNC not reachable: {working_unc}")

    # Simply ensure the WorkingFuser root exists - PhotoMesh creates numbered subdirectories
    # PhotoMesh Fuser creates: 1\, 2\, 3\ directly under WorkingFuser
    localfuser_paths: list[Path] = []
    
    base_path = Path(working_unc)
    
    # Create via PowerShell to avoid long hangs on Python IO errors
    subprocess.run(['powershell', '-NoProfile', '-Command',
                    f"New-Item -ItemType Directory -Path '{base_path}' -Force | Out-Null"],
                   timeout=3, capture_output=True, creationflags=NO_WINDOW_FLAG)
    
    # Return the expected paths that PhotoMesh will create (simple numbered folders)
    for idx in range(1, max(1, desired_count) + 1):
        instance_path = base_path / str(idx)
        localfuser_paths.append(instance_path)
    
    return localfuser_paths

def migrate_local_localfuser_to_unc_if_needed(cfg: dict) -> None:
    try:
        app_dir = Path(sys.argv[0]).resolve().parent
        # any folders that look like *_LocalFuserN in the app dir?
        suspects = [p for p in app_dir.glob('*_LocalFuser*') if p.is_dir()]
        if not suspects:
            return
        working_unc = workingfuser_unc_from_cfg(cfg)
        if not (working_unc and unc_reachable_quick(working_unc)):
            return  # don't move if we can't reach the UNC
        for p in suspects:
            subprocess.run(['powershell','-NoProfile','-Command',
                            f"Move-Item -Force -LiteralPath '{p}' -Destination '{Path(working_unc)}'"],
                           timeout=5, capture_output=True, creationflags=NO_WINDOW_FLAG)
    except Exception:
        pass
# ---------- END: helpers ----------

def _read_photomesh_host() -> str:
    """Resolve the PhotoMesh host from config.ini settings.

    The STE toolkit's :func:`set_host` writes the selected host name to all
    legacy keys checked here, keeping older config readers compatible.
    """
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


def get_machine_name() -> str:
    """Return the current machine name without domain suffix."""
    return socket.gethostname().split('.')[0].upper()


def working_share_root() -> str:
    """UNC to the root share on the host (IP-based)."""
    return build_unc_from_cfg(get_offline_cfg())


def working_fuser_unc() -> str:
    """UNC path to the WorkingFuser subfolder."""
    return resolve_network_working_folder_from_cfg(get_offline_cfg())


def _is_offline_enabled() -> bool:
    """Return True if offline mode is enabled in config.ini."""
    try:
        config.read(CONFIG_PATH)
        return config.getboolean("Offline", "enabled", fallback=False)
    except Exception:
        return False


def get_offline_cfg() -> dict:
    """Return Offline section settings with defaults applied.

    The ``host_name`` value is maintained by ``STE_Toolkit.set_host`` so that
    older tools reading this config continue to work without changes.
    """
    # Default values in case of any config parsing issues
    defaults = {
        "enabled": False,
        "host_name": "KIT-HOST",
        "host_ip": "",
        "share_name": "SharedMeshDrive",
        "local_data_root": os.path.normpath(r"D:\\SharedMeshDrive"),
        "working_fuser_subdir": "WorkingFuser",
        "use_ip_unc": True,
    }
    
    if config is None:
        return defaults  # Config not yet initialized
    try:
        config.read(CONFIG_PATH)
    except Exception:
        pass
    if "Offline" not in config:
        config["Offline"] = {}
    o = config["Offline"]
    
    # Wrap each access in try/except to handle corrupted config values
    # (e.g., lists instead of strings, % interpolation errors)
    try:
        enabled = o.getboolean("enabled", False)
    except Exception:
        enabled = defaults["enabled"]
    
    try:
        host_name = o.get("host_name", "KIT-HOST")
        host_name = host_name.strip() if isinstance(host_name, str) else defaults["host_name"]
    except Exception:
        host_name = defaults["host_name"]
    
    try:
        host_ip = o.get("host_ip", "")
        host_ip = host_ip.strip() if isinstance(host_ip, str) else defaults["host_ip"]
    except Exception:
        host_ip = defaults["host_ip"]
    
    try:
        share_name = o.get("share_name", "SharedMeshDrive")
        share_name = share_name.strip() if isinstance(share_name, str) else defaults["share_name"]
    except Exception:
        share_name = defaults["share_name"]
    
    try:
        local_data_root = o.get("local_data_root", r"D:\\SharedMeshDrive")
        local_data_root = os.path.normpath(local_data_root) if isinstance(local_data_root, str) else defaults["local_data_root"]
    except Exception:
        local_data_root = defaults["local_data_root"]
    
    try:
        working_fuser_subdir = o.get("working_fuser_subdir", "WorkingFuser")
        working_fuser_subdir = working_fuser_subdir.strip() if isinstance(working_fuser_subdir, str) else defaults["working_fuser_subdir"]
    except Exception:
        working_fuser_subdir = defaults["working_fuser_subdir"]
    
    try:
        use_ip_unc = o.getboolean("use_ip_unc", True)
    except Exception:
        use_ip_unc = defaults["use_ip_unc"]
    
    return {
        "enabled": enabled,
        "host_name": host_name,
        "host_ip": host_ip,
        "share_name": share_name,
        "local_data_root": local_data_root,
        "working_fuser_subdir": working_fuser_subdir,
        "use_ip_unc": use_ip_unc,
    }


try:
    # migrate_hostname_to_ip_once()  # Called by importing module after config is set
    pass
except Exception as e:  # pragma: no cover - best effort migration
    logging.warning(f"[migrate] hostname->ip skipped: {e}")


def build_unc_from_cfg(o: dict) -> str:
    """
    Build UNC \\\\<IP>\\share from Offline config, always preferring host_ip.
    Returns an empty string if no host_ip is configured.
    """

    ip = (o.get("host_ip") or "").strip()
    share = (o.get("share_name") or "SharedMeshDrive").strip()
    if not ip:
        return ""
    return rf"\\{ip}\{share}"


def working_fuser_unc_from_cfg(o: dict) -> str:
    """Return UNC path to WorkingFuser based on offline config dict *o*."""
    return resolve_network_working_folder_from_cfg(o)


def resolve_network_working_folder_from_cfg(o: dict) -> str:
    r"""Returns UNC for WorkingFuser (\\\\<IP>\\share\WorkingFuser)."""

    unc = build_unc_from_cfg(o)
    if not unc:
        return ""
    sub = (o.get("working_fuser_subdir") or "WorkingFuser").strip()
    combined = os.path.normpath(os.path.join(unc, sub))
    return combined.replace("/", "\\")


def _resolve_share_root_from_offline(o: dict) -> tuple[str, str]:
    """Return ``(share_name, local_root)`` normalized for SMB sharing."""

    share = o.get("share_name") or "SharedMeshDrive"
    raw_root = o.get("local_data_root") or r"D:\SharedMeshDrive"
    normalized_root = raw_root.replace("/", "\\")
    trimmed_root = normalized_root
    if share:
        tail = f"\\{share}"
        lower_tail = tail.lower()
        candidate = normalized_root.rstrip("\\")
        if candidate.lower().endswith(lower_tail * 2):
            trimmed_root = candidate[: -len(tail)]
    return share, os.path.normpath(trimmed_root)


def ensure_offline_share_via_cmd(log=print) -> None:
    """
    Ensure the Offline share exists using CMD tools only:
      - ``net share`` to create/update the share
      - enable the "File and Printer Sharing" firewall group
    """

    o = get_offline_cfg()
    share, root = _resolve_share_root_from_offline(o)

    try:
        os.makedirs(root, exist_ok=True)
    except Exception as e:
        log(f"Failed to create {root}: {e}")
        return

    try:
        # Least privilege first: Authenticated Users (CHANGE), Administrators (FULL)
        cmd = (
            f'net share {share}="{root}" '
            f'/GRANT:"Authenticated Users",CHANGE /GRANT:"Administrators",FULL'
        )
        result = subprocess.run(["cmd", "/C", cmd], check=False, creationflags=NO_WINDOW_FLAG)
        
        if result.returncode != 0:
            log(f"Authenticated Users share failed, trying Everyone as fallback")
            # Fallback to Everyone with FULL if Authenticated Users fails
            subprocess.run(
                ["cmd", "/C", f'net share {share}="{root}" /GRANT:Everyone,FULL'],
                check=False,
                creationflags=NO_WINDOW_FLAG,
            )
        
        # Enable firewall rules
        firewall_result = subprocess.run(
            [
                "cmd",
                "/C",
                'netsh advfirewall firewall set rule group="File and Printer Sharing" new enable=Yes',
            ],
            check=False,
            creationflags=NO_WINDOW_FLAG,
        )
        
        # Add specific SMB rule if group enable failed
        if firewall_result.returncode != 0:
            log("Firewall group rule failed, trying specific SMB rule")
            subprocess.run(
                [
                    "cmd", 
                    "/C",
                    'netsh advfirewall firewall add rule name="STE Toolkit SMB 445" dir=in action=allow protocol=TCP localport=445 profile=Domain,Private enable=yes'
                ],
                check=False,
                creationflags=NO_WINDOW_FLAG,
            )
        
        log(
            f"Offline share ensured via CMD: \\{get_machine_name()}\\{share}  ({root})"
        )
    except Exception as e:
        log(f"Could not create SMB share via cmd: {e}")


def ensure_offline_share_exists(log=print) -> None:
    """Ensure the offline share exists and firewall rules allow access."""

    ensure_offline_share_via_cmd(log=log)

def can_access_unc(path: str, timeout: float = 2.5) -> bool:
    """Return True only if the UNC root is reachable quickly.
    
    Uses a bounded 'dir' probe to avoid os.path.* UNC stalls that can hang
    startup for 20-60 seconds when the host is unreachable. This prevents
    splash screen hanging in User mode installations.
    """
    if not path:
        return False

    # Quick local-path check
    if not path.startswith("\\\\"):
        try:
            return os.path.isdir(path)
        except Exception:
            return False

    # UNC path: use fast bounded subprocess probe
    try:
        # Use the share root for testing (more reliable than full path)
        parts = path.strip("\\").split("\\")
        if len(parts) >= 2:
            target = rf"\\\\{parts[0]}\\{parts[1]}"
        else:
            target = path
            
        # Probe with bounded 'dir' command - avoids Python's UNC stat latency
        cp = subprocess.run(
            ["cmd", "/c", "dir", f"\"{target}\""],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        return cp.returncode == 0
        
    except subprocess.TimeoutExpired:
        # Timeout means host is unreachable or very slow - don't block startup
        logging.debug(f"[can_access_unc] Timeout checking UNC: {path}")
        return False
    except Exception as e:
        # Other errors - don't block startup
        logging.debug(f"[can_access_unc] Error checking UNC '{path}': {e}")
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


def list_remote_shares(host: str) -> list[str]:
    r"""Return SMB share names exposed by *host*.

    Prefer ``win32net.NetShareEnum``; if unavailable, fall back to parsing
    ``net view \\HOST /all`` output. Returned names exclude administrative
    shares such as ``C$``.
    """
    shares: list[str] = []
    try:  # pragma: no cover - optional dependency
        import win32net  # type: ignore

        resume = 0
        while True:
            data, _, resume = win32net.NetShareEnum(host, 2, resume)
            for item in data:
                name = item.get("netname")
                if name and not name.endswith("$"):
                    shares.append(name)
            if resume == 0:
                break
        return shares
    except Exception:
        pass

    try:
        out = subprocess.run(
            ["net", "view", rf"\\{host}", "/all"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=NO_WINDOW_FLAG,
        ).stdout
        return [m.group(1) for m in _DRIVE_RE.finditer(out)]
    except Exception:
        return []


def probe_best_mesh_share(
    host: str, prefer: list[str] | None = None
) -> tuple[str, str] | None:
    r"""Return ``(share_name, unc_root)`` for the most suitable mesh share.

    The search prefers names in ``prefer`` (case-insensitive) and falls back to
    any share containing a ``Datatarget.txt`` sentinel at its root. If running
    on *host* and no preferred share exists, ``ensure_offline_share_exists`` is
    invoked to create it.
    """

    prefer = prefer or ["SharedMeshDrive", "SharedMesh", "PhotoMesh", "Mesh"]
    shares = list_remote_shares(host)
    if not shares:
        return None

    shares_lower = {s.lower(): s for s in shares}
    for name in prefer:
        s = shares_lower.get(name.lower())
        if s:
            unc = rf"\\{host}\{s}"
            sent = os.path.join(unc, "Datatarget.txt")
            try:
                if not os.path.isfile(sent) and os.access(unc, os.W_OK):
                    with open(sent, "a", encoding="utf-8"):
                        pass
            except Exception:
                pass
            return s, unc

    for s in shares:
        unc = rf"\\{host}\{s}"
        if os.path.isfile(os.path.join(unc, "Datatarget.txt")):
            return s, unc

    try:
        import socket

        if host.lower() in (socket.gethostname().lower(), os.environ.get("COMPUTERNAME", "").lower()):
            ensure_offline_share_exists()
            shares = list_remote_shares(host)
            for name in prefer:
                s = next((x for x in shares if x.lower() == name.lower()), None)
                if s:
                    unc = rf"\\{host}\{s}"
                    return s, unc
    except Exception:
        pass

    return None


def current_mapping(letter: str = "M:") -> str | None:
    r"""Return the UNC path mapped to *letter*, if any."""
    try:
        out = subprocess.run(
            ["net", "use"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=NO_WINDOW_FLAG,
        ).stdout
        pattern = re.compile(rf"^\s*{re.escape(letter)}\s+(\\\\\\S+)", re.MULTILINE | re.IGNORECASE)
        m = pattern.search(out)
        return m.group(1) if m else None
    except Exception:
        return None


def unmap_drive(letter: str = "M:") -> None:
    r"""Unmap drive *letter* using ``net use``."""
    subprocess.run(
        ["net", "use", letter, "/delete", "/yes"],
        check=False,
        creationflags=NO_WINDOW_FLAG,
    )


def map_drive(unc: str, letter: str = "M:") -> bool:
    r"""Map *unc* to drive *letter* via ``net use`` and return success."""
    mapped = current_mapping(letter)
    if mapped and mapped.lower() != unc.lower():
        unmap_drive(letter)
    subprocess.run(
        ["net", "use", letter, unc, "/persistent:yes"],
        check=False,
        creationflags=NO_WINDOW_FLAG,
    )
    target = os.path.join(letter, "")
    return os.path.isdir(target) and can_access_unc(unc)


def resolve_shared_access_path() -> str:
    r"""Return preferred WorkingFuser path based on configuration."""
    o = get_offline_cfg()
    share_unc = build_unc_from_cfg(o)
    working_unc = resolve_network_working_folder_from_cfg(o)

    try:
        config.read(CONFIG_PATH)
    except Exception:
        pass
    sd = config.setdefault("SharedDrive", {})
    mode = sd.get("preferred_mode", "UNC").upper()
    letter = sd.get("drive_letter", "M:")

    if mode == "DRIVE":
        mapped = current_mapping(letter)
        if mapped and mapped.lower() == share_unc.lower() and os.path.isdir(f"{letter}\\"):
            path = os.path.join(letter, o["working_fuser_subdir"])
            if can_access_unc(path):
                return path
    return working_unc


def enforce_photomesh_settings(autostart: bool = True, log=print) -> None:
    """
    Keep Wizard defaults sane and make its NetworkWorkingFolder match our current
    WorkingFuser UNC. Also ensure the WorkingFuser folder exists on the host
    share.

    Parameters
    ----------
    autostart:
        Compatibility placeholder (unused but kept for API stability).
    log:
        Logging function used to report actions or failures.
    """

    # 1) Ensure default outputs already handled by apply_minimal_wizard_defaults()
    apply_minimal_wizard_defaults()  # keeps Model3D/OBJ/3DML on (non-destructive)

    # 2) Compute the canonical UNC
    o = get_offline_cfg()
    share_unc = build_unc_from_cfg(o)
    unc = resolve_network_working_folder_from_cfg(o)  # \\hostOrIp\share\WorkingFuser

    # 3) Ensure folder exists (best effort)
    if unc:
        host_short = o["host_name"].split(".")[0].upper()
        machine = get_machine_name()
        if machine == host_short:
            ensure_offline_share_exists(log=log)
            try:
                os.makedirs(unc, exist_ok=True)
            except Exception as e:  # pragma: no cover - best effort
                log(f"[Wizard] Host could not create WorkingFuser at {unc}: {e}")
        elif not can_access_unc(unc):
            log(
                f"[Wizard] Skipping WorkingFuser pre-create on non-host; {unc} not reachable yet."
            )

    # 4) Enforce Wizard OBJ-only defaults and WorkingFuser UNC
    enforce_wizard_obj_only_defaults(log=log)
# endregion

# region Launch / CLI argument builders
def launch_wizard_new_project(
    project_name: str,
    project_path: str,
    folders: Iterable[str],
    videos: Iterable[str] = (),
    autostart: bool = True,
    log=print,
) -> subprocess.Popen:
    # Ensure defaults are correct for 1.5.1 before any GUI shows
    enforce_wizard_obj_only_defaults(log=log)

    exe = find_wizard_exe()
    if not exe:
        msg = (
            "PhotoMesh Wizard executable was not found.\n\n"
            "Checked Program Files (x64/x86), legacy Tools\\PhotomeshWizard, "
            "and registry InstallLocation. Please install Skyline PhotoMesh/Wizard "
            "or set General/photomesh_wizard_exe in config.ini."
        )
        if messagebox:
            messagebox.showerror("PhotoMesh Wizard not found", msg)
        raise FileNotFoundError(msg)
    args = [exe, "--projectName", project_name, "--projectPath", project_path, "--overrideSettings"]
    for f in folders:
        args += ["--folder", f]
    for v in videos:
        args += ["--video", v]
    if autostart:
        args.append("--autostart")
    log(f"[Wizard] {' '.join(args)}")
    return subprocess.Popen(args, close_fds=False)
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
    command = (
        f'Start-Process "{exe_path}" -ArgumentList "{argline}" '
        "-Verb RunAs -Wait"
    )
    ps = [
        "powershell",
        "-NoProfile",
        "-WindowStyle",
        "Hidden",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        command,
    ]
    subprocess.run(ps, check=True, cwd=cwd or None, creationflags=NO_WINDOW_FLAG)


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
    "ensure_offline_share_via_cmd",
    "ensure_offline_share_exists",
    "can_access_unc",
    "OFFLINE_ACCESS_HINT",
    "_is_offline_enabled",
    "propagate_share_rename_in_config",
    "open_in_explorer",
    "list_remote_shares",
    "probe_best_mesh_share",
    "map_drive",
    "unmap_drive",
    "current_mapping",
    "resolve_shared_access_path",
    "resolve_network_working_folder_from_cfg",
    "enforce_photomesh_settings",
    "enforce_wizard_obj_only_defaults",
    "install_pmpreset",
    "list_output_settings_xml",
    "assert_obj_enabled",
    "assert_preset_settings_name",
    "find_wizard_exe",
    "submit_queue_build",
    "poll_queue_until_done",
    "RM_LNK_NAME",
    "RM_INSTALL_SUBDIRS",
    "is_valid_rm_local_root",
    "find_local_rm_shortcut",
    "get_fuser_counts",
]

# =============================================================================
# Refactor Notes
# - Reorganized functions into labeled sections with docstrings.
# - Added table of contents and region markers for editor folding.
# =============================================================================

