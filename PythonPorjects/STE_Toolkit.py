"""STE Toolkit utility module."""
# =============================================================================
# Project: VBS4Project
# File: STE_Toolkit.py
# Purpose: Main GUI toolkit for launching apps, configuring PhotoMesh/Wizard,
#          managing fusers, paths, and Reality Mesh workflows
# =============================================================================
# Table of Contents
#   1) Metadata & Imports
#   2) Constants & Globals
#   3) Logging Configuration
#   4) Singleton / Process Guard
#   5) Threading Utilities
#   6) PhotoMesh Progress Parsing
#   7) Network / Path Helpers
#   8) VBS4 / BlueIG / BVI Path Resolution
#   9) Version & Executable Discovery
#  10) Executable Finder
#  11) Reality Mesh Link & UNC Resolution
#  12) Reality Mesh Dataset Helpers
#  13) Configuration & App Icon
#  14) Auto-Launch Config
#  15) Fuser Config & Control
#  16) Settings Helpers (Registry & toggles)
#  17) Generic Command Launch Helpers
#  18) UI Assets & Background/Logos
#  19) Help/Tutorials & Document Openers
#  20) (Update or add any other UI here)
# =============================================================================

# =============================================================================
# METADATA & IMPORTS
# =============================================================================

import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, simpledialog, messagebox
from PIL import Image, ImageTk
import os
import subprocess
import shutil
from datetime import datetime
import webbrowser
import urllib.request
import configparser
import winreg
import sys
import functools
import json
import re
import socket
import threading
import shlex
import itertools
from queue import Queue, Empty
import io
try:
    import psutil
except Exception: 
    psutil = None
from photomesh_launcher import (
    get_offline_cfg,
    ensure_offline_share_exists,
    ensure_offline_share_via_cmd,
    can_access_unc,
    OFFLINE_ACCESS_HINT,
    _is_offline_enabled,
    propagate_share_rename_in_config,
    open_in_explorer,
    resolve_network_working_folder_from_cfg,
    enforce_photomesh_settings,
    enforce_wizard_obj_only_defaults,
    working_share_root,
    working_fuser_unc,
    _read_photomesh_host,
    apply_minimal_wizard_defaults,
    launch_wizard_new_project,
    find_wizard_exe,
    install_pmpreset,
    probe_best_mesh_share,
    map_drive,
    unmap_drive,
    RM_LNK_NAME,
    RM_INSTALL_SUBDIRS,
    get_fuser_counts,
)
import time
import glob
import tempfile
import msvcrt
import atexit
import win32api, ctypes
import win32con
import win32gui
import win32net
import win32netcon
import ctypes.wintypes
import logging
from pathlib import Path
from typing import Callable

try:  
    from steup.utils import write_config_atomic  
except Exception: 
    write_config_atomic = None

# --- Resource path resolver -------------------------------------------------
def _resource_path(name: str) -> str:
    """Return absolute path to bundled resource *name*.

    When frozen with PyInstaller, resources live under ``sys._MEIPASS``.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    return os.path.join(base, name)

# --- UI dispatch (thread-safe) ---
_UI_QUEUE = Queue()

def post_ui(fn, *args, **kwargs):
    """Schedule UI work from any background thread."""
    _UI_QUEUE.put((fn, args, kwargs))


def pump_ui_queue(root, interval_ms=33):
    """Process queued UI work at ~30 FPS without blocking."""
    try:
        while True:
            fn, args, kwargs = _UI_QUEUE.get_nowait()
            try:
                fn(*args, **kwargs)
            except Exception:
                pass
    except Empty:
        pass
    root.after(interval_ms, pump_ui_queue, root)

# --- Log batching ---
_log_buf = io.StringIO()
_log_dirty = False


def ui_log_flush(text_widget):
    global _log_dirty
    if _log_dirty:
        text = _log_buf.getvalue()
        _log_buf.seek(0)
        _log_buf.truncate(0)
        text_widget.config(state="normal")
        text_widget.insert("end", text)
        text_widget.see("end")
        text_widget.config(state="disabled")
        _log_dirty = False


def ui_log_schedule_flush(root, text_widget, interval_ms=100):
    ui_log_flush(text_widget)
    root.after(interval_ms, ui_log_schedule_flush, root, text_widget)


def log_to_console(line: str):
    global _log_dirty
    _log_buf.write(line + "\n")
    _log_dirty = True

# =============================================================================
# CONSTANTS & GLOBALS
# =============================================================================
# Win32 constants for tweaking window styles
GWL_STYLE        = -16
WS_BORDER        = 0x00800000
WS_DLGFRAME      = 0x00400000
SWP_NOMOVE       = 0x0002
SWP_NOSIZE       = 0x0001
SWP_NOZORDER     = 0x0004
SWP_FRAMECHANGED = 0x0020

# UI toasts
SHOW_SELECTION_TOAST = False

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    filename='ste_toolkit.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- Hidden subprocess helper (no visible console windows) ---
CREATE_NO_WINDOW = 0x08000000


def run_hidden(cmd: list[str] | str, check=False, cwd=None, shell=False, env=None, capture_output=False, text=True):
    """Run a command without showing a console window."""
    return subprocess.run(
        cmd,
        check=check,
        cwd=cwd,
        shell=shell,
        env=env,
        creationflags=CREATE_NO_WINDOW,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        text=text,
    )

def get_primary_ipv4() -> str:
    """Return the primary non-loopback IPv4 without using visible shells."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""

NO_WINDOW_FLAG = getattr(subprocess, "CREATE_NO_WINDOW", CREATE_NO_WINDOW)

# =============================================================================
# SINGLETON / PROCESS GUARD
# =============================================================================
_lock_file = None

def acquire_singleton(name: str = 'STE_Toolkit.lock') -> bool:
    """Prevent multiple instances by locking a file in the temp directory."""
    global _lock_file
    lock_path = os.path.join(tempfile.gettempdir(), name)
    try:
        _lock_file = open(lock_path, 'w')
        msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        if _lock_file:
            _lock_file.close()
            _lock_file = None
        return False
    atexit.register(release_singleton)
    return True


def release_singleton() -> None:
    global _lock_file
    if _lock_file:
        try:
            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        _lock_file.close()
        _lock_file = None

# =============================================================================
# THREADING UTILITIES
# =============================================================================

def run_in_thread(target, *args, **kwargs):
    """Run *target* in a background daemon thread."""
    thread = threading.Thread(target=target, args=args,
                             kwargs=kwargs, daemon=True)
    thread.start()

def _iter_build_outputs(build_root: str):
    """Yield outputBuild_* directories under Build_* (newest first)."""
    for bdir in sorted(
        (os.path.join(build_root, d) for d in os.listdir(build_root) if d.lower().startswith("build_")),
        key=os.path.getmtime,
        reverse=True,
    ):
        try:
            for odir in sorted(
                (os.path.join(bdir, d) for d in os.listdir(bdir) if d.lower().startswith("outputbuild_")),
                key=os.path.getmtime,
                reverse=True,
            ):
                yield odir
        except Exception:
            continue

def wait_for_obj(build_root: str, timeout_sec: int = 8*3600, poll_sec: int = 10, log=print) -> str | None:
    """Block until an OBJ export exists. Return the folder that holds it."""
    start = time.time()
    while time.time() - start < timeout_sec:
        for odir in _iter_build_outputs(build_root):
            obj_dir = os.path.join(odir, "OBJ")
            if os.path.isdir(obj_dir):
                for _root, _dirs, files in os.walk(obj_dir):
                    if any(fn.lower().endswith(".obj") for fn in files):
                        log(f"[watch] OBJ found: {obj_dir}")
                        return obj_dir
        time.sleep(poll_sec)
    return None

def wait_for_terraexplorer_start(timeout_sec: int = 8*3600, poll_sec: int = 5, log=print) -> bool:
    """Return True when TerraExplorer.exe is observed."""
    want = "terraexplorer.exe"
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            if psutil:
                for p in psutil.process_iter(["name"]):
                    if (p.info.get("name") or "").lower() == want:
                        log("[watch] TerraExplorer.exe detected")
                        return True
            else:
                out = subprocess.check_output(["tasklist"], text=True, stderr=subprocess.DEVNULL)
                if any(want in line.lower() for line in out.splitlines()):
                    log("[watch] TerraExplorer.exe detected (tasklist)")
                    return True
        except Exception:
            pass
        time.sleep(poll_sec)
    return False

# =============================================================================
# PHOTOMESH PROGRESS PARSING
# =============================================================================

_PROGRESS_RE = re.compile(r"Progress:\s*(\d+)%")
_TILE_RE = re.compile(r"Tile\s+(\d+)\s+of\s+(\d+)")

def extract_progress(line: str) -> int | None:
    """Return progress percent from a log line if present."""
    if "Progress:" in line:
        m = _PROGRESS_RE.search(line)
        if m:
            return int(m.group(1))
    m = _TILE_RE.search(line)
    if m:
        done, total = map(int, m.groups())
        if total:
            return int(done / total * 100)
    return None

# =============================================================================
# NETWORK / PATH HELPERS
# =============================================================================

def get_local_ip():
    """Return the primary IPv4 address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def clean_path(path: str) -> str:
    """Return *path* normalized with UNC style backslashes."""
    path = os.path.normpath(path.strip())
    path = path.replace('/', '\\')
    if path.startswith('\\') and not path.startswith('\\\\'):
        path = '\\' + path
    return path

# =============================================================================
# VBS4 / BLUEIG / BVI PATH RESOLUTION
# =============================================================================
# Locate installation paths for supported applications.

def _exe_version_tuple(exe: str) -> tuple[int, ...] | None:
    """Return the file version of *exe* as a tuple or ``None`` on failure."""
    try:
        info = win32api.GetFileVersionInfo(exe, "\\")
        ms = info["FileVersionMS"]
        ls = info["FileVersionLS"]
        return ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF
    except Exception:
        return None

def get_vbs4_install_path() -> str:
    """Return the best VBS4.exe path found on the system.

    Searches common installation roots, preferring the highest file version and
    using the newest modification time as a tiebreaker.  The discovered path is
    cached in ``config['General']['vbs4_path']``.
    """
    path = config['General'].get('vbs4_path', '').strip()
    if path and os.path.isfile(path):
        logging.info("VBS4 path found in config: %s", path)
        return path

    roots = [
        r"C:\BISIM\VBS4",
        r"C:\Builds\VBS4",
        r"C:\Builds",
        r"C:\Bohemia Interactive Simulations",
    ]

    best_path = ""
    best_key: tuple[int, tuple[int, ...], float] = (0, (), 0.0)

    for root in roots:
        try:
            os.makedirs(root, exist_ok=True)
        except Exception:
            continue
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if name.lower() != "vbs4.exe":
                    continue
                exe_path = os.path.join(dirpath, name)
                ver = _exe_version_tuple(exe_path)
                mtime = os.path.getmtime(exe_path)
                key = (1 if ver else 0, ver or (), mtime)
                if key > best_key:
                    best_key = key
                    best_path = exe_path

    if best_path:
        config['General']['vbs4_path'] = best_path
        try:
            if write_config_atomic:
                write_config_atomic(Path(CONFIG_PATH), config)
            else:
                with open(CONFIG_PATH, 'w', encoding='utf-8') as fh:
                    config.write(fh)
        except Exception:
            logging.exception("Failed to write VBS4 path to config")
        return best_path

    logging.warning("VBS4 path not found")
    return ""

def get_vbs4_launcher_path() -> str:
    """
    Return the best path to the VBS4 launcher (VBSLauncher.exe or VBS4Launcher.exe).

    Strategy:
      1) Respect a valid path already saved in config.
      2) Prefer a launcher that sits next to the discovered VBS4.exe.
      3) Search common VBS roots for either filename.
      4) As a last resort, scan C:\\ recursively for either filename.
      5) Among all candidates, prefer highest FileVersion then newest mtime.

    The chosen path is saved to config['General']['vbs4_setup_path'].
    """

    def _save_and_return(p: str) -> str:
        if p:
            config['General']['vbs4_setup_path'] = os.path.normpath(p)
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                config.write(f)
            try:
                refresh_settings_panel_from_config()
            except Exception:
                pass
        return p

    # 0) If config already points to a valid file, use it
    cfg_path = config['General'].get('vbs4_setup_path', '').strip()
    if cfg_path and os.path.isfile(cfg_path):
        logging.info("VBS4 Launcher (from config): %s", cfg_path)
        return cfg_path

    launcher_names = ("VBSLauncher.exe", "VBS4Launcher.exe", "VBSLauncher.bat", "VBS4Launcher.bat")

    # 1) Prefer same folder as discovered VBS4.exe
    vbs4_exe = get_vbs4_install_path()
    if vbs4_exe:
        base = os.path.dirname(vbs4_exe)
        for name in launcher_names:
            cand = os.path.join(base, name)
            if os.path.isfile(cand):
                logging.info("VBS4 Launcher (next to VBS4.exe): %s", cand)
                return _save_and_return(cand)

    # 2) Search common roots for either name
    roots = [
        r"C:\\BISIM\\VBS4",
        r"C:\\Builds\\VBS4",
        r"C:\\Builds",
        r"C:\\Bohemia Interactive Simulations",
        r"C:\\Program Files\\Bohemia Interactive Simulations",
    ]
    if vbs4_exe:
        roots.insert(0, os.path.dirname(vbs4_exe))

    def _iter_candidates(search_roots):
        seen = set()
        for root in search_roots:
            if not os.path.isdir(root):
                continue
            for dirpath, _dirs, files in os.walk(root):
                for name in launcher_names:
                    if name in files:
                        p = os.path.normpath(os.path.join(dirpath, name))
                        if p not in seen:
                            seen.add(p)
                            yield p

    def _rank(p: str):
        ver = _exe_version_tuple(p) or ()
        mtime = 0.0
        try:
            mtime = os.path.getmtime(p)
        except Exception:
            pass
        is_exe = 1 if p.lower().endswith('.exe') else 0
        has_ver = 1 if ver else 0
        return (is_exe, has_ver, ver, mtime)

    # 2a) Try common roots first
    candidates = sorted(_iter_candidates(roots), key=_rank, reverse=True)
    if candidates:
        logging.info("VBS4 Launcher (common roots): %s", candidates[0])
        return _save_and_return(candidates[0])

    # 3) Last resort: walk the entire C:\ drive (may take time on first run)
    candidates = sorted(_iter_candidates([r"C:\\" ]), key=_rank, reverse=True)
    if candidates:
        logging.info("VBS4 Launcher (C:\\ scan): %s", candidates[0])
        return _save_and_return(candidates[0])

    logging.warning("VBS4 Launcher not found")
    return ''

def get_blueig_install_path() -> str:
    path = config['General'].get('blueig_path', '')
    if not path or not os.path.isfile(path):
        path = find_executable('BlueIG.exe')
        if path:
            config['General']['blueig_path'] = path
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
    return path or ''

def get_ares_manager_path() -> str:
    """Return ARES Manager path; try to auto-discover if not in config."""
    path = config['General'].get('bvi_manager_path', '').strip()
    if path and os.path.isfile(path):
        return path

    candidates = [
        r"C:\\Program Files\\ARES",
        r"C:\\Program Files (x86)\\ARES",
        r"D:\\Program Files\\ARES",
        r"D:\\ARES",
    ]
    found = find_executable("ares.manager.exe", additional_paths=candidates)
    if not found:
        found = find_executable("ARES.Manager.exe", additional_paths=candidates)

    if found:
        config['General']['bvi_manager_path'] = clean_path(found)
        with open(CONFIG_PATH, 'w') as f:
            config.write(f)
        return found

    return ''

# =============================================================================
# VERSION & EXECUTABLE DISCOVERY
# =============================================================================
# Helpers to read executable versions and locate binaries.

def get_exe_file_version(exe_path: str) -> str:
    """Return the FileVersion field from an executable, if available."""
    try:
        info = win32api.GetFileVersionInfo(exe_path, '\\')
        ms = info['FileVersionMS']
        ls = info['FileVersionLS']
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:
        return "Unknown"

def get_vbs4_version(file_path: str) -> str:
    """Extract VBS4 version from the file or its path."""
    if os.path.isfile(file_path):
        ver = get_exe_file_version(file_path)
        if ver != "Unknown":
            return ver
    match = re.search(r'VBS4[\\/\s_-]*([0-9]+(?:\.[0-9]+)*)', file_path, re.IGNORECASE)
    return match.group(1) if match else "Unknown"

def get_blueig_version(file_path: str) -> str:
    """Extract BlueIG version from the file or its path."""
    if os.path.isfile(file_path):
        ver = get_exe_file_version(file_path)
        if ver != "Unknown":
            return ver
    match = re.search(r'Blue\s*IG[\\/\s_-]*([0-9]+(?:\.[0-9]+)*)', file_path, re.IGNORECASE)
    return match.group(1) if match else "Unknown"

def get_bvi_version(file_path: str) -> str:
    """Extract BVI (ARES) version from the file or its path."""
    if os.path.isfile(file_path):
        ver = get_exe_file_version(file_path)
        if ver != "Unknown":
            return ver
    match = re.search(r'ARES[-_ ]*dev[-_ ]*release[-_ ]*v[\\/\s_-]*([0-9]+(?:\.[0-9]+)*)', file_path, re.IGNORECASE)
    return match.group(1) if match else "Unknown"

#==============================================================================
# EXECUTABLE FINDER
#==============================================================================

def find_executable(name, additional_paths=[]):
    """
    Try to find either ``name`` (e.g. ``VBS4.exe``) or its ``.bat`` sibling
    (e.g. ``VBS4.bat``) under standard paths or any ``additional_paths``.
    If multiple matching files are found, the newest one (by modification time)
    is returned.
    """
    base, ext = os.path.splitext(name)
    # build list of candidate filenames
    candidates = [name]
    if ext.lower() == '.exe':
        candidates.append(base + '.bat')
    elif ext.lower() == '.bat':
        candidates.append(base + '.exe')

    possible_paths = [
        r"C:\BISIM\VBS4",
        r"C:\Builds\VBS4",
        r"C:\Builds",
        r"C:\Bohemia Interactive Simulations"
    ] + additional_paths

    best_path = None
    best_mtime = -1.0

    # First, check the exact paths
    for path in possible_paths:
        for cand in candidates:
            full_path = os.path.join(path, cand)
            if os.path.isfile(full_path):
                mtime = os.path.getmtime(full_path)
                if mtime > best_mtime:
                    best_mtime = mtime
                    best_path = os.path.normpath(full_path)

    # If not found, search subdirectories
    for path in possible_paths:
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for cand in candidates:
                    if cand in files:
                        full_path = os.path.join(root, cand)
                        mtime = os.path.getmtime(full_path)
                        if mtime > best_mtime:
                            best_mtime = mtime
                            best_path = os.path.normpath(full_path)

    return best_path

# =============================================================================
# REALITY MESH LINK & UNC RESOLUTION
# =============================================================================
# Resolve network shortcuts and local roots for Reality Mesh.

def get_rm_template_from_config() -> str:
    """Read the template from config; keep {host} token if present, normalize slashes."""
    raw = config.get(
        "General",
        "reality_mesh_to_vbs4",
        fallback=r"\\{host}\SharedMeshDrive\RealityMeshInstall\Reality Mesh to VBS4.lnk",
    ).strip()
    if "{host}" not in raw and raw.startswith("\\\\"):
        parts = raw.split("\\")
        if len(parts) >= 4:
            raw = "\\\\{host}\\" + "\\".join(parts[3:])
            config["General"]["reality_mesh_to_vbs4"] = raw
            with open(CONFIG_PATH, "w") as f:
                config.write(f)
    return raw

def _subst_host(template: str) -> str:
    """Replace the {host} token with the configured host IP (fallback to name)."""

    host_ip = get_host_ip()
    replacement = host_ip or get_host()
    return template.replace("{host}", replacement)

def _first_missing_segment(path: str) -> str:
    """Return the first non-existent segment in a path, skipping the UNC host itself."""
    p = os.path.normpath(path)
    if p.startswith("\\\\"):
        parts = p.split("\\")
        if len(parts) < 4:
            return p
        current = f"\\\\{parts[2]}\\{parts[3]}"
        idx = 4
    else:
        parts = p.split(os.sep)
        current = parts[0]
        idx = 1
    for seg in parts[idx:]:
        current = os.path.join(current, seg)
        if not os.path.exists(current):
            return current
    return ""

def _list_dir_safe(path: str, max_items: int = 8) -> str:
    """Return a short newline-separated listing of *path* or an error message."""
    try:
        entries = os.listdir(path)
    except Exception as exc: 
        return f"[cannot list '{path}': {exc}]"
    entries = entries[:max_items]
    return "\n".join(entries)

def _diagnose_missing_unc(path: str) -> str:
    """Return diagnostic text for an unresolved UNC *path*."""
    missing = _first_missing_segment(path)
    if not missing:
        return ""
    parent = os.path.dirname(missing)
    listing = _list_dir_safe(parent)
    return f"Missing path: {missing}\nParent listing ({parent}):\n{listing}"

def _try_link_under(base_dir: str) -> str:
    """Search for the RM link directly in base_dir or recursively beneath it."""
    if not base_dir or not os.path.isdir(base_dir):
        return ""
    direct = os.path.join(base_dir, RM_LNK_NAME)
    if os.path.isfile(direct):
        return direct
    target_lower = RM_LNK_NAME.lower()
    for dp, _ds, fs in os.walk(base_dir):
        for f in fs:
            if f.lower() == target_lower:
                return os.path.join(dp, f)
    return ""

def _candidate_install_roots() -> list[str]:
    """Return possible install roots for both spellings under \\host\\SharedMeshDrive\\…"""
    root = resolve_shared_access_path()
    if not root:
        return []
    return [os.path.join(root, subdir) for subdir in RM_INSTALL_SUBDIRS]

def find_unc_rm_link() -> str:
    """Resolve the UNC shortcut for "Reality Mesh to VBS4".

    Resolve the configured template (substituting ``{host}``).  If the
    shortcut does not exist at that path, walk the ``RealityMeshInstall``
    share looking for it.  Returns an empty string when not found.
    """
    cfg_tpl = get_rm_template_from_config()
    cfg_path = resolve_unc(cfg_tpl)
    if os.path.isfile(cfg_path):
        return cfg_path

    base = os.path.dirname(cfg_path)
    link = _try_link_under(base)
    if link:
        return link

    for root in _candidate_install_roots():
        link = _try_link_under(root)
        if link:
            return link
    return ""

def find_reality_mesh_to_vbs4_link() -> str: 
    return find_unc_rm_link()

def get_rm_local_root() -> str:
    """Return the configured local Reality Mesh install root, if any."""
    return config.get('General', 'reality_mesh_local_root', fallback='').strip()

def set_rm_local_root(path: str) -> None:
    """Store the local Reality Mesh install root in ``config.ini``."""
    if 'General' not in config:
        config['General'] = {}
    norm = os.path.abspath(path) if path else ''
    config['General']['reality_mesh_local_root'] = norm
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)

def is_valid_rm_local_root(root: str) -> bool:
    """
    Return True if *root* exists and contains the 'Reality Mesh to VBS4.lnk'
    either directly or somewhere beneath it.
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

def resolve_active_rm_link() -> tuple[str, str]:
    root = get_rm_local_root()
    if root:
        if not is_valid_rm_local_root(root):
            return ('', 'INVALID_LOCAL_ROOT')
        link = find_local_rm_shortcut(root)
        if link:
            return (link, 'LOCAL')
    link = find_unc_rm_link()
    return (link, 'UNC')

def find_local_rm_link() -> str:  # pragma: no cover - legacy alias
    return find_local_rm_shortcut(get_rm_local_root())

def is_valid_rm_root(local_root: str, data_marker: str = RM_LNK_NAME) -> bool:  # pragma: no cover
    return is_valid_rm_local_root(local_root)

def load_system_settings(path: str) -> dict:
    settings = {}
    if os.path.isfile(path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                value = value.strip()
                if key.strip() == 'dataset_root':
                    value = os.path.normpath(value)
                settings[key.strip()] = value
    return settings

def update_vbs4_settings(path: str) -> None:
    """Ensure ``override_Path_VBS4`` and ``vbs4_version`` reflect the
    configured VBS4 installation."""
    vbs4_exe = get_vbs4_install_path()
    if not vbs4_exe:
        logging.warning("VBS4 path could not be determined; settings not updated")
        return

    vbs4_dir = os.path.dirname(vbs4_exe)
    vbs4_version = get_vbs4_version(vbs4_exe)

    lines = []
    found_path = False
    found_ver = False
    if os.path.isfile(path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('override_Path_VBS4='):
                    line = f'override_Path_VBS4={vbs4_dir}\n'
                    found_path = True
                elif line.startswith('vbs4_version='):
                    line = f'vbs4_version={vbs4_version}\n'
                    found_ver = True
                lines.append(line)

    if not found_path:
        lines.append(f'override_Path_VBS4={vbs4_dir}\n')
    if not found_ver:
        lines.append(f'vbs4_version={vbs4_version}\n')

    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

# =============================================================================
# TERRAIN DISTRIBUTION
def get_distribution_paths() -> list[str]:
    """Return a list of remote VBS4 install paths for terrain distribution."""
    paths_file = os.path.join(BASE_DIR, 'distribution_paths.json')
    if not os.path.isfile(paths_file):
        return []
    try:
        with open(paths_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict):
                paths = data.get('paths', [])
            else:
                paths = data
            return [p for p in paths if isinstance(p, str) and p]
    except Exception:
        return []

def get_local_terrain_path(project_name: str) -> str | None:
    """Return the local terrain output folder for *project_name* if it exists."""
    vbs4_exe = get_vbs4_install_path()
    if not vbs4_exe:
        return None
    terrain_dir = os.path.join(os.path.dirname(vbs4_exe), 'terrain', project_name)
    return terrain_dir if os.path.isdir(terrain_dir) else None

def distribute_terrain(project_name: str, log_func=lambda msg: None) -> None:
    """Copy processed terrain for *project_name* to all configured VBS4 installs."""
    src = get_local_terrain_path(project_name)
    if not src:
        log_func('Local terrain folder not found; skipping distribution')
        return
    for dest_root in get_distribution_paths():
        dest = os.path.join(dest_root, 'terrain', project_name)
        log_func(f'Copying {src} -> {dest}')
        try:
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
            log_func(f'Copied terrain to {dest}')
        except Exception as e:
            log_func(f'Failed to copy to {dest}: {e}')

# =============================================================================
# CONFIGURATION & APP ICON
# =============================================================================
# Load configuration file and apply application icon.

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.ini')
ICON_NAME   = 'icon.ico'

config      = configparser.ConfigParser()
config.read(CONFIG_PATH)

# Global handle to the running MainApp instance so background helpers can
# synchronize UI state (e.g., refresh Settings fields after config updates).
APP_INSTANCE = None

def _save_config():
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)

def _ensure_fuser_defaults() -> None:
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

_ensure_fuser_defaults()

def get_projects_root() -> str:
    try:
        root = config.get("Paths", "projects_root", fallback="").strip()
        return root
    except Exception:
        return ""

def set_projects_root(path: str) -> None:
    if not config.has_section("Paths"):
        config.add_section("Paths")
    config.set("Paths", "projects_root", path)
    _save_config()

# ----- Host/UNC helpers -----
def get_host_ip() -> str:
    """Return the configured host IP (blank when unset)."""

    try:
        return config.get("Offline", "host_ip", fallback="").strip()
    except Exception:
        return ""

def set_host_ip(ip: str) -> None:
    """Persist *ip* to Offline.host_ip and refresh dependent systems."""

    trimmed = ip.strip()
    if "Offline" not in config:
        config["Offline"] = {}
    offline = config["Offline"]
    offline["host_ip"] = trimmed
    if trimmed:
        offline["use_ip_unc"] = "True"
    else:
        offline["use_ip_unc"] = offline.get("use_ip_unc", "True")
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)

    apply_offline_settings()
    update_fuser_shared_path()

def build_unc_from_cfg(o: dict | None = None) -> str:
    """Return ``\\\\<ip>\\<share>`` based on Offline config (IP only)."""

    if o is None:
        o = get_offline_cfg()
    ip = (o.get("host_ip") or "").strip()
    share = (o.get("share_name") or "SharedMeshDrive").strip() or "SharedMeshDrive"
    if not ip:
        return ""
    return f"\\\\{ip}\\{share}"

def resolve_shared_access_path() -> str:
    """Return the root UNC path for the shared mesh drive using the host IP."""

    unc = build_unc_from_cfg()
    return unc or ""

def get_host() -> str:
    return _read_photomesh_host()

def set_host(host: str) -> None:
    """Persist the single 'Host PC Name' across all places legacy code reads from."""
    host = host.strip()
    if not host:
        return

    if "Offline" not in config:
        config["Offline"] = {}
    if "Fusers" not in config:
        config["Fusers"] = {}
    if "Network" not in config:
        config["Network"] = {}

    config["Offline"]["working_fuser_host"] = host
    config["Offline"]["host_name"] = host
    config["Network"]["host"] = host
    config["Fusers"]["working_folder_host"] = host  # so fuser toggle doesn't prompt

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)

    refresh_settings_panel_from_config()

def bootstrap_first_run_if_needed(log=None):
    """Host: ensure IP present and share exists. User: leave blanks."""
    o = config.setdefault('Offline', {})
    general = config.setdefault('General', {})
    mode = general.get('first_run_mode', '').upper()

    if "use_ip_unc" not in o or not o.get("use_ip_unc"):
        o['use_ip_unc'] = 'True'

    if mode == 'HOST':
        if not o.get('host_ip'):
            ip = get_primary_ipv4()
            if ip:
                o['host_ip'] = ip
        o['use_ip_unc'] = 'True'
        ensure_offline_share_exists(log=log or (lambda m: None))
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            config.write(f)
    # USER mode intentionally leaves host blank

def refresh_settings_panel_from_config() -> None:
    """Update the Settings panel UI to reflect the latest config.ini values."""

    app = APP_INSTANCE
    if not app or not hasattr(app, "panels"):
        return

    def _apply():
        try:
            panel = app.panels.get("Settings")
        except Exception:
            return
        if panel and hasattr(panel, "reload_from_config"):
            panel.reload_from_config()

    try:
        post_ui(_apply)
    except Exception:
        try:
            _apply()
        except Exception as exc: 
            logging.getLogger(__name__).warning(
                "[settings-sync] Failed to refresh settings panel: %s", exc
            )

def resolve_unc(template: str) -> str:
    """Replace {host} token with host IP (fallback to host name) and normalize."""

    host = get_host_ip() or get_host()
    path = template.replace("{host}", host)
    return os.path.normpath(path)

def apply_app_icon(widget):
    """Apply the application icon to a Tk widget if the icon file exists."""
    try:
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(os.path.dirname(__file__))
        icon_path = os.path.join(base_path, ICON_NAME)
        widget.iconbitmap(icon_path)
    except Exception as e:
        print(f"Failed to apply icon: {e}")

_orig_toplevel_init = tk.Toplevel.__init__   

def _toplevel_init_with_icon(self, *args, **kwargs):
    _orig_toplevel_init(self, *args, **kwargs)

    def _maybe_icon():
        # Skip undecorated pop-ups which use overrideredirect
        try:
            if not bool(self.wm_overrideredirect()):
                apply_app_icon(self)
        except Exception:
            pass

    # Wait until idle so attributes set immediately after construction are respected
    try:
        self.after_idle(_maybe_icon)
    except Exception:
        _maybe_icon()

tk.Toplevel.__init__ = _toplevel_init_with_icon

if 'General' not in config:
    config['General'] = {}
if 'close_on_launch' not in config['General']:
    config['General']['close_on_launch'] = 'False'
with open(CONFIG_PATH, 'w') as f:
    config.write(f)
def load_image(path, size=None):
    img = Image.open(path)
    if size:
        img = img.resize(size, Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(img)
if 'fullscreen' not in config['General']:
    config['General']['fullscreen'] = 'False' 
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
       
# =============================================================================
# AUTO-LAUNCH CONFIG
# =============================================================================
# Persist user-defined auto-launch program and arguments.

if 'Auto-Launch' not in config:
    config['Auto-Launch'] = {
        'enabled': 'False',
        'program_path': '',
        'arguments': ''
    }
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)

def is_auto_launch_enabled() -> bool:
    return config.getboolean('Auto-Launch', 'enabled', fallback=False)

def get_auto_launch_cmd() -> tuple[str, list[str]]:
    path = config['Auto-Launch'].get('program_path', '').strip()
    raw_args = config['Auto-Launch'].get('arguments', '').strip()
    args = raw_args.split() if raw_args else []
    return path, args

# =============================================================================
# FUSER CONFIG & CONTROL
# =============================================================================
# Manage PhotoMesh Fuser executable settings and scaling.

if 'Fusers' not in config:
    config['Fusers'] = {
        'config_path': 'fuser_config.json',
        'local_fuser_exe': r'C:\\Program Files\\Skyline\\PhotoMesh\\Fuser\\PhotoMeshFuser.exe',
        'remote_fuser_exe': r'C:\\Program Files\\Skyline\\PhotoMesh\\Fuser\\PhotoMeshFuser.exe',
        'fuser_computer': 'False',
        'working_folder_host': ''
    }
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
elif 'fuser_computer' not in config['Fusers']:
    config['Fusers']['fuser_computer'] = 'False'
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
if 'working_folder_host' not in config['Fusers']:
    config['Fusers']['working_folder_host'] = ''
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)

# --- Fuser helpers ---

def get_machine_name() -> str:
    return socket.gethostname().split('.')[0].upper()

def get_working_folder_host() -> str:
    return config['Fusers'].get('working_folder_host', '').split('.')[0].upper()

def is_host_machine() -> bool:
    return get_machine_name() == get_working_folder_host()

def find_fuser_exe() -> str:
    """
    Try common install paths; fall back to walking PhotoMesh install folder.
    Adjust paths if your install differs.
    """
    candidates = [
        r"C:\\Program Files\\Skyline\\PhotoMesh\\Fuser\\PhotoMeshFuser.exe",
        r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\Fuser\\PhotoMeshFuser.exe",
        r"C:\\Program Files (x86)\\Skyline\\PhotoMesh\\Fuser\\PhotoMeshFuser.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    root = r"C:\\Program Files\\Skyline\\PhotoMesh"
    for dp, dn, fn in os.walk(root):
        if "PhotoMeshFuser.exe" in fn:
            return os.path.join(dp, "PhotoMeshFuser.exe")
    return ""

def list_local_fusers() -> list:
    """Return list of psutil.Process for local PhotoMeshFuser.exe."""
    procs = []
    if psutil:
        try:
            for p in psutil.process_iter(['name', 'exe']):
                nm = (p.info.get('name') or '').lower()
                if nm == 'photomeshfuser.exe':
                    procs.append(p)
        except Exception:
            pass
    else:  
        try:
            out = subprocess.check_output(
                ['tasklist', '/FI', 'IMAGENAME eq PhotoMeshFuser.exe'],
                text=True, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                if 'PhotoMeshFuser.exe' in line:
                    procs.append(line)
        except Exception:
            pass
    return procs

def count_local_fusers() -> int:
    return len(list_local_fusers())

# --- Fuser constants / helpers ---------------------------------------------
MIN_LOCAL_FUSERS = 1
MAX_LOCAL_FUSERS = 3

def _clamp_fusers(n: int, is_fuser_computer: bool) -> int:
    """Clamp desired local fuser count according to machine role."""

    lower = MIN_LOCAL_FUSERS if is_fuser_computer else 0
    return max(lower, min(MAX_LOCAL_FUSERS, int(n)))

def start_fuser_instance(idx: int) -> bool:
    """Start *idx*-th fuser via its own shortcut/command."""
    o = get_offline_cfg()
    if o["enabled"]:
        unc = resolve_network_working_folder_from_cfg(o)
        if not can_access_unc(unc):
            messagebox.showerror("Offline Mode", OFFLINE_ACCESS_HINT)
            return False

    exe = find_fuser_exe()
    if not exe:
        messagebox.showerror("Fuser", "PhotoMeshFuser.exe not found. Check PhotoMesh installation.")
        return False

    name = f"LocalFuser{idx}"
    shared = working_fuser_unc()
    bat = os.path.join(os.path.dirname(exe), f"{name}.bat")

    try:
        if os.path.isfile(bat):
            cmd = f'start "" "{bat}"'
        else:
            cmd = f'start "" "{exe}" "{name}" "{shared}" 0 true'
        subprocess.run(cmd, shell=True, check=True)
        return True
    except Exception as e:
        messagebox.showerror("Fuser", f"Failed to start {name}:\n{e}")
        return False

def kill_fusers() -> None:
    """Kill ALL local PhotoMeshFuser.exe instances (safer + faster)."""
    try:
        subprocess.run(['taskkill', '/IM', 'PhotoMeshFuser.exe', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        for p in list_local_fusers():
            try:
                if psutil and isinstance(p, psutil.Process):
                    p.terminate()
            except Exception:
                pass

def ensure_fuser_instances(desired: int):
    """
    Scale local PhotoMeshFuser.exe processes to exactly 'desired'.
    If too few → spawn more; if too many → kill extras.
    """
    is_fuser = config["Fusers"].getboolean("fuser_computer", fallback=False)
    desired = _clamp_fusers(desired, is_fuser)

    current = count_local_fusers()
    if current == desired:
        return

    if current > desired:
        kill_fusers()
        current = 0

    to_start = max(0, desired - current)
    for idx in range(current + 1, current + 1 + to_start):
        start_fuser_instance(idx)

def enforce_local_fuser_policy():
    """Apply the configured fuser instance counts on this machine."""
    try:
        is_fuser = config["Fusers"].getboolean("fuser_computer", fallback=False)
        host_ct, desired_ct = get_fuser_counts()
        if is_host_machine():
            target = host_ct
        elif is_fuser:
            target = desired_ct
        else:
            target = 0
        ensure_fuser_instances(target)
    except Exception as e:
        print(f"[fuser-policy] {e}")

def relaunch_fusers():
    """Restart local fusers to match the configured target count."""

    try:
        kill_fusers()
        enforce_local_fuser_policy()
    except Exception as e:
        print(f"[fuser-relaunch] {e}")

def update_fuser_shared_path(project_path: str | None = None) -> None:
    """Persist the shared WorkingFuser UNC using the configured host IP."""

    o = get_offline_cfg()
    config.setdefault("Fusers", {})

    if project_path and project_path.startswith("\\"):
        unc_path = os.path.normpath(project_path)
    else:
        unc_root = build_unc_from_cfg(o)
        if not unc_root:
            return
        wf_sub = (o.get("working_fuser_subdir") or "WorkingFuser").strip() or "WorkingFuser"
        unc_path = os.path.join(unc_root, wf_sub)

    unc_path = unc_path.replace("/", "\\")
    if not unc_path:
        return

    fuser_cfg = config["Fusers"]
    fuser_cfg["shared_working_unc"] = unc_path

    host_ip = (o.get("host_ip") or "").strip()
    if not host_ip and unc_path.startswith("\\"):
        parts = unc_path.strip("\\").split("\\")
        if parts:
            host_ip = parts[0]
    if host_ip:
        fuser_cfg["working_folder_host"] = host_ip

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)

    config_file = fuser_cfg.get("config_path", "fuser_config.json")
    cfg_path = (
        os.path.join(BASE_DIR, config_file)
        if not os.path.isabs(config_file)
        else config_file
    )

    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

    data.setdefault("fusers", {"localhost": [{"name": "LocalFuser"}]})
    data["shared_path"] = unc_path

    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logging.info(f"[fuser] shared_path -> {unc_path}")
    except Exception as e:
        logging.error("Failed to update fuser config: %s", e)

def apply_offline_settings() -> None:
    """Apply offline configuration changes and refresh dependent systems."""
    enforce_photomesh_settings()
    update_fuser_shared_path()

    if _is_offline_enabled():
        o = get_offline_cfg()
        local_name = get_machine_name()
        host_short = o["host_name"].split('.')[0].upper() if o.get("host_name") else ""
        host_ip = (o.get("host_ip") or "").strip()
        local_ip = get_primary_ipv4()
        if host_ip and local_ip and host_ip == local_ip:
            ensure_offline_share_exists()
        elif host_short and local_name.upper() == host_short:
            ensure_offline_share_exists()

    enforce_local_fuser_policy()

INSTALLER_SILENT_FLAGS = {
    "nightlygit_pmwizard_v1_5_0_photomesh_us.exe": [["/S"], ["/silent"], ["/quiet"]],
    "realitymesh.core.installerx64.25_1.rm.b1.exe": [["/quiet"], ["/silent"], ["/S"], ["/s"]],
    "setup.exe": [["/quiet"], ["/silent"], ["/S"], ["/s"]],
}
DEFAULT_SILENT_FLAGS = [["/quiet"], ["/silent"], ["/S"], ["/s"]]

def is_photomesh_installed() -> bool:
    """Return True when a PhotoMesh Wizard executable is present locally."""

    candidates = [
        r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard\\PhotoMeshWizard.exe",
        r"C:\\Program Files\\Skyline\\PhotoMeshWizard\\PhotoMeshWizard.exe",
    ]
    for cand in candidates:
        if os.path.isfile(cand):
            return True

    try:
        exe = find_wizard_exe()
    except Exception:
        exe = ""
    return bool(exe and os.path.isfile(exe))

def _candidate_rm_roots() -> list[str]:
    """Return potential Reality Mesh install roots for shortcut discovery."""

    roots: list[str] = []
    try:
        cfg_root = config.get("General", "reality_mesh_local_root", fallback="").strip()
        if cfg_root:
            roots.append(cfg_root)
    except Exception:
        pass

    try:
        local_root = config.get("Offline", "local_data_root", fallback="").strip()
        if local_root:
            roots.append(os.path.join(local_root, "RealityMeshInstall"))
    except Exception:
        pass

    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        pf = os.environ.get(env, "").strip()
        if pf:
            roots.append(pf)
            roots.append(os.path.join(pf, "Skyline"))
            roots.append(os.path.join(pf, "Bentley"))

    programdata = os.environ.get("ProgramData", "").strip()
    if programdata:
        roots.append(os.path.join(programdata, "Bentley"))

    seen = set()
    ordered: list[str] = []
    for root in roots:
        norm = os.path.normpath(root)
        if norm and norm not in seen:
            seen.add(norm)
            ordered.append(norm)
    return ordered

def detect_realitymesh_install_root() -> str:
    """Return the folder containing the Reality Mesh shortcut if found."""

    for root in _candidate_rm_roots():
        link = find_local_rm_shortcut(root)
        if link:
            return os.path.dirname(link)
    return ""

def is_realitymesh_installed() -> bool:
    """Return True if a Reality Mesh install shortcut is discoverable."""

    return bool(detect_realitymesh_install_root())

def _iter_installer_files(root: str) -> list[str]:
    """Return sorted installer file paths within *root*."""

    if not root or not os.path.isdir(root):
        return []
    files: list[str] = []
    for path in sorted(Path(root).rglob("*")):
        if path.is_file() and path.suffix.lower() in {".exe", ".msi"}:
            files.append(str(path))
    return files

def _run_installer(path: str) -> tuple[bool, str]:
    """Execute installer *path* silently. Returns (success, error_message)."""

    try:
        if path.lower().endswith(".msi"):
            cmd = ["msiexec", "/i", path, "/qn", "/norestart"]
            log_to_console(f"[first-run] msiexec {' '.join(cmd[1:])}")
            completed = subprocess.run(
                cmd,
                check=True,
                creationflags=NO_WINDOW_FLAG,
            )
            return completed.returncode == 0, ""

        base = os.path.basename(path).lower()
        candidates = INSTALLER_SILENT_FLAGS.get(base, DEFAULT_SILENT_FLAGS)
        last_error = ""
        for flags in candidates:
            cmd = [path, *flags]
            log_to_console(f"[first-run] {' '.join(cmd)}")
            try:
                completed = subprocess.run(
                    cmd,
                    check=True,
                    creationflags=NO_WINDOW_FLAG,
                )
                if completed.returncode == 0:
                    return True, ""
            except subprocess.CalledProcessError as exc:
                last_error = f"exit code {exc.returncode}"
            except Exception as exc: 
                last_error = str(exc)
        return False, last_error or "unknown error"
    except FileNotFoundError as exc:
        return False, str(exc)

def maybe_install_prereqs(payload_root: str) -> list[str]:
    """Install bundled prerequisites when missing. Returns failed installer info."""

    failures: list[str] = []
    if not sys.platform.startswith("win"):
        log_to_console("[first-run] Installer automation skipped on non-Windows platform.")
        return failures

    if not os.path.isdir(payload_root):
        log_to_console(f"[first-run] Installer payload folder missing: {payload_root}")

    photomesh_dir = os.path.join(payload_root, "Photomesh")
    reality_dir = os.path.join(payload_root, "RealityMesh")

    if is_photomesh_installed():
        log_to_console("[first-run] PhotoMesh Wizard detected; skipping bundled installers.")
    else:
        if not os.path.isdir(photomesh_dir):
            log_to_console("[first-run] No PhotoMesh installer payload found.")
        else:
            log_to_console("[first-run] Installing PhotoMesh Wizard prerequisites…")
            for installer in _iter_installer_files(photomesh_dir):
                ok, err = _run_installer(installer)
                if not ok:
                    failures.append(f"{os.path.basename(installer)} ({err})")

    if is_realitymesh_installed():
        log_to_console("[first-run] Reality Mesh installation detected; skipping bundled installers.")
    else:
        if not os.path.isdir(reality_dir):
            log_to_console("[first-run] No Reality Mesh installer payload found.")
        else:
            log_to_console("[first-run] Installing Reality Mesh components…")
            for installer in _iter_installer_files(reality_dir):
                ok, err = _run_installer(installer)
                if not ok:
                    failures.append(f"{os.path.basename(installer)} ({err})")

    return failures

def first_run_setup(master=None) -> None:
    """Execute the first-run workflow for shared drive + installer configuration."""

    log_to_console("[first-run] Starting first-run configuration flow…")
    selected_root = filedialog.askdirectory(
        parent=master,
        title="Select the drive or root folder for SharedMeshDrive",
        mustexist=True,
    )
    if not selected_root:
        raise RuntimeError("First-run setup cancelled by user.")

    selected_root = os.path.normpath(selected_root)
    share_root = selected_root
    if os.path.basename(share_root).lower() != "sharedmeshdrive":
        share_root = os.path.join(selected_root, "SharedMeshDrive")
    log_to_console(f"[first-run] Shared drive root: {share_root}")

    os.makedirs(share_root, exist_ok=True)
    subdirs = [
        "WorkingFuser",
        "Projects",
        "RealityMeshInstall",
        "UnprocessedPhotos",
        "RealityMeshOutput",
    ]
    for sub in subdirs:
        path = os.path.join(share_root, sub)
        try:
            os.makedirs(path, exist_ok=True)
            log_to_console(f"[first-run] Ensured folder: {path}")
        except Exception as exc:
            log_to_console(f"[first-run] Failed to create {path}: {exc}")
            raise

    host_name = get_machine_name()
    host_ip = get_local_ip()
    log_to_console(f"[first-run] Host resolved as {host_name} ({host_ip})")
    if "Offline" not in config:
        config["Offline"] = {}
    offline = config["Offline"]
    offline["enabled"] = "True"
    offline["host_name"] = host_name
    offline["host_ip"] = host_ip
    offline["share_name"] = "SharedMeshDrive"
    offline["local_data_root"] = share_root
    offline["working_fuser_subdir"] = "WorkingFuser"
    offline["working_fuser_host"] = host_name
    offline["use_ip_unc"] = "True"

    sd = config.setdefault("SharedDrive", {})
    sd["preferred_mode"] = "DRIVE"
    sd.setdefault("drive_letter", "M:")
    sd.setdefault("auto_map_on_save", "True")

    _save_config()
    refresh_settings_panel_from_config()
    set_host(host_name)

    ensure_offline_share_via_cmd(log=log_to_console)

    unc_root = build_unc_from_cfg(get_offline_cfg())
    if unc_root:
        set_projects_root(os.path.join(unc_root, "Projects"))

    apply_offline_settings()

    if unc_root and sys.platform.startswith("win"):
        try:
            letter = config["SharedDrive"].get("drive_letter", "M:") if "SharedDrive" in config else "M:"
            if map_drive(unc_root, letter):
                log_to_console(f"[first-run] Mapped {unc_root} to {letter}")
        except Exception as exc:
            log_to_console(f"[first-run] Drive mapping failed: {exc}")

    bundle_root = getattr(sys, "_MEIPASS", BASE_DIR)
    installers_root = os.path.join(bundle_root, "installs")
    failures = maybe_install_prereqs(installers_root)

    try:
        import update_photomesh_config as upc

        upc.main()
    except Exception as exc:  
        log_to_console(f"[first-run] Failed updating PhotoMesh config: {exc}")

    detected_rm_root = detect_realitymesh_install_root()
    share_rm_root = os.path.join(share_root, "RealityMeshInstall")
    final_rm_root = detected_rm_root or (share_rm_root if is_valid_rm_local_root(share_rm_root) else "")
    if final_rm_root:
        set_rm_local_root(final_rm_root)
    else:
        log_to_console("[first-run] Reality Mesh install folder not detected; leaving unset.")

    if failures:
        log_to_console("[first-run] Installer issues: " + "; ".join(failures))
        if messagebox:
            messagebox.showwarning(
                "First-Run Setup",
                "Some installers reported issues:\n- " + "\n- ".join(failures) +
                "\n\nYou can retry from the Settings panel.",
            )

    log_to_console("[first-run] First-run setup completed.")

def first_run_setup_user(master=None) -> None:
    """Configure first-run defaults for non-host machines."""

    log_to_console("[first-run] Starting first-run USER configuration (no sharing)…")

    if "Offline" not in config:
        config["Offline"] = {}
    offline = config["Offline"]
    offline["enabled"] = "True"
    offline["host_name"] = ""
    offline["host_ip"] = ""
    offline["share_name"] = "SharedMeshDrive"
    offline["local_data_root"] = r"D:\\SharedMeshDrive"
    offline["working_fuser_subdir"] = "WorkingFuser"
    offline["use_ip_unc"] = "True"

    sd = config.setdefault("SharedDrive", {})
    sd["preferred_mode"] = "DRIVE"
    sd.setdefault("drive_letter", "M:")
    sd.setdefault("auto_map_on_save", "True")

    _save_config()
    refresh_settings_panel_from_config()
    log_to_console("[first-run] User configuration saved. Set the host later from Settings.")

# =============================================================================
# SETTINGS HELPERS (Registry, toggles)
# =============================================================================
# Registry-based toggles and local settings.

def is_startup_enabled() -> bool:
    """Return True if the app is registered to launch on Windows startup."""
    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "STE_Mission_Planning_Toolkit"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False

def is_close_on_launch_enabled() -> bool:
    """Return True if the config says to close on launch."""
    return config.getboolean('General', 'close_on_launch', fallback=False)

def toggle_startup():
    """Toggle Windows startup registration for this app."""
    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "STE_Mission_Planning_Toolkit"
    if is_startup_enabled():
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        messagebox.showinfo("Settings", "Launch on startup ▶ Disabled")
    else:
        exe_path = sys.executable
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
        messagebox.showinfo("Settings", "Launch on startup ▶ Enabled")

def toggle_close_on_launch():
    """Toggle whether the main window closes when you launch a tool."""
    enabled = not is_close_on_launch_enabled()
    config['General']['close_on_launch'] = str(enabled)
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
    status = "Enabled" if enabled else "Disabled"
    messagebox.showinfo("Settings", f"Close on Software Launch? ▶ {status}")

# =============================================================================
# GENERIC COMMAND LAUNCH HELPERS
# =============================================================================
# Batch file creation and executable resolution utilities.
BATCH_FOLDER = os.path.join(BASE_DIR, "Autolaunch_Batchfiles")
BVI_BAT      = os.path.join(BATCH_FOLDER, "BVI_Manager.bat")

def create_bvi_batch_file(ares_path: str) -> str:
    """
    Write a batch file that launches Ares Manager, waits, then Ares XR.
    """
    xr_path = ares_path.replace(
        "ares.manager\\ares.manager.exe",
        "ares.xr\\Windows\\AresXR.exe"
    )
    with open(BVI_BAT, "w") as f:
        f.write(f'''@echo off
start "" "{ares_path}"
timeout /t 40 /nobreak
start "" "{xr_path}"
exit /b 0
''')
    return BVI_BAT

def get_image_folders_recursively(base_folder):
    r"""Return all subfolders within *base_folder* that contain image files.

    ``os.walk`` preserves whatever path separators the caller provides. When a
    user enters a path with forward slashes on Windows this can result in mixed
    ``/`` and ``\\`` in the returned folder names. Normalizing both the base
    folder and discovered paths ensures consistent separators and proper UNC
    handling.
    """
    base_folder = clean_path(base_folder)
    image_folders = []

    for root, dirs, files in os.walk(base_folder):
        root = clean_path(root)
        if any(
            file.lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff"))
            for file in files
        ):
            image_folders.append(root)

    return image_folders

def create_app_button(parent, app_name, get_path_func, action_func, set_path_func,
                      version_func=None):
    """
    Create a launcher button with a version label and a small [⚙] button to set the path.
    If version_func is provided, it will be used to compute the version string instead of
    the default EXE FileVersion.
    """

    parent_bg = parent.cget("bg")

    row = tk.Frame(parent, bg=parent_bg)
    row.pack(pady=(10, 0), fill="x")

    button = tk.Button(
        row,
        text=f"Launch {app_name}",
        font=("Helvetica", 24),
        bg="#888888",
        fg="white",
        width=30,
        height=1,
        state="disabled",
        command=lambda: action_func() if button.cget("state") == "normal" else None,
        bd=0,
        highlightthickness=0,
    )
    button.pack(side="left")

    set_btn = tk.Button(
        row,
        text="⚙",
        width=2,
        font=("Helvetica", 16, "bold"),
        bg="orange",
        fg="black",
        command=set_path_func,
        bd=0,
        highlightthickness=0,
    )

    checking_label = tk.Label(
        row,
        text="Checking…",
        font=("Helvetica", 12),
        bg=parent_bg,
        fg="white",
    )
    checking_label.pack(side="left", padx=(6, 0))

    version_label = tk.Label(
        parent,
        text="Version: …",
        font=("Helvetica", 16),
        bg="black",
        fg="white",
        bd=0,
        highlightthickness=0,
    )
    version_label.pack(pady=(0, 6))

    def _resolve_and_enable():
        path = get_path_func()
        path = clean_path(path) if path else ""
        ok = bool(path and os.path.exists(path))

        def _apply():
            btn_state, btn_bg = ("normal", "#444444") if ok else ("disabled", "#888888")
            button.config(state=btn_state, bg=btn_bg)
            if ok:
                ver = (version_func(path) if version_func else get_exe_file_version(path))
                version_label.config(text=f"Version: {ver}")
                set_btn.pack_forget()
            else:
                version_label.config(text="Version: …")
                set_btn.pack(side="left", padx=(6, 0))
            checking_label.destroy()

        post_ui(_apply)

    run_in_thread(_resolve_and_enable)

    return button, version_label

#==============================================================================
# EXE finder prompt
#==============================================================================

def prompt_for_exe(app_name, config_key):
    response = messagebox.askyesno(
        f"Set {app_name} Path",
        f"Do you want to set the path for {app_name}?\n\nClick 'No' to skip.",
        icon='question'
    )
    if not response:
        return True 

    path = filedialog.askopenfilename(
        title=f"Select {app_name} Executable",
        filetypes=[("Executable Files", "*.exe")]
    )
    if path and os.path.exists(path):
        config['General'][config_key] = clean_path(path)
        with open(CONFIG_PATH, 'w') as f:
            config.write(f)
        messagebox.showinfo("Success", f"{app_name} path set to:\n{path}")
        return True
    else:
        messagebox.showerror("Error", f"Invalid {app_name} path selected.")
        return False

def ensure_executable(config_key: str, exe_name: str | list[str], prompt_title: str) -> str:
    path = clean_path(config['General'].get(config_key, '').strip())
    if path and os.path.isfile(path):
        return path
    if isinstance(exe_name, str):
        candidate = exe_name.lower()
        if candidate == 'vbs4.exe':
            path = get_vbs4_install_path()
        elif candidate == 'blueig.exe':
            path = get_blueig_install_path()
        elif candidate in ('vbslauncher.exe', 'vbs4launcher.exe'):
            path = get_vbs4_launcher_path()
        else:
            path = find_executable(exe_name)
    else:
        for name in exe_name:
            low = name.lower()
            if low in ('vbslauncher.exe', 'vbs4launcher.exe'):
                path = get_vbs4_launcher_path()
            else:
                path = find_executable(name)
            if path:
                break

    if path and os.path.isfile(path):
        if config_key != 'vbs4_path':
            config['General'][config_key] = clean_path(path)
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
        return path

    if not prompt_for_exe(prompt_title, config_key): 
        raise FileNotFoundError(f"No executable selected for '{config_key}'.")
    path = config['General'][config_key]
    return path

# =============================================================================
# BVI (ARES Manager)

def get_bvi_batch_file() -> str:
    """Return path to a temporary batch file for launching BVI."""
    ares_exe = ensure_executable(
        'bvi_manager_path',
        ['ares.manager.exe', 'ARES.Manager.exe'],
        "Select ARES Manager executable",
    )
    return create_bvi_batch_file(ares_exe)

def launch_vbs4():
    path = get_vbs4_install_path()
    if not path:
        messagebox.showerror("Error", "VBS4 executable not found. Please set the correct path in settings.")
        return
    try:
        subprocess.Popen([path])
        if is_close_on_launch_enabled():
            sys.exit(0)
    except FileNotFoundError:
        logging.exception("VBS4 executable not found")
        messagebox.showerror("Launch Failed", "VBS4 executable not found.")
    except OSError as e:
        logging.exception("Failed to launch VBS4")
        messagebox.showerror("Launch Failed", f"Couldn't launch VBS4:\n{e}")

def launch_vbs4_setup():
    try:
        vbs4_setup_exe = ensure_executable('vbs4_setup_path', 'VBSLauncher.exe', "Select VBSLauncher.exe")
        subprocess.Popen([vbs4_setup_exe], creationflags=subprocess.CREATE_NO_WINDOW)
        if is_close_on_launch_enabled():
            sys.exit(0)
    except FileNotFoundError:
        logging.exception("VBSLauncher.exe not found")
        messagebox.showerror("Launch Failed", "VBSLauncher.exe not found.")
    except OSError as e:
        logging.exception("Failed to launch VBS4 Setup")
        messagebox.showerror("Launch Failed", f"Couldn't launch VBS4 Setup Launcher:\n{e}")

def launch_blueig():
    exe = config['General'].get('blueig_path', '').strip()
    if not exe or not os.path.isfile(exe):
        messagebox.showwarning(
            "BlueIG Not Found",
            "Couldn't find BlueIG.exe — please locate it now."
        )
        exe = filedialog.askopenfilename(
            title="Select BlueIG Executable",
            filetypes=[("Executable Files", "*.exe")]
        )
        if not exe or not os.path.isfile(exe):
            messagebox.showerror("Error", "Invalid BlueIG path selected.")
            return

        # Save the new path in config.ini
        config['General']['blueig_path'] = exe
        with open(CONFIG_PATH, 'w') as cfg:
            config.write(cfg)

    # Determine the folder where BlueIG.exe lives:
    blueig_dir = os.path.dirname(exe)

    # 2) Ask which HammerKit scenario (1–4)
    n = simpledialog.askinteger(
        "Select HammerKit Scenario",
        "Choose VBS4 HammerKit Server (1–4):",
        minvalue=1, maxvalue=4
    )
    if n is None:
        return  # user hit Cancel

    scenario = f"Exercise-HAMMERKIT1-{n}"

    args = [
        exe,
        "-hmd=openxr_ctr:oculus",
        f"-vbsHostExerciseID={scenario}",
        "-splitCPU",
        "-DJobThreads=8",
        "-DJobPool=8",
    ]

    try:
        subprocess.Popen(args, cwd=blueig_dir, creationflags=subprocess.CREATE_NO_WINDOW)
        if is_close_on_launch_enabled():
            sys.exit(0)
    except FileNotFoundError:
        logging.exception("BlueIG executable not found")
        messagebox.showerror("Launch Failed", "BlueIG executable not found.")
    except OSError as e:
        logging.exception("Failed to launch BlueIG")
        messagebox.showerror("Launch Failed", f"Couldn't launch BlueIG:\n{e}")

def launch_bvi():
    try:
        batch_file = get_bvi_batch_file()
        subprocess.Popen([batch_file], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if is_close_on_launch_enabled():
            sys.exit(0)
    except FileNotFoundError:
        logging.exception("BVI executable not found")
        messagebox.showerror("Launch Failed", "BVI executable not found.")
    except OSError as e:
        logging.exception("Failed to launch BVI")
        messagebox.showerror("Launch Failed", f"Couldn't launch BVI:\n{e}")

def open_bvi_terrain():
    url = "http://localhost:9080/terrain"
    def _open():
        try:
            urllib.request.urlopen(url, timeout=1)
            post_ui(lambda: webbrowser.open(url, new=2))
        except Exception:
            post_ui(messagebox.showinfo, "BVI", "Note: BVI must be running")

    run_in_thread(_open)
       
# =============================================================================
# UI ASSETS & BACKGROUND/LOGOS
# =============================================================================
# Paths and helpers for background images and logos.

background_image_path = os.path.join(BASE_DIR, "20240206_101613_026.jpg")
logo_STE_path         = os.path.join(BASE_DIR, "logos", "STE_CFT_Logo.png")
logo_AFC_army         = os.path.join(BASE_DIR, "logos", "US_Army_AFC_Logo.png")
logo_first_army       = os.path.join(BASE_DIR, "logos", "First_Army_Logo.png")
logo_us_army_path     = os.path.join(BASE_DIR, "logos", "New_US_Army_Logo.png")
prompt_box_image_path = os.path.join(BASE_DIR, "promptbox.jpg")
def set_background(window, widget=None):
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()

    # wallpaper
    if os.path.exists(background_image_path):
        # Load the image once at full screen size
        img = Image.open(background_image_path)
        img = img.resize((screen_width, screen_height), Image.Resampling.LANCZOS)
        
        # If we're applying to a panel, calculate the panel's position relative to the window
        if widget is not None and widget != window:
            try:
                # Get the panel's absolute position relative to the root window
                x = widget.winfo_rootx() - window.winfo_rootx()
                y = widget.winfo_rooty() - window.winfo_rooty()
                
                # Create a cropped version of the image that corresponds to where
                # this panel would be in the window
                target_width = widget.winfo_width() or screen_width
                target_height = widget.winfo_height() or screen_height
                
                # Make sure we don't have zero dimensions
                if target_width < 10:
                    target_width = screen_width
                if target_height < 10:
                    target_height = screen_height
                
                # Use the same image but place it with negative offset to align with main bg
                ph = ImageTk.PhotoImage(img)
                lbl = tk.Label(widget, image=ph)
                lbl.image = ph
                lbl.place(x=-x, y=-y, width=screen_width, height=screen_height)
            except Exception as e:
                # Fallback to standard method if positioning fails
                ph = ImageTk.PhotoImage(img)
                lbl = tk.Label(widget, image=ph)
                lbl.image = ph
                lbl.place(x=0, y=0, relwidth=1, relheight=1)
        else:
            # For the main window, just apply the full image
            ph = ImageTk.PhotoImage(img)
            lbl = tk.Label(window, image=ph)
            lbl.image = ph
            lbl.place(x=0, y=0, relwidth=1, relheight=1)
        
        try:
            lbl.lower()
        except Exception:
            pass

def set_wallpaper(window):
    if not os.path.exists(background_image_path):
        return

    w = window.winfo_width()
    h = window.winfo_height()

    img = Image.open(background_image_path).resize((w, h), Image.Resampling.LANCZOS)
    ph  = ImageTk.PhotoImage(img)
    lbl = tk.Label(window, image=ph, bd=0, highlightthickness=0)
    lbl.image = ph
    lbl.place(relwidth=1, relheight=1)
    try:
        lbl.lower()
    except Exception:
        pass
    
# =============================================================================
# HELP/TUTORIALS & DOCUMENT OPENERS
# =============================================================================
# Static references and routines for help menus.

tutorials_items = {
    "VBS4 Documentation": lambda: webbrowser.open(
        r"C:\Builds\VBS4\VBS4 25.1 YYMEA_General\docs\VBS4_Manuals_EN.htm", new=2),
    "Script Wiki":         lambda: webbrowser.open(
        r"C:\Builds\VBS4\VBS4 25.1 YYMEA_General\docs\Wiki\SQF_Reference.html", new=2),
    "BVI PDF Docs":        lambda: messagebox.showinfo("BVI Docs","Open BVI PDF docs"),
}
blueig_help_items = {
    "Blue IG Official Documentation": lambda: subprocess.Popen([BlueIG_HTML], shell=True),
    "Video Tutorials":                lambda: messagebox.showinfo("Coming Soon", "Not implemented yet"),
    "Support Website":                lambda: webbrowser.open("https://bisimulations.com/support/", new=2),
}
# ─── help MENUS ────────────────────────────
VBS4_HTML = r"C:\Builds\VBS4\VBS4 25.1 YYMEA_General\docs\VBS4_Manuals_EN.htm"
BlueIG_HTML = r"C:\Builds\BlueIG\Blue IG 24.2 YYMEA_General\docs\Blue_IG_EN.htm"
SCRIPT_WIKI  = r"C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\Help_Tutorials\Wiki\SQF_Reference.html"
SUPPORT_SITE = "https://bisimulations.com/support/"
STE_SMTP_KIT_GUIDE = os.path.join(BASE_DIR, "Help_Tutorials", "STE_SMTP_KIT_GUIDE.pdf")

# ─── PDF & VIDEO SUB-MENU DATA ───────────────────────────────────────────────
def open_vbs4_manuals():
    vbs4_path = get_vbs4_install_path()
    if vbs4_path:
        manuals_path = os.path.join(os.path.dirname(vbs4_path), "docs", "VBS4_Manuals_EN.htm")
        if os.path.exists(manuals_path):
            webbrowser.open(f"file://{manuals_path}", new=2)
        else:
            messagebox.showerror("Error", "VBS4 Manuals not found in the expected location.")
    else:
        messagebox.showerror("Error", "VBS4 path not set. Please set it in the settings.")

pdf_docs = {
    "SQF Wiki": lambda: webbrowser.open(
        os.path.join(BASE_DIR, "Help_Tutorials", "Wiki", "SQF_Reference.html"),
        new=2),
    "VBS4 Manuals": lambda: open_vbs4_manuals(),
}

# ─── VBS4 PDF Docs Helper ────────────────────────────────────────────────────

VBS4_PDF_DIR = os.path.join(BASE_DIR, "PDF_EN")

def open_vbs4_pdfs():
    """Scan the VBS4 PDF_EN folder and pop up a submenu of all the PDFs."""
    try:
        pdfs = sorted(f for f in os.listdir(VBS4_PDF_DIR) if f.lower().endswith(".pdf"))
    except FileNotFoundError:
        messagebox.showerror("Error", f"VBS4 PDF folder not found:\n{VBS4_PDF_DIR}")
        return

    items = {}
    for fname in pdfs:
        display = os.path.splitext(fname)[0].replace("_", " ")
        path    = os.path.join(VBS4_PDF_DIR, fname)
        items[display] = lambda p=path: subprocess.Popen([p], shell=True)

video_items = {
    "VBS4 Video Tutorials":   lambda: messagebox.showinfo("VBS4 Videos", "Play VBS4 tutorial videos"),
    "BlueIG Video Tutorials": lambda: messagebox.showinfo("BlueIG Videos", "Play BlueIG tutorial videos"),
    "BVI Video Tutorials":    lambda: messagebox.showinfo("BVI Videos", "Play BVI tutorial videos"),
}
vbs4_help_items = {
    "VBS4 Official Documentation": lambda: subprocess.Popen([VBS4_HTML], shell=True),
       "VBS4 Admin Manual": lambda: subprocess.Popen([r"C:\Builds\VBS4\VBS4 25.1 YYMEA_General\docs\PDF_EN\VBS4_Administrator_Manual.pdf"], shell=True),
    "Script Wiki":                  lambda: subprocess.Popen([SCRIPT_WIKI], shell=True),
    "Video Tutorials":              lambda: messagebox.showinfo("Video Tutorials","Coming soon…"),
    "Support Website":              lambda: webbrowser.open(SUPPORT_SITE, new=2),
    "Gaming Help": lambda: webbrowser.open("https://example.com/vbs4-gaming-help", new=2),
}
def open_bvi_quickstart():
    # List of possible locations for the BVI technical document
    possible_paths = [
        os.path.join(BASE_DIR, "BVI_Documentation", "BVI_TECHNICAL_DOC.pdf"),
        os.path.join(BASE_DIR, "..", "BVI_Documentation", "BVI_TECHNICAL_DOC.pdf"),
        os.path.join(BASE_DIR, "..", "..", "BVI_Documentation", "BVI_TECHNICAL_DOC.pdf"),
    ]

    # Check if the path is already saved in the config
    saved_path = config['General'].get('bvi_quickstart_path', '')
    if saved_path and os.path.exists(saved_path):
        possible_paths.insert(0, saved_path)

    # Try to find the document
    for path in possible_paths:
        if os.path.exists(path):
            try:
                subprocess.Popen([path], shell=True)
                return
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open Quick-Start Guide:\n{e}")
                return

    # If not found, ask the user to locate the file
    messagebox.showinfo("BVI Quick-Start Guide", "The BVI Technical Document was not found. Please select its location.")
    user_path = filedialog.askopenfilename(title="Select BVI Technical Document", filetypes=[("PDF Files", "*.pdf")])
    
    if user_path:
        # Save the path for future use
        config['General']['bvi_quickstart_path'] = user_path
        with open(CONFIG_PATH, 'w') as f:
            config.write(f)
        
        try:
            subprocess.Popen([user_path], shell=True)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open Quick-Start Guide:\n{e}")
    else:
        messagebox.showinfo("BVI Quick-Start Guide", "No file selected. The Quick-Start Guide will not be opened.")

def open_bvi_documentation():
    possible_paths = [
        os.path.join(BASE_DIR, "BVI_Documentation", "BVI_User_Instructions.pdf"),
        os.path.join(BASE_DIR, "..", "BVI_Documentation", "BVI_User_Instructions.pdf"),
        os.path.join(BASE_DIR, "..", "..", "BVI_Documentation", "BVI_User_Instructions.pdf"),
    ]

    # Check if the path is already saved in the config
    saved_path = config['General'].get('bvi_documentation_path', '')
    if saved_path and os.path.exists(saved_path):
        possible_paths.insert(0, saved_path)

    # Try to find the document
    for path in possible_paths:
        if os.path.exists(path):
            try:
                subprocess.Popen([path], shell=True)
                return
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open BVI Documentation:\n{e}")
                return

    # If not found, ask the user to locate the file
    messagebox.showinfo("BVI Documentation", "The BVI User Instructions were not found. Please select its location.")
    user_path = filedialog.askopenfilename(title="Select BVI User Instructions", filetypes=[("PDF Files", "*.pdf")])
    
    if user_path:
        # Save the path for future use
        config['General']['bvi_documentation_path'] = user_path
        with open(CONFIG_PATH, 'w') as f:
            config.write(f)
        
        try:
            subprocess.Popen([user_path], shell=True)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open BVI Documentation:\n{e}")
    else:
        messagebox.showinfo("BVI Documentation", "No file selected. The BVI Documentation will not be opened.")

# BVI Help submenu
bvi_help_items = {
    "BVI Official Documentation": open_bvi_documentation,
    "BVI Quick-Start Guide":      open_bvi_quickstart,
    "Video Tutorials":            lambda: messagebox.showinfo("Video Tutorials","Coming soon…"),
    "Support Website":            lambda: webbrowser.open("https://www.dignitastechnologies.com/bvi", new=2),
}

# One-Click Terrain Help submenu
def _find_file(filename, roots):
    """Search for *filename* inside the provided *roots* directories."""
    for root in roots:
        if os.path.isdir(root):
            for dirpath, _dirs, files in os.walk(root):
                if filename in files:
                    return os.path.join(dirpath, filename)
    return None

def open_reality_mesh_docs():
    """Open the Reality Mesh HTML help documentation."""
    path = _find_file("Reality_Mesh_EN.htm", [r"C:\\Bohemia Interactive Simulations"])
    if path:
        webbrowser.open(f"file://{path}", new=2)
    else:
        messagebox.showerror("Error", "Reality Mesh documentation not found.")

def open_photomesh_help():
    """Open the PhotoMesh help PDF, searching development and production paths."""
    roots = [
        os.path.join(BASE_DIR, "Help_Tutorials"),
        r"C:\\Program Files (x86)\\STE Toolkit\\_internal\\Help_Tutorials",
    ]
    path = _find_file("PM804_Wizard_141_Training.pdf", roots)
    if path:
        try:
            subprocess.Popen([path], shell=True)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open PhotoMesh help:\n{e}")
    else:
        messagebox.showerror("Error", "PhotoMesh help not found.")

oct_help_items = {
    "Reality Mesh Help": open_reality_mesh_docs,
    "PhotoMesh Help": open_photomesh_help,
}

# ─── Helper DATA ────────────────────────────────────────────────────

def set_blueig_install_path():
    """Open a file dialog to choose your BlueIG executable and save it."""
    path = filedialog.askopenfilename(
        title="Select BlueIG Executable",
        filetypes=[("Executable Files", "*.exe")]
    )
    if path and os.path.exists(path):
        config['General']['blueig_path'] = path
        with open(CONFIG_PATH, 'w') as f:
            config.write(f)
        messagebox.showinfo("Settings", f"BlueIG path set to:\n{path}")
    else:
        messagebox.showerror("Settings", "Invalid BlueIG path selected.")

# ─── Default Browser Helpers ────────────────────────────────────────────────

def get_default_browser() -> str:
    """Return the currently saved default browser executable path."""
    return config['General'].get('default_browser', '')

def set_default_browser():
    """Open file dialog to set the default browser executable path."""
    path = filedialog.askopenfilename(
        title="Select Default Browser Executable",
        filetypes=[("Executable Files", "*.exe")]
    )
    if path and os.path.exists(path):
        config['General']['default_browser'] = path
        with open(CONFIG_PATH, 'w') as f:
            config.write(f)
        messagebox.showinfo("Settings", f"Default browser set to:\n{path}")
    else:
        messagebox.showerror("Settings", "Invalid browser path selected.")

# ─── One Click Dataset Helpers ─────────────────────────────────────────────

def get_oneclick_output_path() -> str:
    """Return the last One‑Click dataset folder path saved in config."""
    return config.get('BiSimOneClickPath', 'path', fallback='')

def set_oneclick_output_path(path: str) -> None:
    """Save the provided dataset folder path to ``config.ini``."""
    if 'BiSimOneClickPath' not in config:
        config['BiSimOneClickPath'] = {}
    config['BiSimOneClickPath']['path'] = path
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)

# =============================================================================
# FILE DIALOG / EXE SELECTION HELPERS
# =============================================================================
# Prompts for choosing executables and directories.

def set_vbs4_install_path():
    """Open a file dialog to choose VBS4.exe, then save it in config.ini."""
    path = filedialog.askopenfilename(
        title="Select VBS4.exe",
        filetypes=[("Executable Files", "*.exe")]
    )
    if path and os.path.exists(path):
        path = os.path.normpath(path)
        config['General']['vbs4_path'] = path
        with open(CONFIG_PATH, 'w') as f:
            config.write(f)
        messagebox.showinfo("Settings", f"VBS4 path set to:\n{path}")
    else:
        messagebox.showerror("Settings", "Invalid VBS4 path selected.")

def set_ares_manager_path():
    path = filedialog.askopenfilename(title="Select ARES Manager.exe", filetypes=[("Executable", "*.exe")])
    if path:
        config['General']['bvi_manager_path'] = path
        with open(CONFIG_PATH, 'w') as f: config.write(f)
        messagebox.showinfo("Settings", f"ARES Manager path set to:\n{path}")

# ─── One Click Terrain SETUP ──────────────────────────────────────────────────────
def find_terra_explorer() -> str:
    """Search for TerraExplorer.exe and return its path or an empty string."""
    possible_paths = [
        r"C:\Program Files\Skyline\TerraExplorer Pro\TerraExplorer.exe",
        r"C:\Program Files (x86)\Skyline\TerraExplorer Pro\TerraExplorer.exe",
        r"C:\Program Files\Skyline\TerraExplorer\TerraExplorer.exe",
        r"C:\Program Files (x86)\Skyline\TerraExplorer\TerraExplorer.exe",
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    for root, dirs, files in os.walk(r"C:\\"):
        if "TerraExplorer.exe" in files:
            return os.path.join(root, "TerraExplorer.exe")
    return ""

# ─── helper for "External Map" ────────────────────────────────────────────
def select_vbs_map_profile():
    """Prompt for a VBS Map loginName and save it to config."""
    profile = simpledialog.askstring(
        "Select User Profile",
        "Enter VBS Map loginName:"
    )
    if not profile:
        return
    cfg = config['General']
    cfg['vbs_map_user']   = profile.strip()
    cfg.setdefault('vbs_map_server', 'localhost')
    cfg.setdefault('vbs_map_port',   '4080')
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
    messagebox.showinfo("Settings", f"VBS Map loginName set to:\n{profile}")

def open_external_map():
    """Open the VBS Map web UI for the saved user, if server is live."""
    cfg  = config['General']
    user = cfg.get('vbs_map_user','').strip()
    if not user:
        messagebox.showwarning("External Map",
                               "No loginName set. Please select a user profile first.")
        select_vbs_map_profile()
        user = cfg.get('vbs_map_user','').strip()
        if not user:
            return

    host = cfg.get('vbs_map_server', 'localhost').strip()
    port = cfg.get('vbs_map_port',   '4080').strip()
    url = (
        f"http://{host}:{port}/#/external/login"
        f"?loginName={user}"
        f"&vbsFullComputerName={user}"
    )

    def _check_and_open():
        try:
            urllib.request.urlopen(f"http://{host}:{port}", timeout=1)
            post_ui(lambda: webbrowser.open(url, new=2))
        except Exception:
            post_ui(
                messagebox.showinfo,
                "External Map",
                "Note: VBS Map server must be running",
            )

    run_in_thread(_check_and_open)

def make_borderless(hwnd):
    """Strip only the thin border & titlebar out of a real toplevel."""
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
    style &= ~(WS_BORDER | WS_DLGFRAME)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)
    ctypes.windll.user32.SetWindowPos(
        hwnd, None, 0,0,0,0,
        SWP_NOMOVE|SWP_NOSIZE|SWP_NOZORDER|SWP_FRAMECHANGED
    )

def prompt_hostname(parent, initial=""):
    """Show a themed prompt for entering the main PC name."""
    top = tk.Toplevel(parent)
    apply_app_icon(top)
    top.title("Main PC Name")
    top.resizable(False, False)
    top.geometry("801x506")
    top.transient(parent)
    top.grab_set()

    if os.path.exists(prompt_box_image_path):
        img = Image.open(prompt_box_image_path).resize((801, 506), Image.Resampling.LANCZOS)
        ph = ImageTk.PhotoImage(img)
        lbl = tk.Label(top, image=ph)
        lbl.image = ph
        lbl.place(relwidth=1, relheight=1)
    else:
        top.configure(bg="#333333")

    var = tk.StringVar(value=initial)

    tk.Label(
        top,
        text="Enter Host PC name",
        font=("Helvetica", 18, "bold"),
        bg="#333333",
        fg="white"
    ).place(relx=0.5, rely=0.37, anchor="center")

    entry = tk.Entry(top, textvariable=var, font=("Helvetica", 20))
    entry.place(relx=0.5, rely=0.45, anchor="center", width=400)

    result = {"value": None}

    def on_ok():
        result["value"] = var.get().strip()
        top.destroy()

    def on_cancel():
        top.destroy()

    tk.Button(top, text="OK", command=on_ok, font=("Helvetica", 16)).place(relx=0.4, rely=0.7, anchor="center")
    tk.Button(top, text="Cancel", command=on_cancel, font=("Helvetica", 16)).place(relx=0.6, rely=0.7, anchor="center")

    entry.focus()
    parent.wait_window(top)
    return result["value"]

def prompt_project_name(parent):
    """Prompt for a PhotoMesh project name with validation."""
    top = tk.Toplevel(parent)
    apply_app_icon(top)
    top.title("Project Name")
    top.resizable(False, False)
    top.geometry("801x506")
    top.transient(parent)
    top.grab_set()

    if os.path.exists(prompt_box_image_path):
        img = Image.open(prompt_box_image_path).resize((801, 506), Image.Resampling.LANCZOS)
        ph = ImageTk.PhotoImage(img)
        lbl = tk.Label(top, image=ph)
        lbl.image = ph
        lbl.place(relwidth=1, relheight=1)
    else:
        top.configure(bg="#333333")

    var = tk.StringVar()

    tk.Label(
        top,
        text="Enter PhotoMesh project name",
        font=("Helvetica", 18, "bold"),
        bg="#333333",
        fg="white",
    ).place(relx=0.5, rely=0.37, anchor="center")

    entry = tk.Entry(top, textvariable=var, font=("Helvetica", 20))
    entry.place(relx=0.5, rely=0.45, anchor="center", width=400)

    result = {"value": None}

    def on_ok():
        result["value"] = var.get().strip()
        top.destroy()

    def on_cancel():
        top.destroy()

    ok_btn = tk.Button(top, text="OK", command=on_ok, font=("Helvetica", 16), state="disabled")
    ok_btn.place(relx=0.4, rely=0.7, anchor="center")
    tk.Button(top, text="Cancel", command=on_cancel, font=("Helvetica", 16)).place(relx=0.6, rely=0.7, anchor="center")

    def validate(*_):
        ok_btn.config(state="normal" if var.get().strip() else "disabled")

    var.trace_add("write", validate)

    entry.focus()
    validate()
    parent.wait_window(top)
    return result["value"]

# ─── MAINMENU PANEL ────────────────────────────────────────
class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        global APP_INSTANCE
        APP_INSTANCE = self
        pump_ui_queue(self)
        apply_app_icon(self)
        self.title("STE Mission Planning Toolkit")
        self.resizable(False, False)

        # List of buttons that can receive keyboard focus
        self.focusable_buttons = []

        self.fullscreen = config.getboolean('General', 'fullscreen', fallback=False)

        # base windowed size and scaling
        self.base_width, self.base_height = 1660, 800
        self.base_scaling = float(self.tk.call('tk', 'scaling'))

        # screen dims
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        # scale and geometry for windowed mode so it always fits on screen
        self.window_scale = min(sw / self.base_width, sh / self.base_height, 1.0)
        win_w = int(self.base_width * self.window_scale)
        win_h = int(self.base_height * self.window_scale)
        x = (sw - win_w) // 2
        y = (sh - win_h) // 2
        self.windowed_geometry = f"{win_w}x{win_h}+{x}+{y}"

        if self.fullscreen:
            scale = min(sw / self.base_width, sh / self.base_height)
            self.apply_scale(scale)
            self.geometry(f"{sw}x{sh}+0+0")
            self.attributes('-fullscreen', True)
        else:
            self.apply_scale(self.window_scale)
            self.geometry(self.windowed_geometry)

        # track live scale & throttle id
        self._live_scale = None
        self._cfg_job = None
        def log_message(msg):
            print(f"> {msg}")  
        self.log_message = log_message

        def _on_configure(event=None):
            if self._cfg_job is not None:
                self.after_cancel(self._cfg_job)
            self._cfg_job = self.after(25, self._recompute_scale)

        bootstrap_first_run_if_needed(log=self.log_message)

        def _recompute_scale():
            self._cfg_job = None
            self.update_idletasks()
            w = max(1, self.winfo_width())
            h = max(1, self.winfo_height())
            current_scale = self._live_scale if self._live_scale is not None else self.window_scale
            base_h = self.content.winfo_reqheight() / max(current_scale, 1e-6)
            # compute scale vs. design width and dynamic content height
            s = min(w / self.base_width, h / base_h)
            s = max(0.70, min(1.50, s))
            if self._live_scale is None or abs(self._live_scale - s) > 0.02:
                self._live_scale = s
                self.apply_scale(s)
                self.update_idletasks()
                # Re-evaluate scrollability after scaling changes
                if hasattr(self, '_update_scrollability'):
                    self.after(10, self._update_scrollability)

        self._recompute_scale = _recompute_scale
        # bind after initial geometry is set
        self.bind("<Configure>", _on_configure)

        set_background(self)

        self.header_bar = tk.Frame(self, bg="black", height=120)
        self.header_bar.pack(side="top", fill="x")

        # Left logo group
        self._logo_cache = {}
        def _load_logo(path, size):
            if not os.path.exists(path):
                return None
            key = (path, size)
            if key in self._logo_cache:
                return self._logo_cache[key]
            try:
                img = Image.open(path).convert("RGBA").resize(size, Image.Resampling.LANCZOS)
                ph = ImageTk.PhotoImage(img)
                self._logo_cache[key] = ph
                return ph
            except Exception:
                return None

        left_logo_frame = tk.Frame(self.header_bar, bg="black")
        left_logo_frame.pack(side="left", padx=10)
        for path, size in [
            (logo_STE_path, (70,70)),
            (logo_AFC_army, (60,70)),
            (logo_first_army, (45,75)),
        ]:
            ph = _load_logo(path, size)
            if ph:
                tk.Label(left_logo_frame, image=ph, bg="black").pack(side="left", padx=5, pady=5)

        right_logo_frame = tk.Frame(self.header_bar, bg="black")
        right_logo_frame.pack(side="right", padx=10)
        ph_us = _load_logo(logo_us_army_path, (200,76))
        if ph_us:
            tk.Label(right_logo_frame, image=ph_us, bg="black").pack(side="right", padx=5, pady=5)

        center_frame = tk.Frame(self.header_bar, bg="black")
        center_frame.pack(expand=True, fill="both")
        self.header_title = tk.Label(center_frame, text="STE Mission Planning Toolkit", font=("Helvetica", 28, "bold"), bg="black", fg="white")
        self.header_title.pack(pady=(10,0))
        self.header_subtitle = tk.Label(center_frame, text="Home", font=("Helvetica", 20, "bold"), bg="black", fg="white")
        self.header_subtitle.pack(pady=(0,10))

        # Mapping panel names to subtitles
        self._panel_subtitles = {
            'Main': 'Home',
            'VBS4': 'VBS4 / BlueIG',
            'OneClick': 'One-Click Terrain',
            'BVI': 'BVI',
            'Settings': 'Settings',
            'Tutorials': 'Tutorials  ❓',
            'Credits': 'Credits',
            'Contact Us': 'Contact Support',
        }

        close_btn = tk.Button(self, text="✕",
                              font=("Helvetica",12,"bold"),
                              bg="red", fg="white", bd=0,
                              command=self.destroy)
        close_btn.place(relx=1.0, x=-40, y=5, width=30, height=30)
        self.configure(bg="black")
        self.content = tk.Frame(self, bg="black", bd=0, highlightthickness=0)
        self.content.pack(expand=True, fill="both")

        nav = tk.Frame(self.content, bg='#333333')
        nav.pack(side='left', fill='y')
        self._init_scrollable_viewport()
        self.panels = {
            'Main':      MainMenu(self.panels_container, self),
            'VBS4':      VBS4Panel(self.panels_container, self),
            'OneClick':  OneClickPanel(self.panels_container, self),
            'BVI':       BVIPanel(self.panels_container, self),
            'Settings':  SettingsPanel(self.panels_container, self),
            'Tutorials': TutorialsPanel(self.panels_container, self),
            'Credits':   CreditsPanel(self.panels_container, self),
            'Contact Us': ContactSupportPanel(self.panels_container, self),
        }

        try:
            log_fn = self.panels.get('OneClick').log_message if 'OneClick' in self.panels else print
            enforce_photomesh_settings(log=log_fn)
        except Exception as exc:
            print(f"[wizard-enforce] {exc}")
        for panel in self.panels.values():
            panel.pack_forget()

        # Build the nav buttons
        nav_tip = Tooltip(nav)
        for key, label in [
            ('Main',     'Home'),
            ('VBS4',     'VBS4 / BlueIG'),
            ('OneClick', 'One-Click'),
            ('BVI',      'BVI'),
            ('Settings', 'Settings'),
            ('Tutorials','?'),
            ('Credits',  'Credits'),
            ('Contact Us', 'Contact Us'),
        ]:
            btn = tk.Button(nav, text=label,
                            font=("Helvetica", 18),
                            bg="#555", fg="white",
                            width=12,
                            command=lambda k=key: self.show(k))
            btn.pack(pady=5, padx=5)
            btn.bind("<Enter>", lambda e, l=label: nav_tip.show(f"Go to {l}", e.x_root+10, e.y_root+10))
            btn.bind("<Leave>", lambda e: nav_tip.hide())
            self.focusable_buttons.append(btn)

        tk.Button(nav, text="Exit", font=("Helvetica", 18),
                  bg="red", fg="white", command=self.destroy) \
            .pack(fill='x', pady=20, padx=5)
        tk.Label(nav, text="Use \u2191/\u2193 arrows to navigate",
                 bg="#333333", fg="white",
                 font=("Helvetica", 10)).pack(pady=(0, 10))

        enforce_local_fuser_policy()

        try:
            apply_offline_settings()
        except Exception as exc:
            print("[first-run] apply_offline_settings:", exc)

        # Start by showing "Main"
        self.current = None
        self.show('Main')

        # --- Keyboard navigation setup ---
        self.focus_index = 0
        self.focusable_buttons = []
        for key in ("<Right>", "<Down>"):
            self.bind(key, self.focus_next)
        for key in ("<Left>", "<Up>"):
            self.bind(key, self.focus_prev)
        self.bind("<Return>", self.activate_current)
        self.update_navigation()

    def apply_scale(self, scale: float) -> None:
        """Scale fonts and widgets proportionally using Tk scaling."""
        snapped = round(scale * 4) / 4.0
        self.tk.call('tk', 'scaling', self.base_scaling * snapped)

    def toggle_fullscreen(self):
        """Toggle fullscreen while maintaining aspect ratio."""
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        if not self.fullscreen:
            scale = min(screen_w / self.base_width, screen_h / self.base_height)
            self.apply_scale(scale)
            self.geometry(f"{screen_w}x{screen_h}+0+0")
            self.attributes('-fullscreen', True)
            self.fullscreen = True
        else:
            self.attributes('-fullscreen', False)
            self.window_scale = min(screen_w / self.base_width, screen_h / self.base_height, 1.0)
            win_w = int(self.base_width * self.window_scale)
            win_h = int(self.base_height * self.window_scale)
            x = (screen_w - win_w) // 2
            y = (screen_h - win_h) // 2
            self.apply_scale(self.window_scale)
            self.windowed_geometry = f"{win_w}x{win_h}+{x}+{y}"
            self.geometry(self.windowed_geometry)
            self.fullscreen = False

        self.after(10, self._update_scrollability)
        self.after(10, lambda: self.event_generate("<Configure>"))

    def _init_scrollable_viewport(self):
        """Initialize the canvas-based scrollable viewport for panels."""
        # Create the outer canvas (the viewport) with proper background
        self.viewport_canvas = tk.Canvas(self.content, highlightthickness=0, bg='black')
        self.viewport_canvas.pack(side='right', expand=True, fill='both')
        self.viewport_canvas.configure(yscrollincrement=1)
        self.viewport_scrollbar = tk.Scrollbar(self.viewport_canvas, orient='vertical', command=self.viewport_canvas.yview)
        self.viewport_canvas.configure(yscrollcommand=self.viewport_scrollbar.set)
        self._scroll_active = False
        self._scroll_timer = None
        self._wheel_accum = 0
        self._wheel_job = None
        self._bg_image_src = None
        self._bg_image_id = None
        try:
            if os.path.exists(background_image_path):
                self._bg_image_src = Image.open(background_image_path)
                self._bg_photo = ImageTk.PhotoImage(self._bg_image_src.resize((2,2)))
                self._bg_image_id = self.viewport_canvas.create_image(0, 0, image=self._bg_photo, anchor='nw')
        except Exception:
            self._bg_image_src = None
        self.panels_container = tk.Frame(self.viewport_canvas, bg='black')
        self.canvas_frame_id = self.viewport_canvas.create_window(0, 0, window=self.panels_container, anchor='nw')
        self.viewport_canvas.bind('<Configure>', self._on_canvas_configure)
        self.panels_container.bind('<Configure>', self._on_frame_configure)
        self.viewport_canvas.bind('<MouseWheel>', self._on_mousewheel)
        self.viewport_canvas.bind('<Button-4>', self._on_mousewheel)  
        self.viewport_canvas.bind('<Button-5>', self._on_mousewheel)  
        self.panels_container.bind('<MouseWheel>', self._on_mousewheel)
        self.panels_container.bind('<Button-4>', self._on_mousewheel)
        self.panels_container.bind('<Button-5>', self._on_mousewheel)
        self._scrollbar_shown = True
        self.after(50, self._place_overlay_scrollbar)

    def _place_overlay_scrollbar(self):
        """Position the overlay scrollbar at the right edge of the canvas."""
        try:
            sb_width = 18
            self.viewport_scrollbar.place(relx=1.0, x=-sb_width, y=0, width=sb_width, relheight=1.0)
            self.viewport_scrollbar.lift()
        except Exception:
            pass

    def _on_canvas_configure(self, event):
        """Handle canvas resize - update inner frame width and scrollability."""
        canvas_width = event.width
        self.viewport_canvas.itemconfig(self.canvas_frame_id, width=canvas_width)

        current_bg_size = getattr(self, '_last_bg_size', (0, 0))
        new_size = (event.width, event.height)
        size_changed = abs(new_size[0] - current_bg_size[0]) > 5 or abs(new_size[1] - current_bg_size[1]) > 5

        # Only touch the background image when we are NOT scrolling
        if size_changed and not getattr(self, '_scroll_active', False):
            self._last_bg_size = new_size
            self.after_idle(lambda: self._update_canvas_background(event.width, event.height))

        # Do NOT use bbox('all') here; scrollregion is handled in _on_frame_configure/_resize_canvas_to_panel
        self._update_scrollability()

    def _on_frame_configure(self, event):
        """Handle inner frame resize - update scroll region (frame-only)."""
        bbox = self.viewport_canvas.bbox(self.canvas_frame_id)
        if bbox:
            self.viewport_canvas.configure(scrollregion=bbox)
        self._update_scrollability()

    def _on_mousewheel(self, event):
        """Handle mouse wheel scrolling on the viewport canvas with batching."""
        # If we're in the Settings panel, check if the event is over the inner settings canvas
        try:
            if self.current == 'Settings':
                settings = self.panels.get('Settings')
                if settings is not None:
                    # Find if the event originated from the inner settings canvas
                    w = event.widget
                    while w is not None:
                        if w is getattr(settings, '_settings_canvas', None):
                            # If we're directly over the settings canvas or its scrollbar,
                            # let it handle the event (but don't break yet)
                            is_settings_scroll = True
                            break
                        w = getattr(w, 'master', None)
                    else:
                        # We're in Settings panel but not over the inner canvas,
                        # so use the outer scrollbar
                        is_settings_scroll = False
                else:
                    is_settings_scroll = False
            else:
                is_settings_scroll = False
        except Exception:
            is_settings_scroll = False

        # For Settings panel, prioritize the inner scroller when the event is over it
        if is_settings_scroll:
            # Let the event propagate to the inner settings scroller
            return
            
        # For other panels (or Settings panel outside the inner scroller area),
        # check if another scrollable widget has focus
        focused = self.focus_get()
        if focused and hasattr(focused, 'master'):
            parent = focused.master
            while parent is not None:
                clsname = getattr(parent, '__class__', None).__name__
                if clsname in ('Canvas', 'Scrollbar') and parent is not self.viewport_canvas:
                    return "break"  # Another scrollable has focus
                parent = getattr(parent, 'master', None)

        # Don't scroll if scrollbar isn't showing
        if not self._scrollbar_shown:
            return "break"

        delta = 0
        if hasattr(event, 'delta') and event.delta:
            delta = event.delta
        elif hasattr(event, 'num'):
            delta = -120 if event.num == 4 else 120 if event.num == 5 else 0
        self._wheel_accum += delta

        if self._wheel_job is not None:
            return "break"

        def _flush():
            steps = int(self._wheel_accum / 120)
            if steps:
                self._scroll_active = True
                if self._scroll_timer:
                    self.after_cancel(self._scroll_timer)
                self.viewport_canvas.yview_scroll(-steps, "units")
                self._scroll_timer = self.after(100, self._reset_scroll_state)

            self._wheel_accum = 0
            self._wheel_job = None

        self._wheel_job = self.after(8, _flush)
        return "break"
    
    def _reset_scroll_state(self):
        """Reset scroll state to allow background updates again."""
        self._scroll_active = False
        self._scroll_timer = None

    def _update_scrollability(self):
        """Show/hide viewport scrollbar based on content overflow and panel type."""
        try:
            self.viewport_canvas.update_idletasks()
            
            # Get the visible canvas height
            canvas_h = max(1, self.viewport_canvas.winfo_height())
            
            # Get the current visible panel
            panel = self.panels.get(self.current)
            if not panel:
                return
            
            # Get the actual panel height
            panel.update_idletasks()
            panel_h = panel.winfo_reqheight()
            
            # Special handling for Settings panel
            if self.current == 'Settings':
                # For Settings, always enable the outer scrollbar
                # Force a large enough content_h to ensure the scrollbar appears
                content_h = max(panel_h, canvas_h + 100)  # Make it always need scrolling
                needs_scroll = True
            else:
                # For other panels, calculate normally
                # Fallback approach: use the canvas_frame_id
                bbox = self.viewport_canvas.bbox(self.canvas_frame_id)
                if not bbox:
                    # Try with 'all' as a last resort
                    bbox = self.viewport_canvas.bbox('all')
                
                # Make sure we have a valid bounding box
                if bbox:
                    frame_h = bbox[3] - bbox[1]
                    # Use the larger of panel requested height or frame bbox
                    content_h = max(panel_h, frame_h)
                else:
                    content_h = panel_h
                
                # Determine if scrolling is needed - content must be noticeably larger than canvas
                needs_scroll = content_h > (canvas_h + 10)
            
            # Allow scrolling for all panels now
            use_outer_scroll = True
            
            # Debug logging
            if hasattr(self, 'debug_log'):
                self.debug_log(f"Panel '{self.current}': canvas_h={canvas_h}, content_h={content_h}, panel_h={panel_h}, needs_scroll={needs_scroll}")
            
            # Show scrollbar for all panels that need it, including Settings
            show_scrollbar = needs_scroll and use_outer_scroll
            
            # Apply scrollbar visibility change
            if show_scrollbar and not self._scrollbar_shown:
                self._place_overlay_scrollbar()
                self._scrollbar_shown = True
            elif not show_scrollbar and self._scrollbar_shown:
                try:
                    self.viewport_scrollbar.place_forget()
                except Exception:
                    pass
                # Ensure outer view resets when we hide the bar
                self.viewport_canvas.yview_moveto(0)
                self._scrollbar_shown = False
        except Exception as e:
            # If anything fails, keep the scrollbar visible by default
            print(f"Error in _update_scrollability: {e}")
            if not self._scrollbar_shown:
                self._place_overlay_scrollbar()
                self._scrollbar_shown = True

    def _reset_viewport_scroll(self):
        """Reset viewport scroll position to top."""
        self.viewport_canvas.yview_moveto(0)
        
    def _update_panel_background(self, panel):
        """Update the background of a panel to align with the main background."""
        try:
            # Make sure the panel is fully laid out
            panel.update_idletasks()
            
            # Re-apply the background with the current panel dimensions
            if panel and hasattr(panel, 'winfo_exists') and panel.winfo_exists():
                # Remove any existing background labels
                for child in panel.winfo_children():
                    if isinstance(child, tk.Label) and hasattr(child, 'image'):
                        try:
                            if str(child.cget('width')) == str(self.winfo_screenwidth()):
                                child.destroy()
                        except:
                            pass
                
                # Apply a fresh background with proper alignment
                set_background(self, panel)
        except Exception as e:
            print(f"Error updating panel background: {e}")

    def update_button_state(self, button, path_key):
        """Update button state based on whether the executable exists."""
        path = config['General'].get(path_key, '')
        if path and os.path.exists(path):
            button.config(state="normal")
        else:
            button.config(state="disabled")

    def show(self, name):
        """Display the named panel, repacking it inside the scroll viewport."""
        panel = self.panels[name]
        try:
            subtitle = self._panel_subtitles.get(name, name)
            self.header_subtitle.config(text=subtitle)
        except Exception:
            pass
        self._scroll_active = False
        if hasattr(self, '_scroll_timer') and self._scroll_timer:
            self.after_cancel(self._scroll_timer)
            self._scroll_timer = None
        # Reset wheel batching state
        self._wheel_accum = 0
        if hasattr(self, '_wheel_job') and self._wheel_job:
            self.after_cancel(self._wheel_job)
            self._wheel_job = None
            
        # Hide all panels then show the requested one
        for p in self.panels.values():
            p.pack_forget()
        force_full_height = name not in ("Credits", "Contact Us")
        try:
            panel.pack_propagate(False if force_full_height else True)
        except Exception:
            pass
        panel.pack(fill='both', expand=True)
        self.current = name
        self._reset_viewport_scroll()
        
        # Let the panel fully layout first
        self.after(1, lambda p=panel: self._resize_canvas_to_panel(p))
        
        # Re-apply the background with correct alignment after the panel is shown
        self.after(50, lambda p=panel: self._update_panel_background(p))
        
        if name == "VBS4":
            panel.update_vbs4_version()
            self.update_button_state(panel.vbs4_launcher_button, 'vbs4_setup_path')
            self.update_button_state(panel.vbs_license_button, 'vbs_license_manager_path')
            self.update_button_state(panel.blueig_button, 'blueig_path')
        elif name == "OneClick":
            panel.update_fuser_state()
            panel.refresh_rm_status()
        elif name == "BVI":
            self.update_button_state(panel.bvi_button, 'bvi_manager_path')
        elif name == "Tutorials":
            # Special handling for Tutorials panel to ensure transparent backgrounds
            panel.configure(bg="")
            # Schedule multiple background fixes
            self.after(50, lambda: hasattr(panel, '_ensure_background_visible') and panel._ensure_background_visible())
            self.after(200, lambda: hasattr(panel, '_ensure_background_visible') and panel._ensure_background_visible())
        elif name == "Settings":
            # Force scrollbar to show for Settings panel
            self._scrollbar_shown = False  # Reset state so it will re-evaluate
            
        self.update_navigation()
        
        # Schedule multiple scrollability checks with increasing delays
        # This ensures we catch cases where panel content takes time to render
        self.after(10, self._update_scrollability)
        self.after(100, self._update_scrollability)
        self.after(300, self._update_scrollability)
        
        # Extra check specifically for Settings panel to ensure it gets scrollbar
        if name == "Settings":
            def force_settings_scrollbar():
                if not self._scrollbar_shown:
                    self._place_overlay_scrollbar()
                    self._scrollbar_shown = True
            self.after(500, force_settings_scrollbar)
        
        # Handle scaling
        self.after(0, self._recompute_scale)

    def _resize_canvas_to_panel(self, panel):
        """Force scrollregion to the visible panel's requested size (frame-only)."""
        try:
            # Make sure the panel has had a chance to compute its full size
            panel.update_idletasks()
            self.viewport_canvas.update_idletasks()
            
            # Try to get bbox from the frame window
            bbox = self.viewport_canvas.bbox(self.canvas_frame_id)
            
            # If we can't get a bbox, fall back to panel's requested dimensions
            if not bbox:
                req_w = panel.winfo_reqwidth()
                req_h = panel.winfo_reqheight()
                bbox = (0, 0, req_w, req_h)
            
            # Set the scrollregion generously to ensure scrollability when needed
            # Add a small buffer to height to ensure the last elements are fully visible
            x1, y1, x2, y2 = bbox
            self.viewport_canvas.configure(scrollregion=(x1, y1, x2, y2 + 20))
            
            # Force update scrollability state
            self.after(50, self._update_scrollability)
        except Exception as e:
            print(f"Error in _resize_canvas_to_panel: {e}")
            pass

    def _update_canvas_background(self, width=None, height=None):
        """Update / resize the shared background image for the viewport."""
        if not self._bg_image_src:
            return
        if width is None:
            width = max(2, self.viewport_canvas.winfo_width())
        if height is None:
            height = max(2, self.viewport_canvas.winfo_height())
        
        if width < 10 or height < 10:
            return
        
        current_bg_img_size = getattr(self, '_bg_current_size', (0, 0))
        if abs(width - current_bg_img_size[0]) < 5 and abs(height - current_bg_img_size[1]) < 5:
            return  # Skip if size change is minimal

        try:
            self.panels_container.update_idletasks()
            content_h = max(height, self.panels_container.winfo_reqheight())
            height = max(height, content_h)
        except Exception:
            pass
            
        try:
            resized = self._bg_image_src.resize((width, height), Image.Resampling.LANCZOS)
            self._bg_photo = ImageTk.PhotoImage(resized)
            self._bg_current_size = (width, height)
            
            if self._bg_image_id is None:
                self._bg_image_id = self.viewport_canvas.create_image(0, 0, image=self._bg_photo, anchor='nw')
            else:
                self.viewport_canvas.itemconfig(self._bg_image_id, image=self._bg_photo)
            if self._bg_image_id is not None:
                self.viewport_canvas.tag_lower(self._bg_image_id)
        except Exception:
            pass

    def _apply_panel_wallpaper(self, panel):
        """Place/resize a wallpaper image inside a panel so it scrolls."""
        if not os.path.exists(background_image_path):
            return
        try:
            panel.update_idletasks()
            vw = max(1, self.viewport_canvas.winfo_width())
            vh = max(1, self.viewport_canvas.winfo_height())
            pw = max(vw, panel.winfo_reqwidth())
            ph = max(vh, panel.winfo_reqheight())
            # Put an upper bound to avoid creating gigantic images.
            pw = min(pw, 3840)
            ph = min(ph, 4320)
            # Skip tiny initial calls until geometry stabilizes
            if pw < 100 or ph < 100:
                return
            last_size = getattr(panel, '_bg_last_size', None)
            if last_size == (pw, ph):
                return  
            from PIL import Image
            img = Image.open(background_image_path).resize((pw, ph), Image.Resampling.LANCZOS)
            panel._bg_panel_photo = ImageTk.PhotoImage(img)
            panel._bg_last_size = (pw, ph)
            if not hasattr(panel, '_bg_panel_label') or panel._bg_panel_label is None:
                lbl = tk.Label(panel, image=panel._bg_panel_photo, bd=0, highlightthickness=0)
                panel._bg_panel_label = lbl
                lbl.place(relwidth=1, relheight=1)
                lbl.lower() 
            else:
                panel._bg_panel_label.configure(image=panel._bg_panel_photo)
        except Exception:
            pass

    def change_projects_root(self):
        new_root = filedialog.askdirectory(title="Choose Projects Root", parent=self)
        if new_root:
            set_projects_root(new_root)
            if hasattr(self, "log_message"):
                try:
                    self.log_message(f"Projects root updated: {new_root}")
                except Exception:
                    pass

    def collect_buttons(self, widget):
        """Recursively collect all enabled Button widgets."""
        buttons = []
        for child in widget.winfo_children():
            if isinstance(child, tk.Button) and str(child.cget("state")) == "normal":
                buttons.append(child)
            buttons.extend(self.collect_buttons(child))
        return buttons

    def update_navigation(self):
        """Update the list of buttons that can receive focus."""
        panel = self.panels.get(self.current)
        if not panel:
            self.focusable_buttons = []
            return
        self.focusable_buttons = self.collect_buttons(panel)
        self.focus_index = 0
        self.highlight_current()

    def highlight_current(self):
        for b in getattr(self, 'focusable_buttons', []):
            b.config(highlightthickness=0)
        if self.focusable_buttons:
            btn = self.focusable_buttons[self.focus_index]
            btn.focus_set()
            btn.config(highlightbackground="white", highlightthickness=2)

    def focus_next(self, event=None):
        if not self.focusable_buttons:
            return
        self.focus_index = (self.focus_index + 1) % len(self.focusable_buttons)
        self.highlight_current()

    def focus_prev(self, event=None):
        if not self.focusable_buttons:
            return
        self.focus_index = (self.focus_index - 1) % len(self.focusable_buttons)
        self.highlight_current()

    def activate_current(self, event=None):
        """Invoke the currently focused button."""
        if not self.focusable_buttons:
            return
        btn = self.focusable_buttons[self.focus_index]
        try:
            btn.invoke()
        except Exception:
            pass

    def create_tutorial_button(self, parent):
        """
        This method places a small “?” button in the given panel (parent).
        All panels call this inside their __init__ to add the tutorial button.
        """
        button = tk.Button(parent, text="?", 
                           font=("Helvetica", 16, "bold"),
                           bg="red", fg="white",
                           width=2, height=1,
                           command=lambda: self.show('Tutorials'))
        button.place(x=1350, y=110, anchor="nw")

        if isinstance(parent, VBS4Panel):
            parent.create_battlespaces_button()

    def set_file_location(self, app_name, config_key, button):
        path = filedialog.askopenfilename(
            title=f"Select {app_name} Executable",
            filetypes=[("Executable Files", "*.exe")]
        )
        if path and os.path.exists(path):
            config['General'][config_key] = clean_path(path)
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
            messagebox.showinfo("Success", f"{app_name} path set to:\n{path}")
            button.config(state="normal", bg="#444444")
            if app_name == "VBS4":
                self.panels['VBS4'].update_vbs4_version()
            elif app_name == "BlueIG":
                self.panels['VBS4'].update_blueig_version()
            elif app_name == "BVI":
                self.panels['BVI'].update_bvi_version()
        else:
            messagebox.showerror("Error", f"Invalid {app_name} path selected.")

    def run_oneclick_conversion(self) -> None:
        """Kick off the full One-Click Terrain pipeline."""
        panel = self.panels.get('OneClick')
        if panel:
            panel.on_run_oneclick()

    def launch_reality_mesh_to_vbs4(self) -> None:
        """Open the Reality Mesh to VBS4 application."""
        panel = self.panels.get('OneClick')
        if panel:
            panel.launch_reality_mesh_to_vbs4()

    def destroy(self):
        global APP_INSTANCE
        try:
            super().destroy()
        finally:
            if APP_INSTANCE is self:
                APP_INSTANCE = None

# ─── ---------------- MAINMENU PANEL --------------------------------- ──────────

class MainMenu(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.configure(bg="black")
        set_background(controller, self)
        controller.create_tutorial_button(self) 
        self.controller = controller

        self.blueig_frame = tk.Frame(
            self,
            bg="#333333",
            bd=0,
            highlightthickness=0,
        )
        self.blueig_frame.pack(pady=10)
        self.create_blueig_button()

        # Other buttons
        for txt, cmd in [
            ("Launch VBS4 Launcher", launch_vbs4_setup),
            ("Launch BVI", launch_bvi),
            ("Settings", lambda: controller.show("Settings")),
            ("Tutorials", lambda: controller.show("Tutorials")),
            ("Credits", lambda: controller.show("Credits")),
            ("Exit", controller.destroy),
        ]:
            state = "normal"
            bg    = "#444444"
            if txt == "Launch BVI":
                path = get_ares_manager_path()
                if not path or not os.path.isfile(path):
                    state = "disabled"
                    bg    = "#888888"
            elif txt == "Launch VBS4 Launcher":
                path = config['General'].get('vbs4_setup_path', '')
                if not path or not os.path.isfile(path):
                    state = "disabled"
                    bg = "#888888"

            button = tk.Button(
                self,
                text=txt,
                font=("Helvetica", 24),
                bg=bg, fg="white",
                width=30, height=1,
                command=cmd,
                state=state
            )
            button.pack(pady=10)

    def create_blueig_button(self):
        for widget in self.blueig_frame.winfo_children():
            widget.destroy()

        btn = tk.Button(
            self.blueig_frame,
            text="Launch BlueIG",
            font=("Helvetica", 24),
            bg="#888888", fg="white",
            width=30, height=1,
            state="disabled",
        )
        btn.pack()

        is_srv = config["General"].getboolean("is_server", fallback=False)
        if is_srv:
            return

        checking = tk.Label(
            self.blueig_frame,
            text="Checking...",
            bg=self.blueig_frame.cget("bg"),
            fg="white",
        )
        checking.pack()

        def _resolve():
            path_ok = bool(get_blueig_install_path())

            def _apply():
                if path_ok:
                    btn.config(state="normal", bg="#444444", command=self.launch_blueig_with_exercise_id)
                checking.destroy()

            post_ui(_apply)

        run_in_thread(_resolve)

    def launch_blueig_with_exercise_id(self):
        panel = self.controller.panels.get("VBS4") if hasattr(self.controller, "panels") else None
        if panel and hasattr(panel, "launch_blueig_with_exercise_id"):
            panel.launch_blueig_with_exercise_id()

    def open_url(self, url: str) -> None:
        """Open a web URL in the default browser."""
        webbrowser.open(url, new=2)

    def update_blueig_state(self):
        self.create_blueig_button()
  
class VBS4Panel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        set_background(controller, self)
        controller.create_tutorial_button(self)
        self.configure(bg="black") 

        # --- Main actions ----------------------------------------------------
        self.vbs4_launcher_button = self.make_button(
            "Launch VBS4 Launcher", launch_vbs4_setup
        )
        self.vbs4_launcher_button.pack(pady=15)

        self.vbs4_launcher_version_label = tk.Label(
            self,
            text="Version: Unknown",
            font=("Helvetica", 16),
            bg="black",
            fg="white",
            bd=0,
            highlightthickness=0,
        )
        self.vbs4_launcher_version_label.pack(pady=(0, 15))

        self.blueig_button = self.make_button(
            "Launch BlueIG", self.launch_blueig_with_exercise_id
        )
        self.blueig_button.pack(pady=15)

        self.vbs_license_button = self.make_button(
            "Launch VBS License Manager", self.launch_vbs_license_manager
        )
        self.vbs_license_button.pack(pady=15)

        self.external_map_button = self.make_button(
            "External Map", open_external_map
        )
        self.external_map_button.pack(pady=15)

        self.back_button = self.make_button(
            "Back", lambda: controller.show("Main")
        )
        self.back_button.pack(pady=(15, 0))

        # --- Log area --------------------------------------------------------
        self.log_frame = tk.Frame(self, bg=self.cget("bg"), bd=0, highlightthickness=0)
        self.log_frame.pack(side="bottom", fill="x", padx=10, pady=(5, 0))

        tk.Label(
            self.log_frame,
            text="Activity Log",
            font=("Helvetica", 16, "bold"),
            bg=self.log_frame.cget("bg"),
            fg="white",
            bd=0,
            highlightthickness=0,
        ).pack(anchor="w")

        self.log_text = tk.Text(
            self.log_frame,
            height=3,
            bg=self.log_frame.cget("bg"),
            fg="white",
            wrap="word",
            bd=0,
            highlightthickness=0,
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.config(state="disabled")
        self.log_expanded = False
        ui_log_schedule_flush(controller, self.log_text)

        # --- Progress bar ----------------------------------------------------
        progress_frame = tk.Frame(
            self.log_frame, bg=self.log_frame.cget("bg"), bd=0, highlightthickness=0
        )
        progress_frame.pack(fill="x", pady=(5, 0))

        self.progress_var = tk.IntVar(value=0)
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Green.Horizontal.TProgressbar",
            troughcolor=self.log_frame.cget("bg"),
            background="#00aa00",
        )
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            orient="horizontal",
            mode="determinate",
            style="Green.Horizontal.TProgressbar",
        )
        self.progress_bar.pack(side="left", fill="x", expand=True)

        self.progress_label = tk.Label(
            progress_frame,
            text="0%",
            font=("Helvetica", 12),
            bg=progress_frame.cget("bg"),
            fg="white",
            width=5,
            bd=0,
            highlightthickness=0,
        )
        self.progress_label.pack(side="right", padx=(5, 0))

        button_frame = tk.Frame(
            self.log_frame, bg=self.log_frame.cget("bg"), bd=0, highlightthickness=0
        )
        button_frame.pack(fill="x", pady=5)

        self.toggle_log_button = tk.Button(
            button_frame,
            text="Expand Log",
            command=self.toggle_log,
            bg="#555",
            fg="white",
            bd=0,
            highlightthickness=0,
        )
        self.toggle_log_button.pack(side="left")

        tk.Button(
            button_frame,
            text="Clear Log",
            command=self.clear_log,
            bg="#555",
            fg="white",
            bd=0,
            highlightthickness=0,
        ).pack(side="right")

        self.update_vbs4_version()
        self.update_button_states()

    def make_button(self, text, command):
        return tk.Button(
            self,
            text=text,
            font=("Helvetica", 24),
            bg="#444444",
            fg="white",
            activebackground="#666666",
            activeforeground="white",
            width=30,
            height=1,
            command=command,
            bd=0,
            highlightthickness=0,
            relief="flat",
            overrelief="flat",
            takefocus=False,
        )

    def update_vbs4_version(self):
        """Set the launcher version label using the VBS4.exe file version."""

        def _work():
            vbs4_path = get_vbs4_install_path()
            ver = get_vbs4_version(vbs4_path) if vbs4_path else "Unknown"

            def _apply():
                if hasattr(self, "vbs4_version_label") and self.vbs4_version_label:
                    self.vbs4_version_label.config(text=f"Version: {ver}")
                if hasattr(self, "vbs4_launcher_version_label"):
                    self.vbs4_launcher_version_label.config(text=f"Version: {ver}")

            post_ui(_apply)

        run_in_thread(_work)

    def update_button_states(self):
        self.vbs4_launcher_button.config(
            state="normal" if config['General'].get('vbs4_setup_path', '') else "disabled",
            bg="#444444" if config['General'].get('vbs4_setup_path', '') else "#888888"
        )
        self.blueig_button.config(
            state="normal" if get_blueig_install_path() else "disabled",
            bg="#444444" if get_blueig_install_path() else "#888888"
        )
        self.vbs_license_button.config(
            state="normal" if config['General'].get('vbs_license_manager_path', '') else "disabled",
            bg="#444444" if config['General'].get('vbs_license_manager_path', '') else "#888888"
        )

    def log_message(self, message):
        post_ui(log_to_console, f"> {message}")

    def clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state="disabled")

    def toggle_log(self):
        if self.log_expanded:
            self.log_text.config(height=3)
            self.toggle_log_button.config(text="Expand Log")
            self.log_expanded = False
        else:
            self.log_text.config(height=15)
            self.toggle_log_button.config(text="Collapse Log")
            self.log_expanded = True

    def set_progress(self, value: int):
        self.progress_var.set(value)
        self.progress_label.config(text=f"{value}%")

    def launch_blueig_with_exercise_id(self):
        exe = config["General"].get("blueig_path", "").strip()
        if not exe or not os.path.isfile(exe):
            messagebox.showerror(
                "Error",
                "BlueIG executable not found. Please set it in the Settings panel."
            )
            return

        raw_id = simpledialog.askstring(
            "Exercise ID",
            "Enter Exercise ID (e.g., destroyer):",
            parent=self
        )
        if not raw_id:
            return
        exercise_id = self._sanitize_exercise_id(raw_id)
        if not exercise_id:
            messagebox.showerror("Invalid ID", "Exercise ID cannot be empty.")
            return

        host_name = f"exercise-{exercise_id}"
        try:
            set_host(host_name)
        except Exception:
            pass

        if hasattr(self.controller, "panels") and "OneClick" in self.controller.panels:
            pnl = self.controller.panels["OneClick"]
            if hasattr(pnl, "log_message"):
                pnl.log_message(f"Host set to: {host_name}")

        scenario = f"Exercise-{exercise_id}"
        args = [
            exe,
            "-hmd=openxr_ctr:oculus",
            f"-vbsHostExerciseID={scenario}",
            "-splitCPU",
            "-DJobThreads=8",
            "-DJobPool=8",
        ]

        try:
            subprocess.Popen(args, cwd=os.path.dirname(exe))
            if is_close_on_launch_enabled():
                sys.exit(0)
        except Exception as e:
            messagebox.showerror("Launch Failed", f"Couldn't launch BlueIG:\n{e}")

    def _sanitize_exercise_id(self, s: str) -> str:
        import re
        s = (s or "").strip().lower()
        return re.sub(r"[^a-z0-9\-]+", "-", s)

    def launch_vbs_license_manager(self):
        vbs_license_manager_path = config['General'].get('vbs_license_manager_path', '')
        if not vbs_license_manager_path or not os.path.exists(vbs_license_manager_path):
            messagebox.showerror("Error", "VBS License Manager path not set or invalid. Please set it in the settings.")
            return

        try:
            subprocess.Popen([vbs_license_manager_path])
            if is_close_on_launch_enabled():
                sys.exit(0)
        except FileNotFoundError:
            logging.exception("VBS License Manager not found")
            messagebox.showerror("Launch Failed", "VBS License Manager not found.")
        except OSError as e:
            logging.exception("Failed to launch VBS License Manager")
            messagebox.showerror("Launch Failed", f"Couldn't launch VBS License Manager:\n{e}")

    def update_blueig_state(self):
        """Re‐draw the single BlueIG button if 'is_server' toggles."""
        self.create_blueig_button()

    def show_tooltip(self, event, text=None):
        # If text is not provided, use the default text
        if text is None:
            text = "Open local Battlespaces folder"
        x = event.x_root + 10
        y = event.y_root + 20

        self.tooltip.show(text, x, y)

    def create_battlespaces_button(self):
        button = tk.Button(
            self,
            text="📁",
            font=("Helvetica", 16, "bold"),
            bg="orange", fg="black",
            width=2, height=1,
            command=self.open_battlespaces_folder
        )
        button.place(x=1300, y=110, anchor="nw")

        # Bind enter/leave on the button
        button.bind("<Enter>", self.show_tooltip)
        button.bind("<Leave>", self.hide_tooltip)

    def create_vbs4_folder_button(self):
        button = tk.Button(
            self,
            text="📂",
            font=("Helvetica", 16, "bold"),
            bg="lightblue", fg="black",
            width=2, height=1,
            command=self.open_vbs4_folder
        )
        button.place(x=1250, y=110, anchor="nw")

        # Bind enter/leave on the button
        button.bind("<Enter>", lambda e: self.show_tooltip(e, "Open VBS4 installation folder"))
        button.bind("<Leave>", self.hide_tooltip)

    def open_battlespaces_folder(self):
        battlespaces_path = os.path.expanduser(r"~\Documents\VBS4\Battlespaces")
        if os.path.exists(battlespaces_path):
            os.startfile(battlespaces_path)
        else:
            messagebox.showerror("Error", "VBS4 Battlespaces folder not found.")

    def open_vbs4_folder(self):
        vbs4_path = get_vbs4_install_path()
        if vbs4_path:
            folder_path = os.path.dirname(vbs4_path)
            if os.path.exists(folder_path):
                os.startfile(folder_path)
            else:
                messagebox.showerror("Error", "VBS4 installation folder not found.")
        else:
            messagebox.showerror("Error", "VBS4 path not set. Please set it in the settings.")
    
    def hide_tooltip(self, event):
        self.tooltip.hide()

    def update_vbs4_button_state(self):
        if not hasattr(self, "vbs4_button"):
            return

        def _work():
            path = get_vbs4_install_path()
            logging.debug("Updating VBS4 button state. Path: %s", path)
            ok = path and os.path.isfile(path)

            def _apply():
                if ok:
                    self.vbs4_button.config(state="normal", bg="#444444")
                else:
                    self.vbs4_button.config(state="disabled", bg="#888888")

            post_ui(_apply)

        run_in_thread(_work)

    def update_vbs4_launcher_button_state(self):
        def _work():
            path = get_vbs4_launcher_path()
            ok = path and os.path.exists(path)

            def _apply():
                if ok:
                    self.vbs4_launcher_button.config(state="normal", bg="#444444")
                else:
                    self.vbs4_launcher_button.config(state="disabled", bg="#888888")

            post_ui(_apply)

        run_in_thread(_work)

    def set_file_location(self, app_name, config_key, button):
        path = filedialog.askopenfilename(
            title=f"Select {app_name} Executable",
            filetypes=[("Executable Files", "*.exe")]
        )
        if path and os.path.exists(path):
            config['General'][config_key] = clean_path(path)
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
            messagebox.showinfo("Success", f"{app_name} path set to:\n{path}")
            button.config(state="normal", bg="#444444")
            if app_name == "VBS4":
                self.update_vbs4_version()
                if hasattr(self, "vbs4_button"):
                    self.update_vbs4_button_state()
        else:
            messagebox.showerror("Error", f"Invalid {app_name} path selected.")
    
    def select_imagery(self):
        """Allow the user to choose one or more imagery folders."""

        folders = []

        # Create the modal top-level window
        folder_window = tk.Toplevel(self)
        apply_app_icon(folder_window)
        folder_window.title("Select Imagery Folders")
        folder_window.geometry("700x500")
        folder_window.resizable(False, False)
        folder_window.transient(self)
        folder_window.grab_set()
        folder_window.attributes("-topmost", True)
        folder_window.configure(bg=self.cget("bg"))

        if os.path.exists(prompt_box_image_path):
            img = Image.open(prompt_box_image_path).resize(
                (801, 506), Image.Resampling.LANCZOS
            )
            ph = ImageTk.PhotoImage(img)
            bg_label = tk.Label(folder_window, image=ph, borderwidth=0)
            bg_label.image = ph
            bg_label.place(relwidth=1, relheight=1)

        # Header
        tk.Label(
            folder_window,
            text="Selected Imagery Folders:",
            font=("Helvetica", 14, "bold"),
            bg=folder_window.cget("bg"),
            fg="white",
            bd=0,
            highlightthickness=0,
        ).pack(pady=(20, 5))

        # Folder listbox
        folder_listbox = tk.Listbox(
            folder_window,
            width=80,
            height=10,
            bg="#1e1e1e",
            fg="white",
            selectbackground="#444",
            bd=0,
            highlightthickness=0,
        )
        folder_listbox.pack(pady=10)

        def add_folder():
            input_path = simpledialog.askstring(
                "Network Path",
                "Enter network folder path (leave blank to browse):",
                parent=folder_window,
            )
            if input_path:
                path = clean_path(input_path)
                if os.path.isdir(path):
                    selected = filedialog.askdirectory(
                        title="Select DCIM or base imagery folder",
                        initialdir=path,
                        parent=folder_window,
                    )
                    if selected:
                        found = get_image_folders_recursively(clean_path(selected))
                        folders.extend(found)
                else:
                    messagebox.showerror(
                        "Invalid Path",
                        f"The path '{input_path}' does not exist.",
                        parent=folder_window,
                    )
            else:
                selected = filedialog.askdirectory(
                    title="Select DCIM or base imagery folder", parent=folder_window
                )
                if selected:
                    found = get_image_folders_recursively(clean_path(selected))
                    folders.extend(found)

            # Update listbox
            folder_listbox.delete(0, tk.END)
            for folder in folders:
                folder_listbox.insert(tk.END, folder)

        def remove_folder():
            selected_indices = folder_listbox.curselection()
            for index in reversed(selected_indices):
                del folders[index]
                folder_listbox.delete(index)

        def finish_selection():
            """Finalize folder choice if at least one folder was added."""
            if not folders:
                messagebox.showwarning(
                    "No Selection", "No folder selected.", parent=folder_window
                )
                return

            norm_folders = [clean_path(f) for f in folders]
            self.image_folder_paths = norm_folders
            self.image_folder_path = ";".join(norm_folders)
            if SHOW_SELECTION_TOAST:
                messagebox.showinfo(
                    "Imagery Selected",
                    f"Selected imagery folders:\n{', '.join(self.image_folder_paths)}",
                    parent=folder_window,
                )
            else:
                # keep a breadcrumb in the log; 
                if hasattr(self, "log_message"):
                    self.log_message(
                        f"Imagery selected: {', '.join(self.image_folder_paths)}"
                    )
            self.log_message("Selected imagery folders:")
            for folder in norm_folders:
                self.log_message(f" - {folder}")
            folder_window.destroy()

        def cancel_selection():
            """Close the imagery selection window without saving."""
            folder_window.destroy()

        # --- Button Frame ---
        button_frame = tk.Frame(folder_window, bg=folder_window.cget("bg"), bd=0, highlightthickness=0)
        button_frame.pack(pady=20)

        def styled_btn(text, cmd):
            return tk.Button(
                button_frame,
                text=text,
                command=cmd,
                font=("Helvetica", 12, "bold"),
                bg="#444",
                fg="white",
                activebackground="#666",
                width=18,
                height=2,
                bd=0,
            )

        styled_btn("➕ Add Folder", add_folder).pack(side=tk.LEFT, padx=10)
        styled_btn("❌ Remove Selected", remove_folder).pack(side=tk.LEFT, padx=10)
        styled_btn("✅ Finish", finish_selection).pack(side=tk.LEFT, padx=10)
        styled_btn("Cancel", cancel_selection).pack(side=tk.LEFT, padx=10)

        folder_window.wait_window()

    def prompt_remote_fuser_details(self, ip):
        remote_path = simpledialog.askstring(
            "Remote Folder Path",
            fr"Enter shared folder path on {ip} (e.g., \\{ip}\SharedMeshDrive\WorkingFuser):",
            parent=self,
        )
        fuser_name = simpledialog.askstring("Fuser Name", f"Enter unique fuser name for {ip}:", parent=self)
        return remote_path, fuser_name

    def resolve_machine_name(self, ip: str) -> str | None:
        """Try to get the machine name for an IP or prompt the user."""
        try:
            host, _, _ = socket.gethostbyaddr(ip)
            return host.split('.')[0]
        except Exception:
            pass

        return simpledialog.askstring("Machine Name", f"Enter machine name for {ip}:", parent=self)

    def launch_fusers(self, ip_list):
        config_file = config['Fusers'].get('config_path', 'fuser_config.json')
        fuser_exe = config['Fusers'].get(
            'local_fuser_exe',
            r'C:\\Program Files\\Skyline\\PhotoMesh\\Fuser\\PhotoMeshFuser.exe'
        )

        def discover_fusers_from_shared_path(shared_path):
            """Scan *shared_path* for folders named like MACHINE(IP)_Fuser."""
            discovered = {}
            if not shared_path or not os.path.isdir(shared_path):
                return discovered

            pattern = re.compile(r"([^()]+)\(([^()]+)\)_(.+)")
            for entry in os.scandir(shared_path):
                if entry.is_dir():
                    m = pattern.match(entry.name)
                    if m:
                        machine, ip, name = m.groups()
                        discovered.setdefault(ip, []).append({
                            'name': name,
                            'machine_name': machine,
                            'shared_path': shared_path,
                        })
            return discovered

        def load_fuser_config(file_path):
            full_path = os.path.join(BASE_DIR, file_path) if not os.path.isabs(file_path) else file_path
            try:
                with open(full_path, 'r') as f:
                    data = json.load(f)
                    return data.get('fusers', {}), data.get('shared_path')
            except Exception as e:
                self.log_message(f"Failed to load fuser config: {e}")
                return {}, None

        fuser_settings, default_path = load_fuser_config(config_file)
        o = get_offline_cfg()
        if o["enabled"]:
            default_path = resolve_network_working_folder_from_cfg(o)
            if not can_access_unc(default_path):
                messagebox.showerror("Offline Mode", OFFLINE_ACCESS_HINT)
                return

        # Auto-discover fuser directories if a shared path is provided
        discovered = discover_fusers_from_shared_path(default_path)
        for ip, info in discovered.items():
            fuser_settings.setdefault(ip, []).extend(info)

        # If user did not supply IPs, run for all discovered/configured IPs
        if not ip_list:
            ip_list = list(fuser_settings.keys())

        for ip in ip_list:
            fusers = fuser_settings.get(ip, [])
            if not fusers:
                self.log_message(f"No fuser configuration found for {ip}")
                remote_path, fuser_name = self.prompt_remote_fuser_details(ip)
                if remote_path and fuser_name:
                    fusers = [{
                        'name': fuser_name,
                        'shared_path': remote_path,
                        'machine_name': self.resolve_machine_name(ip),
                    }]
                else:
                    continue

            for fuser in fusers:
                name = fuser.get('name')
                path = fuser.get('shared_path') or default_path
                machine_name = fuser.get('machine_name') or self.resolve_machine_name(ip)
                if not path:
                    share = (o.get("share_name") or "SharedMeshDrive").strip() or "SharedMeshDrive"
                    subdir = (o.get("working_fuser_subdir") or "WorkingFuser").strip() or "WorkingFuser"
                    path = rf'\\{ip}\\{share}\\{subdir}'
                if not path:
                    self.log_message(f"No shared path for {name} on {ip}")
                    continue

                bat_path = rf'\\{ip}\\C$\\Program Files\\Skyline\\PhotoMesh\\Fuser\\{name}.bat'
                if os.path.isfile(bat_path):
                    cmd = f'start "" "{bat_path}"'
                else:
                    cmd = f'start "" "{fuser_exe}" "{name}" "{path}" 0 true'

                try:
                    subprocess.run(cmd, shell=True, check=True)
                    host = machine_name or ip
                    self.log_message(f"Launched {name} on {host} at {path}")
                except subprocess.CalledProcessError as e:
                    self.log_message(f"Failed to launch {name} on {ip}: {e}")

        # Launch local fusers on this machine
        self.launch_local_fuser(default_path)

    def launch_local_fuser(self, shared_path=None):
        config_file = config['Fusers'].get('config_path', 'fuser_config.json')
        fuser_exe = config['Fusers'].get(
            'local_fuser_exe',
            r'C:\\Program Files\\Skyline\\PhotoMesh\\Fuser\\PhotoMeshFuser.exe'
        )

        def load_fuser_config(file_path):
            full_path = os.path.join(BASE_DIR, file_path) if not os.path.isabs(file_path) else file_path
            try:
                with open(full_path, 'r') as f:
                    data = json.load(f)
                    return data.get('shared_path')
            except Exception as e:
                self.log_message(f"Failed to load fuser config: {e}")
                return None

        o = get_offline_cfg()
        if o["enabled"]:
            default_path = resolve_network_working_folder_from_cfg(o)
            if not can_access_unc(default_path):
                messagebox.showerror("Offline Mode", OFFLINE_ACCESS_HINT)
                return
        else:
            default_path = shared_path
            if default_path is None:
                default_path = load_fuser_config(config_file)

        fuser_path = default_path or working_fuser_unc()

        for idx in range(1, 4):
            name = f"LocalFuser{idx}"
            bat = rf'C:\\Program Files\\Skyline\\PhotoMesh\\Fuser\\{name}.bat'
            if os.path.isfile(bat):
                cmd = f'start "" "{bat}"'
            else:
                cmd = f'start "" "{fuser_exe}" "{name}" "{fuser_path}" 0 true'

            try:
                subprocess.run(cmd, shell=True, check=True)
                self.log_message(f"Launched {name}.")
            except subprocess.CalledProcessError as e:
                self.log_message(f"Failed to start {name}: {e}")

    def create_mesh(self):
        if not hasattr(self, 'image_folder_paths') or not self.image_folder_paths:
            self.select_imagery()
            if not hasattr(self, 'image_folder_paths') or not self.image_folder_paths:
                return

        project_name = prompt_project_name(self)
        if not project_name:
            messagebox.showwarning("Missing Name", "Project name is required.", parent=self)
            return

        projects_root = get_projects_root()
        project_path = ""
        if projects_root and os.path.isdir(projects_root) and os.access(projects_root, os.W_OK):
            project_path = projects_root
            if hasattr(self, "log_message"):
                self.log_message(f"Using saved Projects root: {project_path}")
        else:
            if projects_root and hasattr(self, "log_message"):
                if not os.path.isdir(projects_root):
                    self.log_message(f"Saved Projects root missing: {projects_root}")
                elif not os.access(projects_root, os.W_OK):
                    self.log_message(f"Saved Projects root not writable: {projects_root}")
            project_path = filedialog.askdirectory(
                title="Select Project Output Folder (root, will be saved)",
                parent=self,
            )
            if not project_path:
                messagebox.showwarning("Missing Folder", "Project output folder is required.", parent=self)
                return
            set_projects_root(project_path)
            if hasattr(self, "log_message"):
                self.log_message(f"Saved Projects root: {project_path}")

        project_path = os.path.normpath(project_path)
        project_dir = clean_path(os.path.join(project_path, project_name))
        os.makedirs(project_dir, exist_ok=True)

        self.log_message(f"Creating mesh for project: {project_name}")

        try:
            pmpreset_path = _resource_path("STEPRESET.PMPreset")
            try:
                install_pmpreset(pmpreset_path, name="STEPRESET", log=self.log_message)
            except FileNotFoundError:
                self.log_message("[Preset] STEPRESET.PMPreset not bundled; launching with defaults.")
            proc = launch_wizard_new_project(
                project_name=project_name,
                project_path=project_dir,
                folders=self.image_folder_paths,
                log=self.log_message,
            )
            if hasattr(self, "detach_wizard_on_photomesh_start_by_pid") and proc:
                self.detach_wizard_on_photomesh_start_by_pid(proc.pid, project_dir)
            self.log_message(
                "PhotoMesh Wizard launched with preset STEPRESET and --overrideSettings."
            )
            self.start_progress_monitor(project_dir)
        except Exception as e:
            error_message = f"Failed to start PhotoMesh Wizard.\nError: {str(e)}"
            self.log_message(error_message)
            messagebox.showerror("Launch Error", error_message, parent=self)
            if messagebox.askyesno(
                "Open Folder", "Would you like to open the project folder?", parent=self
            ):
                open_in_explorer(project_dir)

    def view_mesh(self):
        terra_explorer_path = r"C:\Program Files\Skyline\TerraExplorer Pro\TerraExplorer.exe"
        self.log_message("Launching TerraExplorer...")

        def start_explorer(path):
            try:
                subprocess.Popen([path])
                messagebox.showinfo("View Mesh", "TerraExplorer launched.", parent=self)
            except Exception as e:
                messagebox.showerror("Error", f"Could not launch TerraExplorer:\n{e}", parent=self)

        if os.path.exists(terra_explorer_path):
            start_explorer(terra_explorer_path)
        else:
            def _search_and_launch():
                found_path = find_terra_explorer()
                if found_path:
                    post_ui(start_explorer, found_path)
                else:
                    post_ui(
                        lambda: messagebox.showwarning(
                            "TerraExplorer Not Found",
                            "TerraExplorer is not installed or could not be found.",
                            parent=self,
                        )
                    )

            run_in_thread(_search_and_launch)

    def one_click_conversion(self):
        """Run the entire mesh build and post-process pipeline."""
        self.log_message("Starting One-Click Terrain Conversion...")

        self.log_message("Prompting user to select imagery folders...")
        self.select_imagery()

        if not getattr(self, 'image_folder_paths', None):
            self.log_message("Imagery folder selection failed or cancelled.")
            return

        self.log_message("Launching PhotoMesh Wizard...")
        self.create_mesh()

        if not getattr(self, 'last_build_dir', None):
            self.log_message("Mesh creation did not start properly.")
            messagebox.showerror(
                "Error", "Unable to determine build directory.", parent=self
            )
            return

        def _pipeline():
            # Wait until PhotoMesh has actually exported OBJ tiles before launching RM.
            build_root = self.last_build_dir  
            self.log_message(
                "Waiting for PhotoMesh build to complete (watching for OBJ output)…"
            )
            obj_dir = wait_for_obj(build_root, log=self.log_message)
            if obj_dir:
                self.log_message(
                    f"PhotoMesh build complete (OBJ found at: {obj_dir}). Launching Reality Mesh…"
                )
                # Kick off post-processing / launch RM now that OBJ is present
                self.post_process_last_build(build_root)
            else:
                self.log_message(
                    "Timeout or failure while waiting for OBJ. Reality Mesh will NOT be launched."
                )
        run_in_thread(_pipeline)

    def post_process_last_build(self, build_root: str | None = None) -> None:
        """Launch the external Reality Mesh to VBS4 application."""
        sys_settings_path = os.path.join(BASE_DIR, 'photomesh', 'RealityMeshSystemSettings.txt')
        if build_root:
            self.last_build_dir = build_root
        
    def launch_reality_mesh_to_vbs4(self):
        local_root = get_rm_local_root().strip()
        attempted: list[str] = []
        local = ''
        if local_root:
            if not is_valid_rm_local_root(local_root):
                messagebox.showerror(
                    "Reality Mesh",
                    (
                        f"Reality Mesh install folder '{local_root}' is invalid.\n\n"
                        f"Expected to find '{RM_LNK_NAME}' somewhere under this folder.\n"
                        "Example: D:\\RealityMeshInstall\\Reality Mesh to VBS4.lnk"
                    ),
                )
                self.controller.show('Settings')
                return
            attempted = [
                os.path.normpath(os.path.join(local_root, sub, RM_LNK_NAME))
                for sub in RM_INSTALL_SUBDIRS
            ]
            local = find_local_rm_shortcut(local_root)

        if local:
            self.log_message(f"Launching Reality Mesh via LOCAL: {local}")
            try:
                os.startfile(local)
            except Exception as e:
                messagebox.showerror("Reality Mesh", f"Failed to launch:\n{e}")
            return

        tpl = get_rm_template_from_config()
        link = resolve_unc(tpl)
        if not os.path.isfile(link):
            diag = _diagnose_missing_unc(link)
            listing = ''
            install_dir = ''
            if local_root:
                install_dir = os.path.join(local_root, 'RealityMeshInstall')
                if os.path.isdir(install_dir):
                    listing = _list_dir_safe(install_dir)
            msg_parts = ["Could not locate 'Reality Mesh to VBS4.lnk'."]
            if attempted:
                msg_parts.append("\nLocal attempts:")
                msg_parts.extend(attempted)
            if local_root:
                msg_parts.append(
                    f"\nLocal install folder: {os.path.normpath(local_root)}"
                )
            msg_parts.append(f"\nUNC path: {link}")
            if diag:
                msg_parts.append(f"\n{diag}")
            if listing:
                msg_parts.append(
                    f"\nContents of {os.path.normpath(install_dir)}:\n{listing}"
                )
            messagebox.showerror("Reality Mesh", "\n".join(msg_parts))
            self._update_rm_status()
            return

        self.log_message(f"Launching Reality Mesh via UNC: {link}")
        try:
            os.startfile(link)
        except Exception as e:
            messagebox.showerror("Reality Mesh", f"Failed to launch:\n{e}")
        finally:
            self._update_rm_status()
    def _update_rm_status(self):
        if not hasattr(self, "rm_path_label"):
            return
        link, source = resolve_active_rm_link()
        prev = getattr(self, 'rm_source', None)
        if source != prev and source in ('LOCAL', 'UNC'):
            self.log_message(f"Reality Mesh link source: {source}")
        self.rm_source = source
        if source == 'INVALID_LOCAL_ROOT':
            self.rm_path_label.config(
                text="⚠ Reality Mesh install folder invalid or missing Reality Mesh to VBS4.lnk.",
                fg="#ffb3b3",
            )
            return
        if link:
            self.rm_path_label.config(
                text=f"RM link ({source}): {link}",
                fg="#ddd",
            )
        else:
            self.rm_path_label.config(
                text="⚠ Reality Mesh link not found (LOCAL/UNC). Check Settings.",
                fg="#ffb3b3",
            )
    def show_terrain_tutorial(self):
        messagebox.showinfo("Terrain Tutorial", "coming soon....", parent=self)

    def log_message(self, message):
        post_ui(log_to_console, f"> {message}")

    def clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state="disabled")

    def toggle_log(self):
        if self.log_expanded:
            self.log_text.config(height=3)
            self.toggle_log_button.config(text="Expand Log")
            self.log_expanded = False
        else:
            self.log_text.config(height=15)
            self.toggle_log_button.config(text="Collapse Log")
            self.log_expanded = True

    def set_progress(self, value: int):
        self.progress_var.set(value)
        self.progress_label.config(text=f"{value}%")

    # ------------------------------------------------------------------
    # PhotoMesh progress monitoring
    # ------------------------------------------------------------------

    def start_progress_monitor(self, project_path: str):
        """Begin monitoring PhotoMesh render logs under *project_path*."""
        # Track the project root (the folder that will contain Build_*)
        self.project_root = project_path
        self.last_build_dir = project_path  
        _out = os.path.join(project_path, "Build_1", "out")
        self.project_log_folder = os.path.join(_out, "Log") if os.path.isdir(os.path.join(_out, "Log")) else None
        self.work_folder = os.path.join(_out, "Work") if os.path.isdir(os.path.join(_out, "Work")) else None
        self.progress_var.set(0)
        self.progress_label.config(text="0%")
        if self.progress_job:
            self.after_cancel(self.progress_job)
        self.progress_job = self.after(2000, self.update_render_progress)

    def update_render_progress(self):
        paths = []
        if self.project_log_folder and os.path.isdir(self.project_log_folder):
            paths += glob.glob(os.path.join(self.project_log_folder, "Out*.log"))
            paths += glob.glob(os.path.join(self.project_log_folder, "Run*.log"))
        if self.work_folder and os.path.isdir(self.work_folder):
            paths += glob.glob(os.path.join(self.work_folder, "*.out"))

        latest = max(paths, key=os.path.getmtime) if paths else None
        percent = None
        if latest:
            try:
                with open(latest, "r", errors="ignore") as f:
                    for line in reversed(f.readlines()):
                        percent = extract_progress(line)
                        if percent is not None:
                            break
            except Exception:
                pass

        if percent is not None:
            self.progress_var.set(percent)
            self.progress_label.config(text=f"{percent}%")
            if percent >= 100:
                self.progress_job = None
                return

        self.progress_job = self.after(2000, self.update_render_progress)

class OneClickPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        set_background(controller, self)
        controller.create_tutorial_button(self)
        self.configure(bg="black")

        parent_bg = self.cget("bg")

        # --- Main actions ----------------------------------------------------
        self.oneclick_button = self.make_button(
            "Run One-Click Conversion", self.on_run_oneclick
        )
        self.oneclick_button.pack(pady=15)

        self.rm_button = self.make_button(
            "Launch Reality Mesh to VBS4", self.launch_reality_mesh_to_vbs4
        )
        self.rm_button.pack(pady=15)

        self.relaunch_fusers_button = self.make_button(
            "Relaunch Fusers", self.relaunch_fusers
        )
        self.relaunch_fusers_button.pack(pady=15)

        self.tutorial_button = self.make_button(
            "One-Click Terrain Tutorial", self.show_terrain_tutorial
        )
        self.tutorial_button.pack(pady=15)

        self.back_button = self.make_button(
            "Back", lambda: controller.show("Main")
        )
        self.back_button.pack(pady=(15, 0))

        # --- Status line (RM link source/path) -------------------------------
        status_frame = tk.Frame(self, bg=parent_bg, bd=0, highlightthickness=0)
        status_frame.pack(fill="x", padx=20, pady=(10, 0))
        self.rm_path_label = tk.Label(
            status_frame,
            text="",
            font=("Helvetica", 12),
            bg=parent_bg,
            fg="white",
            justify="left",
            wraplength=900,
        )
        self.rm_path_label.pack(anchor="w")

        # --- Log area --------------------------------------------------------
        self.log_frame = tk.Frame(self, bg=self.cget("bg"), bd=0, highlightthickness=0)
        self.log_frame.pack(side="bottom", fill="x", padx=10, pady=(5, 0))

        tk.Label(
            self.log_frame,
            text="Activity Log",
            font=("Helvetica", 16, "bold"),
            bg=self.log_frame.cget("bg"),
            fg="white",
            bd=0,
            highlightthickness=0,
        ).pack(anchor="w")

        self.log_text = tk.Text(
            self.log_frame,
            height=3,
            bg=self.log_frame.cget("bg"),
            fg="white",
            wrap="word",
            bd=0,
            highlightthickness=0,
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.config(state="disabled")
        self.log_expanded = False
        ui_log_schedule_flush(controller, self.log_text)

        # --- Progress bar ----------------------------------------------------
        progress_frame = tk.Frame(
            self.log_frame, bg=self.log_frame.cget("bg"), bd=0, highlightthickness=0
        )
        progress_frame.pack(fill="x", pady=(5, 0))

        self.progress_var = tk.IntVar(value=0)
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Green.Horizontal.TProgressbar",
            troughcolor=self.log_frame.cget("bg"),
            background="#00aa00",
        )
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            orient="horizontal",
            mode="determinate",
            style="Green.Horizontal.TProgressbar",
        )
        self.progress_bar.pack(side="left", fill="x", expand=True)

        self.progress_label = tk.Label(
            progress_frame,
            text="0%",
            font=("Helvetica", 12),
            bg=progress_frame.cget("bg"),
            fg="white",
            width=5,
            bd=0,
            highlightthickness=0,
        )
        self.progress_label.pack(side="right", padx=(5, 0))

        # --- Log controls ----------------------------------------------------
        button_frame = tk.Frame(
            self.log_frame, bg=self.log_frame.cget("bg"), bd=0, highlightthickness=0
        )
        button_frame.pack(fill="x", pady=5)

        self.toggle_log_button = tk.Button(
            button_frame,
            text="Expand Log",
            command=self.toggle_log,
            bg="#555",
            fg="white",
            bd=0,
            highlightthickness=0,
        )
        self.toggle_log_button.pack(side="left")

        tk.Button(
            button_frame,
            text="Clear Log",
            command=self.clear_log,
            bg="#555",
            fg="white",
            bd=0,
            highlightthickness=0,
        ).pack(side="right")

        # --- State -----------------------------------------------------------
        self.progress_job = None
        self.project_log_folder = None
        self.work_folder = None
        self.last_build_dir = None
        self.image_folder_paths = []
        self.rm_source = None
        self.update_fuser_state()
        self.refresh_rm_status()

    def make_button(self, text, command):
        """Return a main-action button styled like the other panels."""
        return tk.Button(
            self,
            text=text,
            font=("Helvetica", 24),
            bg="#444444",
            fg="white",
            activebackground="#666666",
            activeforeground="white",
            width=30,
            height=1,
            command=command,
            bd=0,
            highlightthickness=0,
            relief="flat",
            overrelief="flat",
            takefocus=False,
        )

        self.progress_job = None
        self.project_log_folder = None
        self.work_folder = None
        self.last_build_dir = None
        self.image_folder_paths: list[str] = []
        self.rm_source: str | None = None

        self.update_fuser_state()
        self.refresh_rm_status()

    def refresh_rm_status(self):
        self.after(0, self._update_rm_status)

    def update_fuser_state(self):
        is_fuser = config["Fusers"].getboolean("fuser_computer", fallback=False)
        host_ct, desired_ct = get_fuser_counts()
        is_host = is_host_machine()
        disable = is_fuser and not is_host and desired_ct > 1

        for btn in (self.oneclick_button, self.rm_button):
            btn.config(state="disabled" if disable else "normal")
            btn.config(bg="#888888" if disable else "#444444")

        if disable:
            tip = (
                "This PC is configured to run multiple fusers. "
                "Reduce Fusers/desired_count to 1 or 0 to enable One-Click."
            )
            self.log_message(tip)
        enforce_local_fuser_policy()

    def relaunch_fusers(self):
        try:
            self.log_message("Relaunching fusers …")
            relaunch = globals().get("relaunch_fusers")
            if callable(relaunch):
                relaunch()
            running = count_local_fusers()
            self.log_message(f"Fusers relaunched. Running: {running}")
        except Exception as e:
            self.log_message(f"Failed to relaunch fusers: {e}")

    def log_message(self, message):
        post_ui(log_to_console, f"> {message}")

    def clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state="disabled")

    def toggle_log(self):
        if self.log_expanded:
            self.log_text.config(height=3)
            self.toggle_log_button.config(text="Expand Log")
            self.log_expanded = False
        else:
            self.log_text.config(height=15)
            self.toggle_log_button.config(text="Collapse Log")
            self.log_expanded = True

    def set_progress(self, value: int):
        self.progress_var.set(value)
        self.progress_label.config(text=f"{value}%")

    def start_progress_monitor(self, project_path: str):
        self.project_root = project_path
        self.last_build_dir = project_path

        _out = os.path.join(project_path, "Build_1", "out")
        log_dir = os.path.join(_out, "Log")
        work_dir = os.path.join(_out, "Work")
        self.project_log_folder = log_dir if os.path.isdir(log_dir) else None
        self.work_folder = work_dir if os.path.isdir(work_dir) else None

        self.progress_var.set(0)
        self.progress_label.config(text="0%")
        if self.progress_job:
            self.after_cancel(self.progress_job)
        self.progress_job = self.after(2000, self.update_render_progress)

    def update_render_progress(self):
        paths: list[str] = []
        if self.project_log_folder and os.path.isdir(self.project_log_folder):
            paths += glob.glob(os.path.join(self.project_log_folder, "Out*.log"))
            paths += glob.glob(os.path.join(self.project_log_folder, "Run*.log"))
        if self.work_folder and os.path.isdir(self.work_folder):
            paths += glob.glob(os.path.join(self.work_folder, "*.out"))

        latest = max(paths, key=os.path.getmtime) if paths else None
        percent = None
        if latest:
            try:
                with open(latest, "r", errors="ignore") as f:
                    for line in reversed(f.readlines()):
                        percent = extract_progress(line)
                        if percent is not None:
                            break
            except Exception:
                pass

        if percent is not None:
            self.progress_var.set(percent)
            self.progress_label.config(text=f"{percent}%")
            if percent >= 100:
                self.progress_job = None
                return

        self.progress_job = self.after(2000, self.update_render_progress)

    def select_imagery(self):
        folders: list[str] = []

        folder_window = tk.Toplevel(self)
        apply_app_icon(folder_window)
        folder_window.title("Select Imagery Folders")
        folder_window.geometry("700x500")
        folder_window.resizable(False, False)
        folder_window.transient(self)
        folder_window.grab_set()
        folder_window.attributes("-topmost", True)
        folder_window.configure(bg=self.cget("bg"))

        if os.path.exists(prompt_box_image_path):
            img = Image.open(prompt_box_image_path).resize(
                (801, 506), Image.Resampling.LANCZOS
            )
            ph = ImageTk.PhotoImage(img)
            bg_label = tk.Label(folder_window, image=ph, borderwidth=0)
            bg_label.image = ph
            bg_label.place(relwidth=1, relheight=1)

        tk.Label(
            folder_window,
            text="Selected Imagery Folders:",
            font=("Helvetica", 14, "bold"),
            bg=folder_window.cget("bg"),
            fg="white",
            bd=0,
            highlightthickness=0,
        ).pack(pady=(20, 5))

        folder_listbox = tk.Listbox(
            folder_window,
            width=80,
            height=10,
            bg="#1e1e1e",
            fg="white",
            selectbackground="#444",
            bd=0,
            highlightthickness=0,
        )
        folder_listbox.pack(pady=10)

        def refresh_listbox():
            folder_listbox.delete(0, tk.END)
            for folder in folders:
                folder_listbox.insert(tk.END, folder)

        def add_folder():
            selected = filedialog.askdirectory(
                title="Select DCIM or base imagery folder",
                parent=folder_window,
            )
            if selected:
                found = get_image_folders_recursively(clean_path(selected))
                folders.extend(found)
                refresh_listbox()
                return

            input_path = simpledialog.askstring(
                "Network Path",
                "Enter network folder path:",
                parent=folder_window,
            )
            if not input_path:
                return
            path = clean_path(input_path)
            if os.path.isdir(path):
                selected = filedialog.askdirectory(
                    title="Select DCIM or base imagery folder",
                    initialdir=path,
                    parent=folder_window,
                )
                if selected:
                    found = get_image_folders_recursively(clean_path(selected))
                    folders.extend(found)
            else:
                messagebox.showerror(
                    "Invalid Path",
                    f"The path '{input_path}' does not exist.",
                    parent=folder_window,
                )
            refresh_listbox()

        def remove_folder():
            selected_indices = folder_listbox.curselection()
            for index in reversed(selected_indices):
                del folders[index]
            refresh_listbox()

        def finish_selection():
            if not folders:
                messagebox.showwarning(
                    "No Selection", "No folder selected.", parent=folder_window
                )
                return

            norm_folders = [clean_path(f) for f in folders]
            self.image_folder_paths = norm_folders
            self.image_folder_path = ';'.join(norm_folders)
            if SHOW_SELECTION_TOAST:
                messagebox.showinfo(
                    "Imagery Selected",
                    f"Selected imagery folders:\n{', '.join(self.image_folder_paths)}",
                    parent=folder_window,
                )
            else:
                self.log_message(
                    f"Imagery selected: {', '.join(self.image_folder_paths)}"
                )
            folder_window.destroy()

        def cancel_selection():
            folder_window.destroy()

        button_bar = tk.Frame(folder_window, bg=folder_window.cget("bg"))
        button_bar.pack(pady=20)

        def styled_btn(label, command):
            return tk.Button(
                button_bar,
                text=label,
                command=command,
                font=("Helvetica", 14, "bold"),
                bg="#444",
                fg="white",
                activebackground="#666",
                width=18,
                height=2,
                bd=0,
            )

        styled_btn("➕ Add Folder", add_folder).pack(side=tk.LEFT, padx=10)
        styled_btn("❌ Remove Selected", remove_folder).pack(side=tk.LEFT, padx=10)
        styled_btn("✅ Finish", finish_selection).pack(side=tk.LEFT, padx=10)
        styled_btn("Cancel", cancel_selection).pack(side=tk.LEFT, padx=10)

        folder_window.wait_window()

    def create_mesh(self):
        if not self.image_folder_paths:
            self.select_imagery()
            if not self.image_folder_paths:
                return

        project_name = prompt_project_name(self)
        if not project_name:
            messagebox.showwarning("Missing Name", "Project name is required.", parent=self)
            return

        projects_root = get_projects_root()
        project_path = ""
        if projects_root and os.path.isdir(projects_root) and os.access(projects_root, os.W_OK):
            project_path = projects_root
            self.log_message(f"Using saved Projects root: {project_path}")
        else:
            if projects_root:
                if not os.path.isdir(projects_root):
                    self.log_message(f"Saved Projects root missing: {projects_root}")
                elif not os.access(projects_root, os.W_OK):
                    self.log_message(f"Saved Projects root not writable: {projects_root}")
            project_path = filedialog.askdirectory(
                title="Select Project Output Folder (root, will be saved)",
                parent=self,
            )
            if not project_path:
                messagebox.showwarning("Missing Folder", "Project output folder is required.", parent=self)
                return
            set_projects_root(project_path)
            self.log_message(f"Saved Projects root: {project_path}")

        project_path = os.path.normpath(project_path)
        project_dir = clean_path(os.path.join(project_path, project_name))
        os.makedirs(project_dir, exist_ok=True)

        self.log_message(f"Creating mesh for project: {project_name}")

        try:
            apply_offline_settings()
            enforce_wizard_obj_only_defaults(log=self.log_message)
            update_fuser_shared_path()
            pmpreset_path = _resource_path("STEPRESET.PMPreset")
            try:
                install_pmpreset(pmpreset_path, name="STEPRESET", log=self.log_message)
            except FileNotFoundError:
                self.log_message("[Preset] STEPRESET.PMPreset not bundled; launching with defaults.")
            proc = launch_wizard_new_project(
                project_name=project_name,
                project_path=project_dir,
                folders=self.image_folder_paths,
                log=self.log_message,
            )
            if hasattr(self, "detach_wizard_on_photomesh_start_by_pid") and proc:
                self.detach_wizard_on_photomesh_start_by_pid(proc.pid, project_dir)
            self.log_message(
                "PhotoMesh Wizard launched with preset STEPRESET and --overrideSettings."
            )
            self.start_progress_monitor(project_dir)
        except Exception as e:
            error_message = f"Failed to start PhotoMesh Wizard.\nError: {str(e)}"
            self.log_message(error_message)
            messagebox.showerror("Launch Error", error_message, parent=self)
            if messagebox.askyesno(
                "Open Folder", "Would you like to open the project folder?", parent=self
            ):
                open_in_explorer(project_dir)

    def one_click_conversion(self):
        self.log_message("Starting One-Click Terrain Conversion...")
        self.log_message("Prompting user to select imagery folders...")
        self.select_imagery()

        if not self.image_folder_paths:
            self.log_message("Imagery folder selection failed or cancelled.")
            return

        self.log_message("Launching PhotoMesh Wizard...")
        self.create_mesh()

        if not getattr(self, "last_build_dir", None):
            self.log_message("Mesh creation did not start properly.")
            messagebox.showerror("Error", "Unable to determine build directory.", parent=self)
            return

        def _pipeline():
            # Wait until PhotoMesh has actually exported OBJ tiles before launching RM.
            build_root = self.last_build_dir  
            self.log_message(
                "Waiting for PhotoMesh build to complete (watching for OBJ output)…"
            )
            obj_dir = wait_for_obj(build_root, log=self.log_message)
            if obj_dir:
                self.log_message(
                    f"PhotoMesh build complete (OBJ found at: {obj_dir}). Launching Reality Mesh…"
                )
                # Kick off post-processing / launch RM now that OBJ is present
                self.post_process_last_build(build_root)
            else:
                self.log_message(
                    "Timeout or failure while waiting for OBJ. Reality Mesh will NOT be launched."
                )

        run_in_thread(_pipeline)

    def on_run_oneclick(self):
        enforce_local_fuser_policy()
        self.one_click_conversion()

    def post_process_last_build(self, build_root: str | None = None) -> None:
        sys_settings_path = os.path.join(BASE_DIR, 'photomesh', 'RealityMeshSystemSettings.txt')
        if build_root:
            self.last_build_dir = build_root
        if os.path.isfile(sys_settings_path):
            try:
                shutil.copy2(sys_settings_path, os.path.join(BASE_DIR, 'RealityMeshSystemSettings.txt'))
            except Exception:
                pass
        self.launch_reality_mesh_to_vbs4()

    def launch_reality_mesh_to_vbs4(self):
        local_root = get_rm_local_root().strip()
        attempted: list[str] = []
        local = ''
        if local_root:
            if not is_valid_rm_local_root(local_root):
                messagebox.showerror(
                    "Reality Mesh",
                    (
                        f"Reality Mesh install folder '{local_root}' is invalid.\n\n"
                        f"Expected to find '{RM_LNK_NAME}' somewhere under this folder.\n"
                        "Example: D:\\RealityMeshInstall\\Reality Mesh to VBS4.lnk"
                    ),
                )
                self.controller.show('Settings')
                return
            attempted = [
                os.path.normpath(os.path.join(local_root, sub, RM_LNK_NAME))
                for sub in RM_INSTALL_SUBDIRS
            ]
            local = find_local_rm_shortcut(local_root)

        if local:
            self.log_message(f"Launching Reality Mesh via LOCAL: {local}")
            try:
                os.startfile(local)
            except Exception as e:
                messagebox.showerror("Reality Mesh", f"Failed to launch:\n{e}")
            return

        tpl = get_rm_template_from_config()
        link = resolve_unc(tpl)
        if not os.path.isfile(link):
            diag = _diagnose_missing_unc(link)
            listing = ''
            install_dir = ''
            if local_root:
                install_dir = os.path.join(local_root, 'RealityMeshInstall')
                if os.path.isdir(install_dir):
                    listing = _list_dir_safe(install_dir)
            msg_parts = ["Could not locate 'Reality Mesh to VBS4.lnk'."]
            if attempted:
                msg_parts.append("\nLocal attempts:")
                msg_parts.extend(attempted)
            if local_root:
                msg_parts.append(
                    f"\nLocal install folder: {os.path.normpath(local_root)}"
                )
            msg_parts.append(f"\nUNC path: {link}")
            if diag:
                msg_parts.append(f"\n{diag}")
            if listing:
                msg_parts.append(
                    f"\nContents of {os.path.normpath(install_dir)}:\n{listing}"
                )
            messagebox.showerror("Reality Mesh", "\n".join(msg_parts))
            self.refresh_rm_status()
            return

        self.log_message(f"Launching Reality Mesh via UNC: {link}")
        try:
            os.startfile(link)
        except Exception as e:
            messagebox.showerror("Reality Mesh", f"Failed to launch:\n{e}")
        finally:
            self.refresh_rm_status()

    def _update_rm_status(self):
        if not hasattr(self, "rm_path_label"):
            return
        link, source = resolve_active_rm_link()
        prev = getattr(self, 'rm_source', None)
        if source != prev and source in ('LOCAL', 'UNC'):
            self.log_message(f"Reality Mesh link source: {source}")
        self.rm_source = source
        if source == 'INVALID_LOCAL_ROOT':
            self.rm_path_label.config(
                text="⚠ Reality Mesh install folder invalid or missing Reality Mesh to VBS4.lnk.",
                fg="#ffb3b3",
            )
            return
        if link:
            self.rm_path_label.config(
                text=f"RM link ({source}): {link}",
                fg="#ddd",
            )
        else:
            self.rm_path_label.config(
                text="⚠ Reality Mesh link not found (LOCAL/UNC). Check Settings.",
                fg="#ffb3b3",
            )

    def show_terrain_tutorial(self):
        messagebox.showinfo("Terrain Tutorial", "coming soon....", parent=self)

class BVIPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        # Keep the background call but we'll make sure it's properly aligned
        set_background(controller, self)
        controller.create_tutorial_button(self)
        self.configure(bg="black")

        # --- Main actions ----------------------------------------------------
        self.bvi_button = self.make_button(
            "Launch BVI", launch_bvi
        )
        self.bvi_button.pack(pady=15)

        self.version_label = tk.Label(
            self,
            text=f"Version: {get_bvi_version(get_ares_manager_path())}",
            font=("Helvetica", 16),
            bg="black",
            fg="white",
            bd=0,
            highlightthickness=0,
        )
        self.version_label.pack(pady=(0, 15))

        self.open_terrain_button = self.make_button(
            "Open Terrain", open_bvi_terrain
        )
        self.open_terrain_button.pack(pady=15)

        self.back_button = self.make_button(
            "Back", lambda: controller.show("Main")
        )
        self.back_button.pack(pady=(15, 0))

        self.update_bvi_version()

    def make_button(self, text, command):
        return tk.Button(
            self,
            text=text,
            font=("Helvetica", 24),
            bg="#444444",
            fg="white",
            activebackground="#666666",
            activeforeground="white",
            width=30,
            height=1,
            command=command,
            bd=0,
            highlightthickness=0,
            relief="flat",
            overrelief="flat",
            takefocus=False,
        )

    def update_bvi_version(self):
        bvi_path = get_ares_manager_path()
        version = get_bvi_version(bvi_path)
        self.version_label.config(text=f"Version: {version}")

# ─── SETTINGS PANEL ──────────────────────────────────────────────────────────
class SettingsPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.configure(bg="black")  # header removed; fixed header used
        self.grid_rowconfigure(7, weight=1, minsize=400)
        self.grid_columnconfigure(0, weight=1)

        # --- Top toggles -------------------------------------------------
        toggles = tk.LabelFrame(self, text="", bg="black", fg="white", bd=0, highlightthickness=0)
        toggles.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        toggles.grid_columnconfigure(0, weight=1)
        toggles.grid_columnconfigure(1, weight=1)

        self.fullscreen_var = tk.BooleanVar(value=controller.fullscreen)
        self.startup_var = tk.BooleanVar(value=is_startup_enabled())
        self.close_on_launch_var = tk.BooleanVar(value=is_close_on_launch_enabled())
        self.fuser_var = tk.BooleanVar(
            value=config["Fusers"].getboolean("fuser_computer", False)
        )

        def _on_fuser_toggle():
            config["Fusers"]["fuser_computer"] = str(self.fuser_var.get())
            with open(CONFIG_PATH, "w") as f:
                config.write(f)

            if self.fuser_var.get():
                # Ensure Fusers host matches the single Host PC Name
                ip = get_host_ip()
                if not ip:
                    ip = get_primary_ipv4()
                    if ip:
                        self.host_ip_var.set(ip)
                        try:
                            set_host_ip(ip)
                        except Exception:
                            pass
                else:
                    try:
                        set_host_ip(ip)
                    except Exception:
                        pass

                config["Fusers"]["working_folder_host"] = ip or get_host().strip()
                n = simpledialog.askinteger(
                    "Local Fusers",
                    "How many local fusers should this computer run? (1–3)",
                    minvalue=1,
                    maxvalue=3,
                    parent=self,
                )
                if n is None:
                    try:
                        n = int(config["Fusers"].get("desired_count", "3") or 3)
                    except Exception:
                        n = 3
                n = _clamp_fusers(n, True)
                config["Fusers"]["desired_count"] = str(n)
            else:
                # When turning off leave desired_count unchanged; policy will stop local fusers.
                pass

            with open(CONFIG_PATH, "w") as f:
                config.write(f)

            update_fuser_shared_path()
            enforce_local_fuser_policy()
            self._refresh_fuser_counter_row()
            if "OneClick" in self.controller.panels:
                oc_panel = self.controller.panels["OneClick"]
                oc_panel.update_fuser_state()
                oc_panel.refresh_rm_status()

        toggle_specs = [
            ("Fullscreen Mode", self.fullscreen_var, self._on_fullscreen_toggle),
            ("Launch on Startup", self.startup_var, self._on_launch_on_startup),
            (
                "Close on Software Launch?",
                self.close_on_launch_var,
                self._on_close_on_launch,
            ),
            ("Fuser Computer", self.fuser_var, _on_fuser_toggle),
        ]

        for i, (text, var, cmd) in enumerate(toggle_specs):
            r, c = divmod(i, 2)
            chk = tk.Checkbutton(
                toggles,
                text=text,
                variable=var,
                command=cmd,
                font=("Helvetica", 20),
                bg="#444444",
                fg="white",
                selectcolor="#444444",
                indicatoron=True,
                width=30,
                pady=5,
                bd=0,
                highlightthickness=0,
            )
            chk.grid(row=r, column=c, padx=6, pady=6, sticky="ew")

        # --- Local fuser controls -----------------------------------------
        frow = tk.Frame(self, bg="black")
        frow.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))

        self.fuser_count_label = tk.Label(
            frow,
            text="Local fusers: 0 running / 0 desired",
            font=("Helvetica", 14),
            bg="black",
            fg="white",
        )
        self.fuser_count_label.pack(side="left")

        def _bump(delta: int):
            is_fuser = config["Fusers"].getboolean("fuser_computer", fallback=False)
            try:
                current = int(config["Fusers"].get("desired_count", "3") or 3)
            except Exception:
                current = 3
            newv = _clamp_fusers(current + delta, is_fuser)
            config["Fusers"]["desired_count"] = str(newv)
            with open(CONFIG_PATH, "w") as f:
                config.write(f)
            ensure_fuser_instances(newv)
            self._refresh_fuser_counter_row()

        tk.Button(
            frow,
            text="–",
            bg="#444",
            fg="white",
            command=lambda: _bump(-1),
            bd=0,
            width=3,
        ).pack(side="left", padx=8)

        tk.Button(
            frow,
            text="+",
            bg="#444",
            fg="white",
            command=lambda: _bump(1),
            bd=0,
            width=3,
        ).pack(side="left")

        self._refresh_fuser_counter_row()

        # --- Network Host -----------------------------------------------
        net_frame = tk.Frame(self, bg="black")
        net_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 6))
        net_frame.grid_columnconfigure(1, weight=1)

        tk.Label(
            net_frame,
            text="Host IP",
            font=("Helvetica", 14),
            bg="black",
            fg="white",
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        host_row = tk.Frame(net_frame, bg="black")
        host_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 10))

        self.host_ip_var = tk.StringVar(
            value=config.get("Offline", "host_ip", fallback="")
        )

        tk.Entry(
            host_row,
            textvariable=self.host_ip_var,
            font=("Consolas", 12),
            bg="#111111",
            fg="white",
            insertbackground="white",
            bd=0,
        ).pack(side="left", fill="x", expand=True)

        def _use_my_ip():
            ip = get_primary_ipv4()
            if ip:
                self.host_ip_var.set(ip)

        tk.Button(
            host_row,
            text="Use my IP",
            command=_use_my_ip,
            font=("Helvetica", 12),
            bg="#444444",
            fg="white",
            bd=0,
        ).pack(side="left", padx=8)

        tk.Button(
            host_row,
            text="Save",
            command=self._save_host_ip,
            font=("Helvetica", 12),
            bg="#444444",
            fg="white",
            bd=0,
        ).pack(side="left", padx=8)

        # Provide a “Share Now” action to (re)publish the folder silently
        def _share_now():
            # Canonical share creator from photomesh_launcher.py
            ensure_offline_share_exists(log=self.controller.log)
            o = get_offline_cfg()
            root = o.get("local_data_root") or ""
            messagebox.showinfo(
                "Share",
                f"Shared (or already shared): {root if root else 'No folder configured'}",
            )

        tk.Button(net_frame, text="Share Folder Now", command=_share_now,
                  font=("Helvetica", 12), bg="#444444", fg="white", bd=0) \
            .grid(row=2, column=0, sticky="w", pady=(0, 6))

        # --- Offline / Shared Drive ------------------------------------
        grp = tk.LabelFrame(
            self,
            text="Offline / Shared Drive",
            fg="white",
            bg="black",
            labelanchor="nw",
            padx=10,
            pady=10,
        )
        grp.grid(row=4, column=0, sticky="ew", padx=10, pady=10)

        off = get_offline_cfg()
        self.off_enabled = tk.BooleanVar(value=off["enabled"])
        self.off_share_name = tk.StringVar(value=off["share_name"])
        self.off_local_root = tk.StringVar(value=off["local_data_root"])
        self.off_work_subdir = tk.StringVar(value=off["working_fuser_subdir"])
        self.off_use_ip_unc = tk.BooleanVar(value=off["use_ip_unc"])

        row0 = tk.Frame(grp, bg="black")
        row0.pack(fill="x", pady=4)
        tk.Checkbutton(
            row0,
            text="Enable Offline Mode",
            variable=self.off_enabled,
            bg="black",
            fg="white",
            selectcolor="black",
        ).pack(side="left")
        tk.Checkbutton(
            row0,
            text="Use IP in UNC",
            variable=self.off_use_ip_unc,
            bg="black",
            fg="white",
            selectcolor="black",
        ).pack(side="left", padx=10)

        row2 = tk.Frame(grp, bg="black")
        row2.pack(fill="x", pady=4)
        tk.Label(row2, text="Share Name:", bg="black", fg="white").pack(side="left", padx=(0, 6))
        tk.Entry(row2, textvariable=self.off_share_name, width=24, bg="#111", fg="white", insertbackground="white").pack(side="left")

        row3 = tk.Frame(grp, bg="black")
        row3.pack(fill="x", pady=4)
        tk.Label(row3, text="Local Data Root:", bg="black", fg="white").pack(side="left", padx=(0, 6))
        tk.Entry(row3, textvariable=self.off_local_root, width=50, bg="#111", fg="white", insertbackground="white").pack(side="left", fill="x", expand=True)
        tk.Button(row3, text="Browse...", bg="#444", fg="white", command=self._browse_local_root).pack(side="left", padx=8)

        row4 = tk.Frame(grp, bg="black")
        row4.pack(fill="x", pady=4)
        tk.Label(row4, text="Working Fuser Subdir:", bg="black", fg="white").pack(side="left", padx=(0, 6))
        tk.Entry(row4, textvariable=self.off_work_subdir, width=28, bg="#111", fg="white", insertbackground="white").pack(side="left")

        sd = config["SharedDrive"] if "SharedDrive" in config else {}
        self.shared_mode = tk.StringVar(value=sd.get("preferred_mode", "UNC"))
        self.shared_letter = tk.StringVar(value=sd.get("drive_letter", "M:"))
        self.shared_auto_map = tk.BooleanVar(
            value=str(sd.get("auto_map_on_save", "True")).lower() in ("1", "true", "yes")
        )

        row5 = tk.Frame(grp, bg="black")
        row5.pack(fill="x", pady=4)
        tk.Label(row5, text="Preferred Access:", bg="black", fg="white").pack(side="left", padx=(0, 6))
        tk.Radiobutton(
            row5,
            text="UNC",
            variable=self.shared_mode,
            value="UNC",
            bg="black",
            fg="white",
            selectcolor="black",
        ).pack(side="left")
        tk.Radiobutton(
            row5,
            text="Drive",
            variable=self.shared_mode,
            value="DRIVE",
            bg="black",
            fg="white",
            selectcolor="black",
        ).pack(side="left", padx=10)

        row6 = tk.Frame(grp, bg="black")
        row6.pack(fill="x", pady=4)
        tk.Label(row6, text="Drive Letter:", bg="black", fg="white").pack(side="left", padx=(0, 6))
        tk.Entry(row6, textvariable=self.shared_letter, width=5, bg="#111", fg="white", insertbackground="white").pack(side="left")
        tk.Button(row6, text="Map as Drive", bg="#444", fg="white", command=self._map_drive).pack(side="left", padx=8)
        tk.Button(row6, text="Unmap", bg="#444", fg="white", command=self._unmap_drive).pack(side="left")

        row7 = tk.Frame(grp, bg="black")
        row7.pack(fill="x", pady=4)
        tk.Checkbutton(
            row7,
            text="Auto-map on Save",
            variable=self.shared_auto_map,
            bg="black",
            fg="white",
            selectcolor="black",
        ).pack(side="left")
        tk.Button(row7, text="Auto-Find Share", bg="#444", fg="white", command=self._auto_find_share).pack(side="left", padx=8)

        row8 = tk.Frame(grp, bg="black")
        row8.pack(fill="x", pady=6)
        tk.Button(row8, text="Save", bg="#444", fg="white", command=self._save_offline_settings).pack(side="left")
        tk.Button(row8, text="Test Access", bg="#444", fg="white", command=self._test_offline_access).pack(side="left", padx=8)
        tk.Button(row8, text="Open Working Folder", bg="#444", fg="white", command=self._open_working_folder).pack(side="left")

        # Reality Mesh Install Folder
        rm_row = tk.Frame(self, bg="black")
        rm_row.grid(row=5, column=0, sticky="ew", padx=10, pady=5)
        tk.Label(
            rm_row,
            text="Reality Mesh Install Folder",
            font=("Helvetica", 20),
            bg="black",
            fg="white",
        ).pack(side="left")
        self.rm_local_var = tk.StringVar(value=get_rm_local_root())
        tk.Entry(
            rm_row,
            textvariable=self.rm_local_var,
            width=40,
            bd=0,
            bg="#111111",
            fg="white",
            insertbackground="white",
        ).pack(side="left", fill="x", expand=True)
        tk.Button(
            rm_row,
            text="Browse...",
            command=self._browse_rm_local_root,
            font=("Helvetica", 12),
            bg="#444444",
            fg="white",
            bd=0,
        ).pack(side="left", padx=8)
        tk.Button(
            rm_row,
            text="Save",
            command=self._save_rm_local_root,
            font=("Helvetica", 12),
            bg="#444444",
            fg="white",
            bd=0,
        ).pack(side="left", padx=8)

        # --- Scrollable Application Locations ---------------------------
        locs_box = tk.LabelFrame(
            self,
            text="Application Locations",
            bg="black",
            fg="white",
            font=("Helvetica", 16),
            bd=0,
            highlightthickness=0,
        )
        # Row 6 expands for the scroller; keep Back button at row 7 non‑scrolling
        self.grid_rowconfigure(6, weight=1, minsize=600)
        locs_box.grid(row=6, column=0, sticky="nsew", padx=10, pady=(0, 10))

        # Canvas + vertical scrollbar
        self._settings_canvas = tk.Canvas(
            locs_box, bg="black", highlightthickness=0, bd=0
        )
        self._settings_scrollbar = tk.Scrollbar(locs_box, orient="vertical",
                            command=self._settings_canvas.yview)
        self._settings_canvas.configure(yscrollcommand=self._settings_scrollbar.set)
        
        # Configure pixel-based scrolling to prevent sub-pixel artifacts
        self._settings_canvas.configure(yscrollincrement=1)
        
        self._settings_canvas.pack(side="left", fill="both", expand=True)
        
        # Only show the Settings panel scrollbar when in windowed mode
        if not controller.fullscreen:
            self._settings_scrollbar.pack(side="right", fill="y")

        # Inner frame to hold the path rows
        self._settings_inner = tk.Frame(self._settings_canvas, bg="black")
        win_id = self._settings_canvas.create_window(
            (0, 0), window=self._settings_inner, anchor="nw"
        )
        
        # Wheel event batching for smooth settings scrolling
        self._set_wheel_accum = 0
        self._set_wheel_job = None

        # Keep inner frame width equal to visible canvas width
        def _on_canvas_resize(evt):
            self._settings_canvas.itemconfig(win_id, width=evt.width)
        self._settings_canvas.bind("<Configure>", _on_canvas_resize)

        # Maintain scrollregion with a bit of bottom pad so last row is fully visible
        _SCROLLER_BOTTOM_PAD = 50
        def _update_scrollregion(_evt=None):
            bbox = self._settings_canvas.bbox("all")
            if bbox:
                x0, y0, x1, y1 = bbox
                self._settings_canvas.configure(
                    scrollregion=(x0, y0, x1, y1 + _SCROLLER_BOTTOM_PAD)
                )
        self._settings_inner.bind("<Configure>", _update_scrollregion)

        # Smooth wheel behavior with batching (Windows/macOS: <MouseWheel>, X11: Button-4/5)
        def _on_mousewheel(evt):
            delta = 0
            if hasattr(evt, 'delta') and evt.delta:
                delta = evt.delta
            elif hasattr(evt, 'num'):
                delta = -120 if evt.num == 4 else 120 if evt.num == 5 else 0

            self._set_wheel_accum += delta
            if self._set_wheel_job is not None:
                return "break"

            def _flush():
                steps = int(self._set_wheel_accum / 120)
                if steps:
                    # Pause background resizes in the outer viewport while we scroll the inner canvas
                    try:
                        self.controller._scroll_active = True
                        if self.controller._scroll_timer:
                            self.controller.after_cancel(self.controller._scroll_timer)
                        self.controller._scroll_timer = self.controller.after(100, self.controller._reset_scroll_state)
                    except Exception:
                        pass

                    self._settings_canvas.yview_scroll(-steps, "units")

                self._set_wheel_accum = 0
                self._set_wheel_job = None
                return "break"

            self._set_wheel_job = self.after(8, _flush)
            return "break"

        def _bind_wheel(evt):
            # Bind specifically to the settings canvas and inner frame, not globally
            self._settings_canvas.bind("<MouseWheel>", _on_mousewheel, add=True)
            self._settings_canvas.bind("<Button-4>", _on_mousewheel, add=True)
            self._settings_canvas.bind("<Button-5>", _on_mousewheel, add=True)
            self._settings_inner.bind("<MouseWheel>", _on_mousewheel, add=True)
            self._settings_inner.bind("<Button-4>", _on_mousewheel, add=True)
            self._settings_inner.bind("<Button-5>", _on_mousewheel, add=True)

        def _unbind_wheel(evt):
            # Unbind from settings canvas and inner frame
            try:
                self._settings_canvas.unbind("<MouseWheel>")
                self._settings_canvas.unbind("<Button-4>")
                self._settings_canvas.unbind("<Button-5>")
                self._settings_inner.unbind("<MouseWheel>")
                self._settings_inner.unbind("<Button-4>")
                self._settings_inner.unbind("<Button-5>")
            except Exception:
                pass

        # Bind to both canvas and inner frame for better coverage
        self._settings_canvas.bind("<Enter>", _bind_wheel)
        self._settings_canvas.bind("<Leave>", _unbind_wheel)
        self._settings_inner.bind("<Enter>", _bind_wheel)
        self._settings_inner.bind("<Leave>", _unbind_wheel)

        # ---- Add the existing path rows into `self._settings_inner` exactly as before ----
        self.lbl_projects_root = self._create_path_row(
            "Change Projects Root",
            self._on_change_projects_root,
            get_projects_root(),
            parent=self._settings_inner,
        )
        self.lbl_vbs4 = self._create_path_row(
            "Set VBS4 Install Location",
            self._on_set_vbs4,
            get_vbs4_install_path(),
            parent=self._settings_inner,
        )
        self.lbl_vbs4_setup = self._create_path_row(
            "Set VBS4 Setup Launcher Location",
            self._on_set_vbs4_setup,
            config["General"].get("vbs4_setup_path", ""),
            parent=self._settings_inner,
        )
        self.lbl_blueig = self._create_path_row(
            "Set BlueIG Install Location",
            self._on_set_blueig,
            get_blueig_install_path(),
            parent=self._settings_inner,
        )
        self.lbl_ares = self._create_path_row(
            "Set ARES Manager Location",
            self._on_set_ares,
            get_ares_manager_path(),
            parent=self._settings_inner,
        )
        self.lbl_browser = self._create_path_row(
            "Pick Default Browser",
            self._on_set_browser,
            get_default_browser(),
            parent=self._settings_inner,
        )
        self.lbl_vbs_license = self._create_path_row(
            "Set VBS License Manager Location",
            self._on_set_vbs_license_manager,
            config["General"].get("vbs_license_manager_path", ""),
            parent=self._settings_inner,
        )
        self.lbl_oneclick = self._create_path_row(
            "Set One-Click Output Folder",
            self._on_set_oneclick,
            get_oneclick_output_path(),
            parent=self._settings_inner,
        )

        # Spacer so the last row can scroll above the bottom edge
        tk.Frame(self._settings_inner, height=_SCROLLER_BOTTOM_PAD, bg="black").pack(fill="x")

        # Force update of layout and scroll region to ensure all items are visible
        self._settings_inner.update_idletasks()
        self._settings_canvas.update_idletasks()
        self._settings_canvas.yview_moveto(0)
        
        # Manually update scroll region to ensure all content is accessible
        bbox = self._settings_canvas.bbox("all")
        if bbox:
            x0, y0, x1, y1 = bbox
            self._settings_canvas.configure(scrollregion=(x0, y0, x1, y1 + _SCROLLER_BOTTOM_PAD))

        # Back button and tutorial
        tk.Button(
            self,
            text="Back",
            font=("Helvetica", 24),
            bg="#444444",
            fg="white",
            width=30,
            height=1,
            command=lambda: controller.show("Main"),
            bd=0,
            highlightthickness=0,
        ).grid(row=7, column=0, pady=10)

    def reload_from_config(self):
        """Synchronize all Settings inputs with the persisted configuration."""

        off = get_offline_cfg()
        if hasattr(self, "host_ip_var"):
            self.host_ip_var.set(off["host_ip"])
        self.off_enabled.set(bool(off["enabled"]))
        self.off_share_name.set(off["share_name"])
        self.off_local_root.set(off["local_data_root"])
        self.off_work_subdir.set(off["working_fuser_subdir"])
        self.off_use_ip_unc.set(bool(off["use_ip_unc"]))

        sd = config["SharedDrive"] if "SharedDrive" in config else {}
        preferred = str(sd.get("preferred_mode", "UNC")).upper()
        self.shared_mode.set("DRIVE" if preferred == "DRIVE" else "UNC")
        self.shared_letter.set(sd.get("drive_letter", "M:"))
        auto_map = str(sd.get("auto_map_on_save", "True")).lower() in ("1", "true", "yes", "on")
        self.shared_auto_map.set(auto_map)

        if hasattr(self, "rm_local_var"):
            self.rm_local_var.set(get_rm_local_root())

        # Update common path labels so they reflect any background changes.
        if hasattr(self, "lbl_projects_root"):
            self.lbl_projects_root.config(text=get_projects_root() or "[not set]")
        if hasattr(self, "lbl_vbs4"):
            self.lbl_vbs4.config(text=get_vbs4_install_path() or "[not set]")
        general = config["General"] if "General" in config else {}
        if hasattr(self, "lbl_vbs4_setup"):
            self.lbl_vbs4_setup.config(general.get("vbs4_setup_path", ""))
        if hasattr(self, "lbl_blueig"):
            self.lbl_blueig.config(text=get_blueig_install_path() or "[not set]")
        if hasattr(self, "lbl_ares"):
            self.lbl_ares.config(text=get_ares_manager_path() or "[not set]")
        if hasattr(self, "lbl_browser"):
            self.lbl_browser.config(text=get_default_browser() or "[not set]")
        if hasattr(self, "lbl_vbs_license"):
            self.lbl_vbs_license.config(general.get("vbs_license_manager_path", ""))
        if hasattr(self, "lbl_oneclick"):
            self.lbl_oneclick.config(text=get_oneclick_output_path() or "[not set]")

        self._refresh_fuser_counter_row()

    def _browse_local_root(self):
        p = filedialog.askdirectory(
            title="Select Local Data Root",
            initialdir=self.off_local_root.get() or "C:\\",
        )
        if p:
            self.off_local_root.set(os.path.normpath(p))

    def _save_offline_settings(self):
        old_share = config.get("Offline", "share_name", fallback=self.off_share_name.get()).strip()

        if "Offline" not in config:
            config["Offline"] = {}
        o = config["Offline"]
        o["enabled"] = str(bool(self.off_enabled.get()))
        # Keep host_name in sync with the single top-level host field:
        o["host_name"] = get_host().strip()
        ip = self.host_ip_var.get().strip()
        o["host_ip"] = ip
        o["share_name"] = self.off_share_name.get().strip()
        o["local_data_root"] = os.path.normpath(self.off_local_root.get().strip())
        o["working_fuser_subdir"] = self.off_work_subdir.get().strip()
        if ip:
            o["use_ip_unc"] = "True"
        else:
            o["use_ip_unc"] = o.get("use_ip_unc", "True")
        self.off_use_ip_unc.set(str(o["use_ip_unc"]).lower() in ("1", "true", "yes"))

        sd = config.setdefault("SharedDrive", {})
        sd["preferred_mode"] = self.shared_mode.get()
        sd["drive_letter"] = self.shared_letter.get().strip() or "M:"
        sd["auto_map_on_save"] = str(bool(self.shared_auto_map.get()))

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            config.write(f)

        new_share = o["share_name"]
        if new_share and new_share.lower() != old_share.lower():
            propagate_share_rename_in_config(old_share, new_share)
        working = tk.Toplevel(self)
        working.title("Working…")
        tk.Label(working, text="Working…", padx=20, pady=20).pack()

        def _work():
            try:
                apply_offline_settings()  # sync Wizard, fusers, and ensure share

                if self.shared_auto_map.get():
                    unc_root = build_unc_from_cfg(o)
                    if unc_root and map_drive(unc_root, sd["drive_letter"]):
                        def _apply_map():
                            self.shared_mode.set("DRIVE")
                            sd["preferred_mode"] = "DRIVE"
                            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                                config.write(f)

                        post_ui(_apply_map)

                def _done(msg="Offline/Shared settings saved."):
                    working.destroy()
                    messagebox.showinfo("Settings", msg)

                post_ui(_done)
            except Exception as exc:
                def _err():
                    working.destroy()
                    messagebox.showerror("Settings", str(exc))

                post_ui(_err)

        run_in_thread(_work)

    def _test_offline_access(self):
        path = resolve_shared_access_path()
        if not path:
            messagebox.showinfo(
                "Test Access",
                "Host IP is not configured. Set it above to test the shared folder.",
            )
            return
        working = tk.Toplevel(self)
        working.title("Working…")
        tk.Label(working, text="Working…", padx=20, pady=20).pack()

        def _work():
            ok = can_access_unc(path)

            def _done():
                working.destroy()
                if ok:
                    messagebox.showinfo("Offline Access", f"Access OK:\n{path}\n\nOpening Explorer…")
                    open_in_explorer(path)
                else:
                    messagebox.showerror(
                        "Offline Access",
                        f"Cannot access:\n{path}\n\n",
                        "If this is a local, offline LAN:\n",
                        " • Ensure all PCs are on the same switch\n",
                        " • Static IPs (e.g., 192.168.50.10/24 host)\n",
                        " • Share exists and permissions allow read/write\n",
                        " • Confirm the Host IP above matches the host PC",
                    )

            post_ui(_done)

        run_in_thread(_work)

    def _refresh_fuser_counter_row(self):
        if not hasattr(self, "fuser_count_label"):
            return

        running = count_local_fusers()
        is_fuser = config["Fusers"].getboolean("fuser_computer", fallback=False)
        try:
            desired_raw = int(config["Fusers"].get("desired_count", "3") or 3)
        except Exception:
            desired_raw = 3
        desired = _clamp_fusers(desired_raw, is_fuser)
        suffix = "" if is_fuser else "  (fuser computer is OFF)"
        self.fuser_count_label.config(
            text=f"Local fusers: {running} running / {desired} desired{suffix}"
        )

    def _open_working_folder(self):
        path = resolve_shared_access_path()
        if can_access_unc(path):
            open_in_explorer(path)
        else:
            messagebox.showerror("Open Working Folder", f"Cannot access:\n{path}\nUse Test Access to diagnose.")

    def _auto_find_share(self):
        o = get_offline_cfg()
        host = (o.get("host_ip") or "").strip() or get_host().strip()
        if not host:
            messagebox.showerror("Auto-Find Share", "Host IP or name is not configured.")
            return
        res = probe_best_mesh_share(host)
        if not res:
            messagebox.showerror("Auto-Find Share", f"No share found on {host}")
            return
        share, unc = res
        old = self.off_share_name.get().strip()
        self.off_share_name.set(share)
        if "Offline" not in config:
            config["Offline"] = {}
        config["Offline"]["share_name"] = share
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            config.write(f)
        if share.lower() != old.lower():
            propagate_share_rename_in_config(old, share)
        update_fuser_shared_path()
        logging.info(f"Auto-Find Share -> {unc}")
        messagebox.showinfo("Auto-Find Share", f"Using share:\n{unc}")

    def _map_drive(self):
        o = get_offline_cfg()
        letter = self.shared_letter.get().strip() or "M:"
        unc = build_unc_from_cfg(o)
        if not unc:
            messagebox.showerror(
                "Map Drive",
                "Host IP is not set. Please enter it above before mapping.",
            )
            return
        if map_drive(unc, letter):
            self.shared_mode.set("DRIVE")
            sd = config.setdefault("SharedDrive", {})
            sd["preferred_mode"] = "DRIVE"
            sd["drive_letter"] = letter
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                config.write(f)
            update_fuser_shared_path()
            logging.info(f"Mapped {letter} to {unc}")
            messagebox.showinfo("Map Drive", f"Mapped {letter} to {unc}")
        else:
            messagebox.showerror("Map Drive", f"Failed to map {letter} to {unc}")

    def _unmap_drive(self):
        letter = self.shared_letter.get().strip() or "M:"
        unmap_drive(letter)
        sd = config.setdefault("SharedDrive", {})
        sd["preferred_mode"] = "UNC"
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            config.write(f)
        self.shared_mode.set("UNC")
        logging.info(f"Unmapped {letter}")
        messagebox.showinfo("Map Drive", f"Unmapped {letter}")
    def _save_host_ip(self):
        ip = self.host_ip_var.get().strip()
        try:
            set_host_ip(ip)
            messagebox.showinfo("Settings", f"Host IP set to: {ip or '[blank]'}")
        except Exception as exc:
            messagebox.showerror("Settings", str(exc))

    def _browse_rm_local_root(self):
        path = filedialog.askdirectory()
        if path:
            self.rm_local_var.set(os.path.normpath(path))

    def _save_rm_local_root(self):
        path = self.rm_local_var.get().strip()
        if path.startswith('\\\\'):
            messagebox.showerror("Settings", "UNC paths are not supported for the local install folder.")
            return
        # New validation: look for the .lnk
        if path and not is_valid_rm_local_root(path):
            messagebox.showerror(
                "Settings",
                (
                    f"'{path}' does not look like a Reality Mesh install folder.\n\n"
                    f"Expected to find '{RM_LNK_NAME}' somewhere under this folder.\n"
                    "Example: D:\\RealityMeshInstall\\Reality Mesh to VBS4.lnk"
                ),
            )
            return
        set_rm_local_root(path)
        pnl = self.controller.panels.get('OneClick')
        if pnl and hasattr(pnl, '_update_rm_status'):
            pnl._update_rm_status()
        messagebox.showinfo(
            "Settings",
            f"Reality Mesh install folder set to:\n{path}" if path else "Reality Mesh install folder cleared.",
        )

    def _create_path_row(self, text, command, initial_path, parent=None):
        """Create a consistent button/label row for file path settings."""
        parent = parent or self
        frame = tk.Frame(parent, bg="black")
        tk.Button(
            frame,
            text=text,
            font=("Helvetica", 20),
            bg="#444444",
            fg="white",
            command=command,
            bd=0,
            highlightthickness=0,
        ).pack(side="left", padx=(0, 10))
        lbl = tk.Label(
            frame,
            text=initial_path or "[not set]",
            font=("Helvetica", 14),
            bg="black",
            fg="white",
            anchor="w",
        )
        lbl.pack(side="left", fill="x", expand=True)
        frame.pack(fill="x", padx=10, pady=5)
        return lbl

    def _on_change_projects_root(self):
        self.controller.change_projects_root()
        self.lbl_projects_root.config(text=get_projects_root() or "[not set]")

    def _on_set_vbs4(self):
        path = filedialog.askopenfilename(
            title="Select VBS4 Executable",
            filetypes=[("Executable Files", "*.exe")]
        )
        if path and os.path.exists(path):
            path = os.path.normpath(path)
            config['General']['vbs4_path'] = path
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
            self.lbl_vbs4.config(text=path)
            vbs4_panel = self.controller.panels.get('VBS4')
            if vbs4_panel:
                vbs4_panel.update_vbs4_version()

    def _on_set_vbs4_setup(self):
     path = filedialog.askopenfilename(
        title="Select VBS4 Setup Launcher",
        filetypes=[("Executable Files", "*.exe")]
     )
     if path and os.path.exists(path):
        path = os.path.normpath(path)
        config['General']['vbs4_setup_path'] = path
        with open(CONFIG_PATH, 'w') as f:
            config.write(f)
        self.lbl_vbs4_setup.config(text=path)
        self.controller.panels['VBS4'].update_vbs4_launcher_button_state()

    def _on_set_blueig(self):
        set_blueig_install_path()
        self.lbl_blueig.config(text=get_blueig_install_path() or "[not set]")

    def _on_set_ares(self):
        set_ares_manager_path()
        self.lbl_ares.config(text=get_ares_manager_path() or "[not set]")

    def _on_set_browser(self):
        set_default_browser()
        self.lbl_browser.config(text=get_default_browser() or "[not set]")

    def _on_set_vbs_license_manager(self):
        path = filedialog.askopenfilename(
            title="Select VBSLicenseManager.exe",
            filetypes=[("Executable Files", "*.exe")]
        )
        if path and os.path.exists(path):
            config['General']['vbs_license_manager_path'] = path
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
            self.lbl_vbs_license.config(text=path)
            messagebox.showinfo("Settings", f"VBS License Manager path set to:\n{path}")
        else:
            messagebox.showerror("Settings", "Invalid VBS License Manager path selected.")

    def _on_set_oneclick(self):
        path = filedialog.askdirectory(title="Select One-Click Output Folder")
        if path:
            set_oneclick_output_path(path)
            self.lbl_oneclick.config(text=path)
        else:
            messagebox.showerror("Settings", "Invalid folder selected.")

    def update_oneclick_path_label(self):
        self.lbl_oneclick.config(text=get_oneclick_output_path() or "[not set]")

    def _on_launch_on_startup(self):
        toggle_startup()
        self.startup_var.set(is_startup_enabled())

    def _on_close_on_launch(self):
        toggle_close_on_launch()
        self.close_on_launch_var.set(is_close_on_launch_enabled())
        enforce_local_fuser_policy()

    def _on_fullscreen_toggle(self):
        self.controller.toggle_fullscreen()
        self.fullscreen_var.set(self.controller.fullscreen)
        
        # Update Settings panel scrollbar visibility
        if self.controller.fullscreen:
            # Fullscreen mode - hide the Settings scrollbar
            self._settings_scrollbar.pack_forget()
        else:
            # Windowed mode - show the Settings scrollbar
            self._settings_scrollbar.pack(side="right", fill="y")

class TutorialsPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="black", bd=0, highlightthickness=0)
        set_background(controller, self)
        self.configure(bg="black")
        
        # Ensure the background image shows through properly
        try:
            for child in self.winfo_children():
                if isinstance(child, tk.Label) and hasattr(child, 'image'):
                    child.lift()  # Move background image to top
                    break
        except Exception:
            pass

        # Grid container for 4 cards (2 x 2)
        # Using transparent bg to let the background image show through
        grid = tk.Frame(self, bg="", bd=0, highlightthickness=0)
        grid.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        
        # Make sure frame doesn't interfere with background
        grid.lower()
        
        for c in range(2):
            grid.grid_columnconfigure(c, weight=1, uniform="cards")
        for r in range(2):
            grid.grid_rowconfigure(r, weight=1, uniform="cards")

        # Helper to create a card and place it
        def create_card(row, col, title, items):
            card = TutorialCard(grid, title, items)
            card.grid(row=row, column=col, sticky="nsew", padx=10, pady=10)
            # Make sure card has proper z-order
            card.lift()  # Bring cards above transparent grid but below any overlays
            return card

        # Build 4 cards
        create_card(0, 0, "VBS4 Help", vbs4_help_items)
        create_card(0, 1, "BVI Help", bvi_help_items)
        create_card(1, 0, "One-Click Terrain Help", oct_help_items)
        create_card(1, 1, "Blue IG Help", blueig_help_items)

        # Back button (centered) - fully transparent to show background
        footer = tk.Frame(self, bd=0, highlightthickness=0, 
                         bg="#000000")  # Start with black, will be made transparent
        footer.pack(pady=12)
        # Use empty string to make it truly transparent
        footer.configure(background="")  
        footer.pack_propagate(True)      # Allow footer to collapse to button size
        
        # Create a dark styled back button directly - avoid any library functions that might use white
        back_btn = tk.Button(footer, text="Back", command=lambda: controller.show('Main'),
                         bg="#3a3a3a", fg="white",  # Dark gray background
                         activebackground="#4a4a4a", activeforeground="white",
                         font=("Helvetica", 16, "bold"),
                         bd=0, highlightthickness=0, padx=18, pady=8)
        back_btn.pack()
        
        # Add hover effects
        back_btn.bind("<Enter>", lambda e: back_btn.config(bg="#4a4a4a"))
        back_btn.bind("<Leave>", lambda e: back_btn.config(bg="#3a3a3a"))
            
        # Ensure this frame doesn't block the background
        footer.lower()
        
        # Call after a short delay to make sure background image is visible
        self.after(100, self._ensure_background_visible)
        
    def _ensure_background_visible(self):
        """Make sure the background image is visible and frames are transparent."""
        # Find the background image label and bring it to the correct z-order
        bg_label = None
        for child in self.winfo_children():
            if isinstance(child, tk.Label) and hasattr(child, 'image'):
                bg_label = child
                break
                
        if bg_label:
            # Put background behind content but in front of any solid color frames
            for child in self.winfo_children():
                if child != bg_label:
                    if isinstance(child, tk.Frame):
                        # Make sure frames don't create solid blocks
                        child.configure(bg="")
                        
                        # Special handling for the footer frame that contains the back button
                        if child.winfo_children() and isinstance(child.winfo_children()[0], tk.Button):
                            # Ensure the button is dark colored
                            btn = child.winfo_children()[0]
                            btn.configure(bg="#3a3a3a", fg="white")
                            btn.bind("<Enter>", lambda e, b=btn: b.config(bg="#4a4a4a"))
                            btn.bind("<Leave>", lambda e, b=btn: b.config(bg="#3a3a3a"))
                        
                        # Lift grid frames above the background
                        if hasattr(child, 'winfo_children'):
                            for grandchild in child.winfo_children():
                                if isinstance(grandchild, TutorialCard):
                                    grandchild.lift()
            
            # Final z-order arrangement
            bg_label.lower()  # Background at the very bottom


class TutorialCard(tk.Frame):
    def __init__(self, parent, title: str, items: dict[str, Callable]):
        super().__init__(parent,
                         bg="#1f1f1f",
                         highlightthickness=2,
                         highlightbackground="#333333",
                         highlightcolor="#333333",
                         bd=0)
        # Title
        tk.Label(self, text=title,
                 font=("Helvetica", 24, "bold"),
                 bg="#1f1f1f", fg="white", pady=10).pack(fill="x", padx=16, pady=(8, 0))

        # Divider
        tk.Frame(self, bg="#2b2b2b", height=1, bd=0, highlightthickness=0)\
            .pack(fill="x", padx=16, pady=(6, 10))

        # Button column
        body = tk.Frame(self, bg="#1f1f1f", bd=0, highlightthickness=0)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        for text, cmd in (items or {}).items():
            btn = make_link_btn(body, text, cmd)
            btn.pack(fill="x", pady=6)

    def add_item(self, text: str, command: Callable):
        btn = make_link_btn(self, text, command) 
        # reparent into the last packed frame (body)
        body = self.winfo_children()[-1]
        btn.master = body
        btn.pack(fill="x", pady=6)

def make_link_btn(parent, text, command):
    btn = tk.Button(parent, text=text, command=command,
                    bg="#3a3a3a", fg="white",
                    activebackground="#4a4a4a", activeforeground="white",
                    font=("Helvetica", 14, "bold"),
                    bd=0, highlightthickness=0,
                    padx=16, pady=10, wraplength=340, justify="center")

    def _enter(_):
        if btn["state"] != tk.DISABLED:
            btn.configure(bg="#4a4a4a")
    def _leave(_):
        if btn["state"] != tk.DISABLED:
            btn.configure(bg="#3a3a3a")
    btn.bind("<Enter>", _enter)
    btn.bind("<Leave>", _leave)
    return btn

class DarkButtons:
    @staticmethod
    def link(parent, text, command, disabled=False):
        b = tk.Button(parent, text=text, command=command,
                      bg="#3a3a3a", fg="white",
                      activebackground="#4a4a4a", activeforeground="white",
                      font=("Helvetica", 16, "bold"),
                      bd=0, highlightthickness=0, padx=18, pady=8)
        if disabled:
            b.configure(state=tk.DISABLED, bg="#777777")
        else:
            b.bind("<Enter>", lambda e: b.config(bg="#4a4a4a"))
            b.bind("<Leave>", lambda e: b.config(bg="#3a3a3a"))
        return b


def _round_rectangle(canvas, x1, y1, x2, y2, radius=20, **kwargs):
    """Draw a rounded rectangle on *canvas* from (x1,y1) to (x2,y2)."""
    points = [
        x1 + radius, y1,
        x1 + radius, y1,
        x2 - radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)

def create_card(parent, max_width=600, padding=20, radius=20, bg="#222222"):
    """Return a canvas and inner frame styled as a centered card."""
    canvas = tk.Canvas(parent, highlightthickness=0, bd=0)
    inner = tk.Frame(canvas, bg=bg)
    window = canvas.create_window(padding, padding, anchor="nw", window=inner)

    def _resize(event=None):
        inner.update_idletasks()
        width = min(max_width, inner.winfo_reqwidth() + 2 * padding)
        height = inner.winfo_reqheight() + 2 * padding
        canvas.config(width=width, height=height, bg=parent.cget("bg"))
        canvas.delete("card")
        _round_rectangle(canvas, 0, 0, width, height, radius, fill=bg, outline=bg, tags="card")
        canvas.coords(window, padding, padding)

    inner.bind("<Configure>", _resize)
    _resize()
    return canvas, inner

class CreditsPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#222222")
        set_background(controller, self)
        controller.create_tutorial_button(self)

        card_canvas, card = create_card(self)
        card_canvas.pack(pady=(20, 60))

        tk.Label(card, text="CREDITS", font=("Helvetica", 28, "bold"), bg="#222222", fg="white")\
            .pack(pady=(0, 20))

        if os.path.exists(logo_STE_path):
            img = Image.open(logo_STE_path).resize((90, 90), Image.Resampling.LANCZOS)
            ph = ImageTk.PhotoImage(img)
            tk.Label(card, image=ph, bg="#222222", borderwidth=0, highlightthickness=0)\
                .pack(pady=(0, 20))
            self.logo_image = ph

        tk.Label(card, text="STE Mission Planning Toolkit", font=("Helvetica", 18, "bold"),
                 bg="#222222", fg="white", anchor="w").pack(fill="x")

        tk.Label(card, text="Designed and developed by:", font=("Helvetica", 18, "bold"),
                 bg="#222222", fg="white", anchor="w").pack(fill="x", pady=(20, 0))
        tk.Label(card, text="Ryan Curphey - Developer", font=("Helvetica", 14),
                 bg="#222222", fg="white", anchor="w").pack(fill="x")
        tk.Label(card, text="Yovany Tietze-torres - Designer", font=("Helvetica", 14),
                 bg="#222222", fg="white", anchor="w")\
            .pack(fill="x", pady=(0, 20))

        tk.Label(card, text="Version: 1.0", font=("Helvetica", 18, "bold"),
                 bg="#222222", fg="white", anchor="w").pack(fill="x", pady=(0, 20))

        tk.Label(card, text="Special thanks to:", font=("Helvetica", 18, "bold"),
                 bg="#222222", fg="white", anchor="w").pack(fill="x")
        tk.Label(card, text="- The STE CFT team\n- All contributors and testers",
                 font=("Helvetica", 14), bg="#222222", fg="white", anchor="w",
                 justify="left").pack(fill="x", pady=(0, 20))

        tk.Button(card, text="Back", font=("Helvetica", 24), bg="#444444", fg="white",
                  width=30, height=1, command=lambda: controller.show('Main'),
                  bd=0, highlightthickness=0).pack(pady=(10, 0))

class ContactSupportPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#222222")
        set_background(controller, self)
        controller.create_tutorial_button(self)

        card_canvas, card = create_card(self)
        card_canvas.pack(pady=(20, 60))

        tk.Label(card, text="Contact Support", font=("Helvetica", 28, "bold"),
                 bg="#222222", fg="white").pack(pady=(0, 20))

        tk.Label(card,
                 text="For technical support or assistance, please contact:",
                 font=("Helvetica", 14), bg="#222222", fg="white",
                 anchor="w", justify="left", wraplength=560).pack(fill="x")

        tk.Label(card, text="Michael Enloe", font=("Helvetica", 18, "bold"),
                 bg="#222222", fg="white", anchor="w").pack(fill="x", pady=(20, 0))
        tk.Label(card, text="Cheif Technology Officer", font=("Helvetica", 14),
                 bg="#222222", fg="white", anchor="w").pack(fill="x")
        tk.Label(card, text="Email: michael.r.enloe.civ@army.mil", font=("Helvetica", 14),
                 bg="#222222", fg="white", anchor="w").pack(fill="x")

        tk.Label(card, text="Yovany Tietze-torres", font=("Helvetica", 18, "bold"),
                 bg="#222222", fg="white", anchor="w").pack(fill="x", pady=(20, 0))
        tk.Label(card, text="Senior Syetems Architect", font=("Helvetica", 14),
                 bg="#222222", fg="white", anchor="w").pack(fill="x")
        tk.Label(card, text="Email: yovany.e.tietze-torres.ctr@army.mil", font=("Helvetica", 14),
                 bg="#222222", fg="white", anchor="w").pack(fill="x")

        tk.Label(card,
                 text="US Army Futures Command, Synthetic Training Environment (STE)   Cross Functional Team (CFT)\n12809 Science Dr, Orlando, FL 32836",
                 font=("Helvetica", 14), bg="#222222", fg="white", anchor="w",
                 justify="left", wraplength=560).pack(fill="x", pady=(20, 0))

        tk.Label(card, text="Hours of Operation:", font=("Helvetica", 18, "bold"),
                 bg="#222222", fg="white", anchor="w").pack(fill="x", pady=(20, 0))
        tk.Label(card, text="Monday - Friday: 9:00 AM - 5:00 PM EST",
                 font=("Helvetica", 14), bg="#222222", fg="white", anchor="w")\
            .pack(fill="x")

        tk.Button(card, text="Contact Support via Email", font=("Helvetica", 24),
                  bg="#444444", fg="white", width=30, height=1,
                  command=self.contact_support, bd=0, highlightthickness=0)\
            .pack(pady=(30, 10))
        tk.Button(card, text="Back", font=("Helvetica", 24), bg="#444444",
                  fg="white", width=30, height=1,
                  command=lambda: controller.show('Main'), bd=0,
                  highlightthickness=0).pack(pady=(0, 10))

    def contact_support(self):
        webbrowser.open('mailto:yovany.e.tietze-torres.ctr@army.mil?subject=Support%20Request')

class Tooltip:
    """
    A simple tooltip that appears in its own undecorated Toplevel window.
    Usage:
        tip = Tooltip(parent)
        tip.show("Some text", x, y)
        tip.hide()
    """
    def __init__(self, parent):
        self.parent = parent
        self.tw = None

    def show(self, text, x, y):
        # If tooltip already exists, destroy it first:
        self.hide()
        self.tw = tk.Toplevel(self.parent)
        self.tw.wm_overrideredirect(True)  
        self.tw.attributes("-topmost", True)

        # Use a normal Label (not ttk) so we can set a custom background:
        label = tk.Label(
            self.tw,
            text=text,
            justify="left",
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=("Helvetica", 10)
        )
        label.pack(ipadx=4, ipady=2)
        self.tw.geometry(f"+{x}+{y}")

    def hide(self):
        if self.tw:
            self.tw.destroy()
            self.tw = None

def show_info_toast(parent: tk.Misc | None, message: str, duration_ms: int = 4000) -> None:
    """Display a short-lived notification near the bottom of the parent window."""
    if parent is None:
        return

    try:
        toast = tk.Toplevel(parent)
        toast.wm_overrideredirect(True)
        toast.attributes("-topmost", True)

        label = tk.Label(
            toast,
            text=message,
            bg="#333333",
            fg="white",
            font=("Helvetica", 12),
            padx=16,
            pady=10,
            wraplength=420,
            justify="center",
        )
        label.pack()

        parent.update_idletasks()
        toast.update_idletasks()

        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        tw = toast.winfo_width()
        th = toast.winfo_height()

        if pw <= 1 or ph <= 1:
            x = px + 40
            y = py + 40
        else:
            x = px + max(0, (pw - tw) // 2)
            y = py + max(0, ph - th - 40)

        toast.geometry(f"+{x}+{y}")
        toast.after(max(1000, duration_ms), toast.destroy)
    except Exception as exc:
        print(f"[toast] {exc}")

def run_command_server(host: str = "", port: int = 9100) -> None:
    """Listen for incoming command strings and execute them."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(1)
    while True:
        conn, _ = srv.accept()
        with conn:
            data = conn.recv(4096).decode().strip()
            if not data:
                continue
            try:
                args = shlex.split(data)
                subprocess.Popen(args, creationflags=NO_WINDOW_FLAG)
                conn.sendall(b"OK")
            except Exception as e:
                conn.sendall(f"ERROR: {e}".encode())

def start_command_server(port: int = 9100) -> None:
    thread = threading.Thread(target=run_command_server, args=("", port), daemon=True)
    thread.start()

if __name__ == "__main__":
    if not acquire_singleton():
        print("STE Toolkit is already running.")
        sys.exit(0)
    start_command_server()
    try:
        apply_offline_settings()
    except Exception as exc:
        print(f"[startup] apply_offline_settings: {exc}")

    try:
        update_fuser_shared_path()
    except Exception as exc:
        print(f"[startup] update_fuser_shared_path: {exc}")

    if not config.has_section('General'):
        config.add_section('General')
    should_prompt_settings = not config['General'].getboolean('first_run_done', fallback=False)

    app = MainApp()
    app.after(50, apply_minimal_wizard_defaults)
    app.after(75, lambda: enforce_wizard_obj_only_defaults(log=app.panels['OneClick'].log_message))
    app.after(50, update_fuser_shared_path)
    app.after(50, app.panels['OneClick'].update_fuser_state)
    app.after(50, enforce_local_fuser_policy)

    if should_prompt_settings:
        def _show_first_run_toast():
            try:
                app.show('Settings')
            except Exception as exc:
                print(f"[startup] show Settings: {exc}")
            show_info_toast(app, "Review settings (host name, drive letter, RM install path)")
            config['General']['first_run_done'] = 'True'
            _save_config()

        app.after(250, _show_first_run_toast)

    app.mainloop()
