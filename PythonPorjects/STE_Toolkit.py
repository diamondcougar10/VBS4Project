"""
STE Toolkit - VBS4 Simulation Training Environment Control Application

This application provides a unified interface for:
- Launching VBS4, BlueIG, and BVI simulation components
- Managing PhotoMesh/Reality Mesh 3D terrain processing
- Configuring and monitoring PhotoMesh Fuser instances across networked PCs
- Controlling shared network resources and UNC path management
- Automated scenario deployment and configuration management
"""

# ============================================================================
# TABLE OF CONTENTS
# ============================================================================
#
#  1. Memory Optimization Bootstrap
#  2. Imports
#  3. Resource Path Resolver
#  4. Messagebox Safety Wrappers
#  5. LAN Host Discovery (UDP Beacon)
#  6. SMB Session Management
#  7. Splash Screen Class
#  8. Constants & Globals
#  9. Logging Configuration
# 10. Singleton / Process Guard
# 11. Network Connection Helpers (UNC/SMB)
# 12. Presence Heartbeat Service
# 13. Threading Utilities
# 14. PhotoMesh Progress Parsing
# 15. Network / Path Helpers
# 16. VBS4 / BlueIG / BVI Path Resolution
# 17. Version & Executable Discovery
# 18. Executable Finder
# 19. Reality Mesh Link & UNC Resolution
# 20. Reality Mesh Dataset Helpers
# 21. Configuration & App Icon Management
# 22. Background Warmup Tasks
# 23. Auto-Launch Configuration
# 24. Fuser Configuration & Control
# 25. PhotoMesh Fuser Management
# 26. Settings Helpers (Registry & Toggles)
# 27. Generic Command Launch Helpers
# 28. BVI (ARES Manager) Launch
# 29. UI Assets & Background/Logos
# 30. Help/Tutorials & Document Openers
# 31. File Dialog / EXE Selection Helpers
# 32. Main Application Class (MainApp)
# 33. UI Panel Classes (MainMenu, VBS4, OneClick, BVI, Settings, etc.)
# 34. Launcher with Splash
#
# ============================================================================

# ============================================================================
# MEMORY OPTIMIZATION BOOTSTRAP
# Configure Python runtime for large-scale 3D data processing operations
# ============================================================================
import gc
import sys
import os

# Python runtime optimizations
if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(100000)

gc.set_threshold(700, 10, 10)
gc.enable()
os.environ['PYTHONOPTIMIZE'] = '2'

# Windows process memory configuration
if sys.platform == 'win32':
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetCurrentProcess()
        min_ws = 64 * 1024 * 1024    # 64MB minimum working set
        max_ws = 2048 * 1024 * 1024  # 2GB maximum working set
        kernel32.SetProcessWorkingSetSize(handle, min_ws, max_ws)
    except:
        pass

# ============================================================================
# IMPORTS
# ============================================================================

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
import platform
import itertools
from queue import Queue, Empty
import io
import time
import traceback

# Crash logging setup (early so hooks apply before other threads start)
_CRASH_DIR = os.path.join(os.getcwd(), "logs", "crash")
try:
    os.makedirs(_CRASH_DIR, exist_ok=True)
except Exception:
    pass

def _write_crash_log(exc_type, exc_value, exc_tb, origin="main"):
    try:
        ts = time.strftime("%Y%m%d-%H%M%S")
        fname = f"crash-{ts}-{origin}.txt"
        path = os.path.join(_CRASH_DIR, fname)
        stack = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
        diag = [
            f"Origin: {origin}",
            f"Timestamp: {ts}",
            f"Exe: {sys.argv[0]}",
            f"Python: {sys.version}",
            f"Working Dir: {os.getcwd()}",
            f"Platform Node: {platform.node()}",
            f"Primary IP: {socket.gethostbyname(socket.gethostname()) if socket.gethostname() else 'unknown'}",
            f"Host IP (cfg): N/A (config may not yet be loaded)",
            "--- STACK TRACE ---",
            stack,
        ]
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(diag))
        try:
            logging = globals().get('logging')
            if logging:
                logging.error(f"[crash] Unhandled exception captured -> {path}")
        except Exception:
            pass
    except Exception:
        pass

def _global_excepthook(exc_type, exc_value, exc_tb):
    _write_crash_log(exc_type, exc_value, exc_tb, origin="sys.excepthook")
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _global_excepthook

def _threading_excepthook(args):
    _write_crash_log(args.exc_type, args.exc_value, args.exc_traceback, origin="thread")
    if hasattr(threading, '__excepthook__'):
        try:
            threading.__excepthook__(args)
        except Exception:
            pass

try:
    threading.excepthook = _threading_excepthook  # Python 3.8+
except Exception:
    pass
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
    import pyi_splash  # type: ignore[import]
except Exception:
    pyi_splash = None

# ============================================================================
# RESOURCE PATH RESOLVER
# Handles bundled resources in both development and PyInstaller frozen builds
# ============================================================================

def _resource_path(name: str) -> str:
    """
    Resolve absolute path to a bundled resource file.
    In frozen builds, resources are extracted to sys._MEIPASS temporary directory.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    return os.path.join(base, name)


# ============================================================================
# MESSAGEBOX SAFETY WRAPPERS
# Ensures dialogs properly parent to main window to prevent fullscreen issues
# ============================================================================

# -----------------------------------------------------------------------------
# Frozen-build and first-run helpers
# -----------------------------------------------------------------------------
def is_frozen_build() -> bool:
    """Return True when running under PyInstaller (frozen) build."""
    try:
        return bool(getattr(sys, "frozen", False))
    except Exception:
        return False

def _first_run_flag_path() -> str:
    """Location of the first-run completion marker."""
    base = os.environ.get('PROGRAMDATA', r'C:\\ProgramData')
    folder = os.path.join(base, 'STE Toolkit')
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        pass
    return os.path.join(folder, 'first_run_complete.flag')


def safe_messagebox_showerror(title, message, **kwargs):
    """Show error dialog with automatic parent window handling."""
    global APP_INSTANCE
    if APP_INSTANCE and 'parent' not in kwargs:
        kwargs['parent'] = APP_INSTANCE
    return messagebox.showerror(title, message, **kwargs)

def safe_messagebox_showwarning(title, message, **kwargs):
    """Show warning dialog with automatic parent window handling."""
    global APP_INSTANCE
    if APP_INSTANCE and 'parent' not in kwargs:
        kwargs['parent'] = APP_INSTANCE
    return messagebox.showwarning(title, message, **kwargs)

def safe_messagebox_showinfo(title, message, **kwargs):
    """Show info dialog with automatic parent window handling."""
    global APP_INSTANCE
    if APP_INSTANCE and 'parent' not in kwargs:
        kwargs['parent'] = APP_INSTANCE
    return messagebox.showinfo(title, message, **kwargs)

def safe_messagebox_askyesno(title, message, **kwargs):
    """Show yes/no dialog with automatic parent window handling."""
    global APP_INSTANCE
    if APP_INSTANCE and 'parent' not in kwargs:
        kwargs['parent'] = APP_INSTANCE
    return messagebox.askyesno(title, message, **kwargs)


# ============================================================================
# LAN HOST DISCOVERY
# UDP beacon broadcasting and listening for automatic peer discovery
# ============================================================================

BEACON_MAGIC = "STE_TOOLKIT_BEACON_V1"
BEACON_PORT = 40609
_BCN_STOP = threading.Event()
_BCN_THREAD = None
_LST_STOP = threading.Event()
_LST_THREAD = None

# Cache for received beacon data with fuser counts (pc_name -> {ip, fuser_count, ts})
_BEACON_CACHE = {}
_BEACON_CACHE_LOCK = threading.Lock()


# ============================================================================
# SMB SESSION MANAGEMENT
# Handles Windows UNC path authentication and connection caching
# ============================================================================

SMB_SESSION_CACHE = {}
SMB_SESSION_LOCK = threading.Lock()
_NETWORK_ERROR_SHOWN = False

def is_running_elevated():
    """Check if process is running with administrator privileges."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def ensure_smb_session_cached(unc_path, username=None, password=None, timeout=5):
    """
    Establish and cache a persistent SMB session to the given UNC path.
    Prevents ERROR 1219 by ensuring only one credential set per host.
    - App tries to create another session under user token
    - Windows rejects with ERROR 1219 (multiple connections)
    
    Args:
        unc_path: UNC path like \\\\host\\share or \\\\host\\share\\subfolder
        username: Optional username (e.g., DOMAIN\\user or host\\user)
        password: Optional password
        timeout: Timeout in seconds for connection attempts
        
    Returns:
        True if session is established or already exists, False otherwise
    """
    if not unc_path or not unc_path.startswith("\\\\"):
        logging.warning(f"[smb] Invalid UNC path: {unc_path}")
        return False
    
    # Extract host from UNC path
    parts = unc_path.strip("\\").split("\\")
    if len(parts) < 2:
        logging.warning(f"[smb] Cannot extract host from: {unc_path}")
        return False
    
    host = parts[0]
    share = parts[1] if len(parts) > 1 else ""
    unc_root = f"\\\\{host}\\{share}" if share else f"\\\\{host}"
    
    # Check cache first
    with SMB_SESSION_LOCK:
        if SMB_SESSION_CACHE.get(host):
            logging.debug(f"[smb] Using cached session for {host}")
            return True
    
    # Try to access without connecting first
    try:
        if quick_unc_check(unc_root, timeout=2):
            logging.info(f"[smb] Path already accessible: {unc_root}")
            with SMB_SESSION_LOCK:
                SMB_SESSION_CACHE[host] = True
            return True
    except Exception as e:
        logging.debug(f"[smb] Quick check failed for {unc_root}: {e}")
    
    # Build net use command
    cmd = ['net', 'use', unc_root]
    if username:
        cmd.extend([f'/user:{username}', password or ""])
    cmd.append('/persistent:no')  # Non-persistent to avoid cross-token issues
    
    # Try to establish session
    logging.info(f"[smb] Establishing session for {unc_root}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
         
        rc = result.returncode
        stderr_text = (result.stderr or "").lower()
        stdout_text = (result.stdout or "").lower()
        combined = stderr_text + stdout_text
        
        # Log the detailed output
        logging.debug(f"[smb] net use returned: rc={rc}, stdout={result.stdout}, stderr={result.stderr}")
        
        # Success 
        if rc == 0:
            logging.info(f"[smb] Session established successfully for {unc_root}")
            with SMB_SESSION_LOCK:
                SMB_SESSION_CACHE[host] = True
            return True
        
        if "already" in combined or "remembered" in combined:
            logging.info(f"[smb] Session already exists for {unc_root}")
            with SMB_SESSION_LOCK:
                SMB_SESSION_CACHE[host] = True
            return True
        
        # ERROR 1219: Multiple connections with different credentials
        if "1219" in combined or "multiple connections" in combined:
            logging.warning(f"[smb] ERROR 1219 detected for {unc_root} - clearing and retrying")
            
            # Clear ALL connections to this host
            subprocess.run(['net', 'use', f'\\\\{host}', '/delete', '/y'],
                         capture_output=True, timeout=3,
                         creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            subprocess.run(['net', 'use', f'\\\\{host}\\IPC$', '/delete', '/y'],
                         capture_output=True, timeout=3,
                         creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            
            # Wait a moment for Windows to clean up
            time.sleep(0.5)
            
            # Retry the connection
            result2 = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            
            if result2.returncode == 0 or "already" in (result2.stdout + result2.stderr).lower():
                logging.info(f"[smb] Session established after clearing conflicts for {unc_root}")
                with SMB_SESSION_LOCK:
                    SMB_SESSION_CACHE[host] = True
                return True
            else:
                logging.error(f"[smb] Retry failed for {unc_root}: {result2.stderr}")
                return False
        
        # Other errors
        logging.error(f"[smb] Failed to establish session for {unc_root}: rc={rc}, stderr={result.stderr}")
        return False
        
    except subprocess.TimeoutExpired:
        logging.error(f"[smb] Connection timeout for {unc_root}")
        return False
    except Exception as e:
        logging.error(f"[smb] Exception establishing session for {unc_root}: {e}")
        return False

def _compose_beacon_payload() -> bytes:
    try:
        o = get_offline_cfg()
        
        # Include real-time fuser count for host to display
        fuser_count = 0
        try:
            fuser_count = count_local_fusers()
        except Exception:
            pass
        
        # Determine this node's role: 'host' only if the share exists locally (real host)
        role = "user"
        try:
            share_name = (o.get("share_name") or "SharedMeshDrive").strip() or "SharedMeshDrive"
            rc, out, err = _run(["net", "share", share_name], timeout=2.0)
            if rc == 0 and "Path" in out:
                role = "host"
        except Exception:
            pass

        # Advertise our *primary* IPv4 (never the config host_ip if that equals self) to avoid self‑adoption loops
        primary_ip = get_primary_ipv4() or _machine_ip_fast() or (o.get("host_ip") or "")

        payload = {
            "magic": BEACON_MAGIC,
            "pc": platform.node(),
            "ip": primary_ip,
            "role": role,
            "share": (o.get("share_name") or "SharedMeshDrive"),
            "wf_sub": (o.get("working_fuser_subdir") or "WorkingFuser"),
            "fuser_count": fuser_count,  # Real-time running fuser count
            "ts": int(time.time()),
        }
        return json.dumps(payload).encode("utf-8")
    except Exception:
        return b""

def _host_beacon_loop():
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1.0)
        while not _BCN_STOP.is_set():
            try:
                data = _compose_beacon_payload()
                if data:
                    sock.sendto(data, ("255.255.255.255", BEACON_PORT))
            except Exception:
                pass
            _BCN_STOP.wait(2.0)
    finally:
        try:
            if sock:
                sock.close()
        except Exception:
            pass

def start_host_beacon():
    global _BCN_THREAD
    if _BCN_THREAD and _BCN_THREAD.is_alive():
        return
    try:
        _BCN_STOP.clear()
    except Exception:
        pass
    _BCN_THREAD = threading.Thread(target=_host_beacon_loop, name="host-beacon", daemon=True)
    _BCN_THREAD.start()
    logging.info("[beacon] Host UDP beacon started")

def stop_host_beacon():
    try:
        _BCN_STOP.set()
        global _BCN_THREAD
        if _BCN_THREAD and _BCN_THREAD.is_alive():
            try:
                _BCN_THREAD.join(timeout=1.5)
            except Exception:
                pass
        _BCN_THREAD = None
    except Exception:
        pass

def _user_listener_loop():
    """
    User PC listener: receives host beacons for auto-discovery.
    Also caches all beacon data (including fuser counts) for potential display.
    """
    sock = None
    last_set = 0
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception:
            pass
        sock.bind(("", BEACON_PORT))
        sock.settimeout(1.0)
        while not _LST_STOP.is_set():
            try:
                data, _addr = sock.recvfrom(4096)
                if not data:
                    continue
                try:
                    d = json.loads(data.decode("utf-8", errors="ignore"))
                except Exception:
                    continue
                if not isinstance(d, dict) or d.get("magic") != BEACON_MAGIC:
                    continue
                ip = (d.get("ip") or "").strip()
                pc = (d.get("pc") or "").strip()
                role = (d.get("role") or "user").strip()
                if not ip or not pc:
                    continue
                
                # Cache beacon data with fuser count for display
                with _BEACON_CACHE_LOCK:
                    _BEACON_CACHE[pc] = {
                        "ip": ip,
                        "fuser_count": int(d.get("fuser_count", 0)),
                        "ts": d.get("ts", int(time.time())),
                        "last_seen": time.time(),
                    }
                
                # Auto-discover host IP (user PCs only)
                now = time.time()
                if now - last_set < 3.0:
                    continue
                cur = config.get("Offline", "host_ip", fallback="").strip()
                # Ignore beacons from ourselves (compare against our primary IP)
                self_ip = get_primary_ipv4() or _machine_ip_fast()
                if ip == self_ip:
                    continue
                # Only adopt host from a beacon explicitly marked as role='host'
                if role == "host" and (not cur or cur != ip):
                    logging.info(f"[beacon] Discovered host {ip} (role={role}); applying")
                    try:
                        set_host_ip(ip)
                        connect_working_share_interactive(parent=None, silent=True)
                    except Exception:
                        pass
                    last_set = now
            except socket.timeout:
                pass
            except Exception:
                pass
    finally:
        try:
            if sock:
                sock.close()
        except Exception:
            pass

def start_user_listener():
    global _LST_THREAD
    if _LST_THREAD and _LST_THREAD.is_alive():
        return
    try:
        _LST_STOP.clear()
    except Exception:
        pass
    _LST_THREAD = threading.Thread(target=_user_listener_loop, name="user-listener", daemon=True)
    _LST_THREAD.start()
    logging.info("[beacon] User UDP listener started")

def stop_user_listener():
    try:
        _LST_STOP.set()
        global _LST_THREAD
        if _LST_THREAD and _LST_THREAD.is_alive():
            try:
                _LST_THREAD.join(timeout=1.5)
            except Exception:
                pass
        _LST_THREAD = None
    except Exception:
        pass

def get_live_fuser_counts_from_beacons(timeout_sec=10):
    """
    Get real-time fuser counts from cached beacon data.
    Returns dict: {pc_name: fuser_count} for PCs seen within timeout_sec.
    
    This provides live running counts (actual processes) instead of seeded directories.
    Ideal for host status display showing which user PCs have live fusers.
    """
    result = {}
    now = time.time()
    
    with _BEACON_CACHE_LOCK:
        for pc, data in list(_BEACON_CACHE.items()):
            last_seen = data.get("last_seen", 0)
            if now - last_seen <= timeout_sec:
                result[pc] = int(data.get("fuser_count", 0))
    
    return result

def safe_filedialog_askdirectory(**kwargs):
    """Global wrapper for filedialog.askdirectory with proper parenting."""
    global APP_INSTANCE
    if APP_INSTANCE and 'parent' not in kwargs:
        kwargs['parent'] = APP_INSTANCE
    return filedialog.askdirectory(**kwargs)

def safe_filedialog_askopenfilename(**kwargs):
    """Global wrapper for filedialog.askopenfilename with proper parenting."""
    global APP_INSTANCE
    if APP_INSTANCE and 'parent' not in kwargs:
        kwargs['parent'] = APP_INSTANCE
    return filedialog.askopenfilename(**kwargs)

def safe_simpledialog_askstring(title, prompt, **kwargs):
    """Global wrapper for simpledialog.askstring with proper parenting."""
    global APP_INSTANCE
    if APP_INSTANCE and 'parent' not in kwargs:
        kwargs['parent'] = APP_INSTANCE
    return simpledialog.askstring(title, prompt, **kwargs)

# --- UI setup pt 1 ---
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

# =============================================================================
# Splash Screen (non-blocking, keeps main focused)
# =============================================================================
class SplashScreen(tk.Toplevel):
    """
    A lightweight, non-interactive splash that overlays the main window,
    fades in/out, shows status messages, and displays a progress bar.
    It never steals focus and has a minimum display time.
    """
    def __init__(self, master, image_path=None, version_text="", start_alpha=0.0, end_alpha=0.98, min_display_time=3.0):
        super().__init__(master)
        self.withdraw()  # Hide initially to prevent flash
        self.overrideredirect(True)              # borderless
        self._is_splash = True
        self.attributes("-alpha", start_alpha)
        self._alpha_target = float(end_alpha)
        self._alpha_step   = 0.08
        self._closing      = False
        self._start_time = time.time()
        self._min_display_time = float(min_display_time)  # in seconds
        self._ready_to_close = False
        self._progress = 0.0
        
        # Canvas with image and text
        self.configure(bg="#000")
        frm = tk.Frame(self, bg="#000")
        frm.pack(padx=16, pady=16)
        self._img_lbl = None
        if image_path and os.path.isfile(image_path):
            try:
                img = Image.open(image_path)
                img.thumbnail((560, 340), Image.Resampling.LANCZOS)
                self._ph = ImageTk.PhotoImage(img)
                self._img_lbl = tk.Label(frm, image=self._ph, bg="#000")
                self._img_lbl.pack()
            except Exception:
                pass

        self._msg_var = tk.StringVar(value="Starting…")
        self._msg = tk.Label(
            frm, textvariable=self._msg_var, font=("Helvetica", 12),
            bg="#000", fg="white"
        )
        self._msg.pack(pady=(10,0))
        
        # Add a progress bar
        progress_frame = tk.Frame(frm, bg="#000")
        progress_frame.pack(fill="x", expand=True, pady=(15, 5))
        
        # Calculate progress bar width based on image or default size
        progress_width = 400 if not self._img_lbl else min(500, img.width * 0.8 if 'img' in locals() else 400)
        
        # Create an empty canvas for the progress bar background
        self._progress_canvas = tk.Canvas(
            progress_frame, 
            height=10, 
            width=progress_width,
            bg="#111111", 
            highlightthickness=0
        )
        self._progress_canvas.pack()
        
        # Create the progress bar fill rectangle
        self._progress_bar = self._progress_canvas.create_rectangle(
            0, 0, 0, 10, fill="#4CAF50", width=0
        )
        
        # Add percentage text below progress bar
        self._percent_var = tk.StringVar(value="0%")
        self._percent_label = tk.Label(
            progress_frame,
            textvariable=self._percent_var,
            font=("Helvetica", 9),
            bg="#000",
            fg="#bbbbbb"
        )
        self._percent_label.pack()

        self._ver = tk.Label(
            frm, text=version_text, font=("Helvetica", 10),
            bg="#000", fg="#bbbbbb"
        )
        if version_text:
            self._ver.pack(pady=(5,0))

        # position centered on the screen
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w  = self.winfo_reqwidth()
        h  = self.winfo_reqheight()
        x  = max(0, (sw - w)//2)
        y  = max(0, (sh - h)//2)
        self.geometry(f"{w}x{h}+{x}+{y}")

        # Start the progress update
        self._animate_progress()
        
        # Add failsafe close: hard ceiling of 10 seconds
        self.after(int(10_000), lambda: (None if self._closing else self.close()))
        self.deiconify()
        self._fade_in()
        
    def _animate_progress(self):
        """Animate the progress bar to give visual feedback during loading"""
        if self._closing:
            return
            
        # Calculate elapsed time as a percentage of min display time
        elapsed = time.time() - self._start_time
        target_progress = min(1.0, elapsed / self._min_display_time)
        
        # For smoother animation, move the progress towards the target
        if self._progress < target_progress:
            self._progress = min(self._progress + 0.01, target_progress)
        
        # Update the progress bar
        width = self._progress_canvas.winfo_width()
        filled_width = int(width * self._progress)
        self._progress_canvas.coords(self._progress_bar, 0, 0, filled_width, 10)
        self._percent_var.set(f"{int(self._progress * 100)}%")
        
        # Schedule next update
        self.after(30, self._animate_progress)
        
        # Check if we've reached the minimum display time
        if self._ready_to_close and self._progress >= 1.0:
            self.after(500, self._begin_close) 
        
    def _begin_close(self):
        """Start the fade out process"""
        try:
            self._closing = True
            try: self.attributes("-disabled", False)
            except Exception: pass
            self._fade_out()
        except Exception:
            # If anything fails, just destroy the window immediately
            try:
                self.destroy()
            except Exception:
                pass

    def set_message(self, text: str) -> None:
        """Update the message shown on the splash screen"""
        self._msg_var.set(text or "")

    def set_progress(self, value: float) -> None:
        """
        Manually set progress value (0.0 to 1.0)
        Note: This won't override the minimum time constraint
        """
        self._progress = max(0.0, min(1.0, float(value)))

    def _fade_in(self):
        if self._closing:
            return
        cur = float(self.attributes("-alpha") or 0.0)
        if cur < self._alpha_target:
            cur = min(self._alpha_target, cur + self._alpha_step)
            self.attributes("-alpha", cur)
            self.after(16, self._fade_in)

    def close(self):
        """
        Request to close the splash screen.
        Will only close after the minimum display time has elapsed.
        """
        self._ready_to_close = True
        
        # Check if we've already met the minimum display time
        elapsed = time.time() - self._start_time
        if elapsed >= self._min_display_time:
            self.after(0, self._begin_close)

    def _fade_out(self):
        try:
            cur = float(self.attributes("-alpha") or 0.0)
            if cur > 0.0:
                self.attributes("-alpha", max(0.0, cur - 0.10))
                self.after(16, self._fade_out)
            else:
                # ensure we don't steal focus on destroy
                try: self.master.focus_force()
                except Exception: pass
                # Make sure splash is completely gone before main window is shown
                self.destroy()
        except Exception:
            # Window already destroyed - just finish
            try:
                self.destroy()
            except Exception:
                pass

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
    level=logging.DEBUG,
    filename='ste_toolkit.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s'
)
# Force flush logs immediately to help diagnose startup hangs
logging.getLogger().handlers[0].setLevel(logging.DEBUG)

# =============================================================================
# CRASH LOGGING (unhandled exceptions)
# =============================================================================
# Writes detailed crash reports to a dedicated folder for post‑mortem analysis.
# Captures:
#   - Exception type/value/traceback
#   - Timestamp & uptime
#   - Process & memory stats
#   - Key config values (host_ip, desired/local counts, role)
#   - Fuser process counts & PIDs
#   - Tail of main application log (for recent context)
#   - Thread name (if from threading.excepthook)

_APP_BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) \
                else os.path.abspath(os.path.dirname(__file__))
_CRASH_LOG_DIR = os.path.join(_APP_BASE_DIR, "crash_logs")

def _ensure_crash_dir():
    try:
        os.makedirs(_CRASH_LOG_DIR, exist_ok=True)
    except Exception:
        pass

_APP_START_TIME = time.time()

def _tail_file(path: str, max_lines: int = 200) -> str:
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        return ''.join(lines[-max_lines:])
    except Exception:
        return '<unavailable>'

def _fuser_diag() -> str:
    try:
        running = []
        for p in psutil.process_iter(['pid','name','cmdline']):
            try:
                if (p.info.get('name') or '').lower() == 'photomeshfuser.exe':
                    running.append(p)
            except Exception:
                pass
        out = [f"count={len(running)}"]
        for p in running[:25]:  # cap detail
            out.append(f"pid={p.pid} cmd={' '.join(p.info.get('cmdline') or [])[:200]}")
        return '\n'.join(out)
    except Exception as e:
        return f'<fuser diag failed: {e}>'

def _build_crash_report(exc_type, exc_value, exc_tb, thread_name: str | None = None) -> str:
    import traceback
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    uptime = f"{time.time() - _APP_START_TIME:.1f}s"
    cfg_host_ip = ''
    desired = ''
    role = ''
    try:
        cfg_host_ip = config.get('Offline','host_ip', fallback='')
        desired = config.get('Fusers','desired_count', fallback='')
        role = 'HOST' if is_this_pc_the_real_host() else ('FUSER' if config.getboolean('Fusers','fuser_computer', fallback=False) else 'CLIENT')
    except Exception:
        pass
    mem_info = ''
    try:
        p = psutil.Process()
        mi = p.memory_info()
        mem_info = f"rss={mi.rss} vms={mi.vms}"
    except Exception:
        pass
    log_tail = _tail_file('ste_toolkit.log')
    tb_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    return (
        f"=== STE Toolkit Crash Report ===\n"
        f"Timestamp: {now}\n"
        f"Uptime: {uptime}\n"
        f"Thread: {thread_name or 'Main'}\n"
        f"Exception: {exc_type.__name__}: {exc_value}\n"
        f"Role: {role}\n"
        f"Host IP (config): {cfg_host_ip}\n"
        f"Desired Fusers: {desired}\n"
        f"Fuser Processes:\n{_fuser_diag()}\n"
        f"Memory: {mem_info}\n"
        f"Python: {sys.version}\n"
        f"Executable: {sys.executable}\n"
        f"Args: {' '.join(sys.argv)}\n"
        f"Traceback:\n{tb_str}\n"
        f"--- Log Tail (last 200 lines) ---\n{log_tail}\n"
    )

def _write_crash_report(content: str):
    _ensure_crash_dir()
    ts = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    path = os.path.join(_CRASH_LOG_DIR, f"crash-{ts}.txt")
    try:
        with open(path,'w', encoding='utf-8') as f:
            f.write(content)
        logging.error(f"[crash] Crash report written to {path}")
    except Exception as e:
        logging.error(f"[crash] Failed writing crash report: {e}")

_ORIG_EXCEPTHOOK = sys.excepthook

def _global_excepthook(exc_type, exc_value, exc_tb):
    try:
        rep = _build_crash_report(exc_type, exc_value, exc_tb, thread_name=None)
        _write_crash_report(rep)
    finally:
        try:
            _ORIG_EXCEPTHOOK(exc_type, exc_value, exc_tb)
        except Exception:
            pass

sys.excepthook = _global_excepthook

# Threading hook (Python >=3.8)
try:
    import threading as _th
    _ORIG_THREAD_HOOK = getattr(_th, 'excepthook', None)
    def _thread_excepthook(args):
        try:
            rep = _build_crash_report(args.exc_type, args.exc_value, args.exc_traceback, thread_name=getattr(args, 'thread', None) and args.thread.name)
            _write_crash_report(rep)
        finally:
            if _ORIG_THREAD_HOOK:
                try:
                    _ORIG_THREAD_HOOK(args)
                except Exception:
                    pass
    if hasattr(_th,'excepthook'):
        _th.excepthook = _thread_excepthook
except Exception:
    pass

def attach_tk_exception_hook(root):
    """Redirect uncaught Tk callbacks to crash logger instead of silent fail."""
    try:
        import tkinter as _tk
        def _report_callback_exception(exc_type, exc_value, exc_tb):
            rep = _build_crash_report(exc_type, exc_value, exc_tb, thread_name='TkCallback')
            _write_crash_report(rep)
            # Also log for immediate visibility
            logging.error(f"[tk-crash] {exc_type.__name__}: {exc_value}")
        root.report_callback_exception = _report_callback_exception  # type: ignore[attr-defined]
        logging.info("[crash] Tk exception hook attached")
    except Exception as e:
        logging.warning(f"[crash] Failed attaching Tk hook: {e}")

# --- Hidden subprocess helper (Windows console-free execution) ---
CREATE_NO_WINDOW = 0x08000000
IS_WIN = (os.name == "nt")

# --- Debounce lock for periodic fuser checks (prevents overlapping calls) ---
_FUSER_CHECK_LOCK = threading.Lock()
_LAST_FUSER_CHECK = 0.0

def run_hidden(cmd, *, timeout=15, cwd=None, check=False, text=True, capture_output=True, env=None):
    """
    Run a console command invisibly on Windows; safe cross-platform fallback elsewhere.
    
    This prevents console window flashes by:
    - Using CREATE_NO_WINDOW flag (no console creation)
    - Setting STARTF_USESHOWWINDOW + SW_HIDE (hide window if one exists)
    - Avoiding shell=True (prevents cmd.exe window)
    
    Args:
        cmd: Command as list (e.g., ["tasklist", "/FI", "..."])
        timeout: Max seconds to wait
        cwd: Working directory
        check: Raise on non-zero exit
        text: Return stdout/stderr as strings (not bytes)
        capture_output: Capture stdout/stderr
        env: Environment variables
    
    Returns:
        CompletedProcess with .returncode, .stdout, .stderr
    """
    if not IS_WIN:
        # Non-Windows: normal run (no console flashes anyway)
        return subprocess.run(
            cmd, 
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            cwd=cwd, 
            timeout=timeout, 
            check=check, 
            text=text,
            env=env
        )

    # Windows: hide console completely
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE

    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        cwd=cwd,
        timeout=timeout,
        check=check,
        text=text,
        env=env,
        shell=False,  # Critical: avoid cmd.exe
        startupinfo=si,
        creationflags=CREATE_NO_WINDOW
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
    # Register fuser cleanup on exit
    atexit.register(kill_all_fusers_on_exit)
    # Register presence service cleanup on exit
    atexit.register(stop_presence_service)
    # Stop UDP beacons/listeners on exit
    atexit.register(stop_host_beacon)
    atexit.register(stop_user_listener)
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
# NETWORK CONNECTION HELPERS FOR WORKING FUSER UNC
# =============================================================================

# --- UNC session guard / throttle ---
_UNC_SESS_LOCK = threading.Lock()
_UNC_SESS_CACHE = {}      
_UNC_SESS_COOLDOWN = 120  
_NET_USE_LAST_TS = 0.0
_NET_USE_MIN_GAP = 1.0     # at least 1s between 'net use' calls

def quick_ping_check(host_ip: str, timeout: float = 0.8) -> bool:
    """Quick ping check to avoid spinning up SMB when host is plainly offline."""
    if not host_ip:
        return False
        
    try:
        # Use ping with short timeout and single attempt
        result = subprocess.run(
            ["ping", "-n", "1", "-w", "400", host_ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            creationflags=0x08000000 
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False

def quick_unc_check(unc_path, timeout=3):
    """Try UNC accessibility quickly with timeout — prevents startup hangs."""
    if not unc_path:
        return False
    
    result = Queue()

    def _try():
        try:
            # Quick access test for local paths
            if not unc_path.startswith("\\\\"):
                result.put(os.path.isdir(unc_path))
                return
            try:
                # Extract host from UNC path (\\host\share\path -> \\host)
                parts = unc_path.split("\\")
                if len(parts) >= 3:
                    host = f"\\\\{parts[2]}"
                    subprocess_timeout = max(1, timeout - 1.0)
                    rc = subprocess.run(
                        ["net", "view", host],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=subprocess_timeout,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    ).returncode
                    
                    if rc == 0:
                        # Host is reachable, now check if path exists
                        result.put(True)
                        return
            except subprocess.TimeoutExpired:
                logging.debug(f"[quick_unc_check] net view timed out for {unc_path}")
            except Exception as e:
                logging.debug(f"[quick_unc_check] net view failed: {e}")

            # Method 2: Try dir command as fallback 
            try:
                subprocess_timeout = max(1, timeout - 0.5)
                rc = subprocess.run(
                    ["cmd", "/c", "dir", unc_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=subprocess_timeout,
                    creationflags=subprocess.CREATE_NO_WINDOW
                ).returncode
                result.put(rc == 0)
                return
            except subprocess.TimeoutExpired:
                logging.debug(f"[quick_unc_check] dir command timed out")
            except Exception as e:
                logging.debug(f"[quick_unc_check] dir command failed: {e}")
            
            # Method 3: Last resort - os.path.exists
            try:
                result.put(os.path.exists(unc_path))
            except:
                result.put(False)
                
        except Exception as e:
            logging.debug(f"[quick_unc_check] Unexpected error: {e}")
            result.put(False)

    t = threading.Thread(target=_try, daemon=True)
    t.start()
    t.join(timeout)
    
    try:
        return not result.empty() and result.get_nowait()
    except:
        return False

def discover_host_ip_quick(timeout_per_host: float = 0.5) -> str:
    r"""Best-effort discovery of the Host IP on the local subnet.

    Strategy:
    - If Offline.host_ip exists and is reachable (ping + UNC probe), use it.
    - Otherwise, ARP-scan likely gateway and a small range of last octets (1,10,20,50,100):
      try \\<candidate>\SharedMeshDrive fast with quick checks.
    Returns the first responding IP or ''. Non-blocking per host with tight timeouts.
    """
    try:
        # 1) Use configured IP if valid
        ip = config.get("Offline", "host_ip", fallback="").strip()
        if ip:
            if quick_ping_check(ip, timeout=timeout_per_host) or can_access_unc(rf"\\{ip}\SharedMeshDrive"):
                return ip
        # 2) Try common candidates on the local subnet
        local = get_primary_ipv4()
        if not local or local.count(".") != 3:
            return ""
        parts = local.split(".")
        base = ".".join(parts[:3])
        candidates = [
            f"{base}.1",
            f"{base}.10",
            f"{base}.20",
            f"{base}.50",
            f"{base}.100",
        ]
        for cand in candidates:
            try:
                if quick_ping_check(cand, timeout=timeout_per_host):
                    if can_access_unc(rf"\\{cand}\SharedMeshDrive") or quick_unc_check(rf"\\{cand}\SharedMeshDrive", timeout=1):
                        return cand
            except Exception:
                continue
    except Exception:
        pass
    return ""

def auto_connect_shared_working_folder() -> bool:
    """Ensure Offline.host_ip is discovered and connect to WorkingFuser UNC.

    - Discovers host IP if missing.
    - Updates Offline.host_ip and Fusers.working_folder_host.
    - Tries to connect silently to the share root and verifies the WorkingFuser path.
    Returns True on success, False otherwise.
    """
    try:
        o = get_offline_cfg()
        ip = (o.get("host_ip") or "").strip()
        if not ip:
            ip = discover_host_ip_quick()
            if ip:
                set_host_ip(ip)

        if not ip:
            return False

        # Try to connect to the share root quickly
        unc_root = build_unc_from_cfg(o | {"host_ip": ip}) if '|' in dir(dict) else build_unc_from_cfg({**o, "host_ip": ip})
        if not unc_root:
            unc_root = rf"\\{ip}\SharedMeshDrive"

        # First, do a quick check without net use to avoid CMD windows
        # If the share is already accessible, skip the connection attempt
        wf_sub = (o.get("working_fuser_subdir") or "WorkingFuser").strip() or "WorkingFuser"
        wf_unc = os.path.join(unc_root, wf_sub).replace("/", "\\")
        
        if quick_unc_check(wf_unc, timeout=1):
            # Already accessible, no need to connect
            logging.info(f"[autoconnect] Share already accessible: {wf_unc}")
            update_fuser_shared_path(wf_unc)
            return True

        # User can manually connect via Settings → Test Access if needed
        logging.info(f"[autoconnect] Share not immediately accessible, skipping (on-demand connection)")
        return False
        
    except Exception as e:
        logging.info(f"[autoconnect] failed: {e}")
        return False

def _run(cmd, **kw):
    """Run a command with memory safety; return (rc, stdout, stderr). No console windows."""
    try:
        # Prepare STARTUPINFO to hide console window
        si = None
        if sys.platform == 'win32' and 'startupinfo' not in kw:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE
        
        # Add memory optimizations
        optimized_kw = {
            'capture_output': True,
            'text': True,
            'timeout': 30,  # Prevent hanging
            'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == 'win32' else 0,
            'startupinfo': si,
            **kw
        }

        gc.collect()
        cp = subprocess.run(cmd, **optimized_kw)
        return cp.returncode, (cp.stdout or ""), (cp.stderr or "")
        
    except subprocess.TimeoutExpired:
        logging.warning(f"[_run] Command timed out: {cmd}")
        return 1, "", "Command timed out"
    except OSError as e:
        if "not enough memory" in str(e).lower() or "resource" in str(e).lower():
            logging.error(f"[_run] Memory/resource error for command {cmd}: {e}")
            for _ in range(3):
                gc.collect()
            try:
                basic_kw = {
                    'capture_output': True, 
                    'text': True, 
                    'timeout': 10,
                    'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == 'win32' else 0
                }
                cp = subprocess.run(cmd, **basic_kw)
                return cp.returncode, (cp.stdout or ""), (cp.stderr or "")
            except Exception as retry_err:
                logging.error(f"[_run] Retry also failed for command {cmd}: {retry_err}")
                return 1, "", f"Memory/resource error: {e}"
        else:
            logging.error(f"[_run] OS error for command {cmd}: {e}")
            return 1, "", str(e)
    except Exception as e:
        logging.error(f"[_run] Unexpected error for command {cmd}: {e}")
        return 1, "", str(e)

def _try_net_use_unc_throttled(unc_root: str, timeout: float = 8.0) -> bool:
    """
    Throttled 'net use' attach. Handles 1219 (credential collision) once.
    Returns True when the session is usable.
    """
    global _NET_USE_LAST_TS
    now = time.monotonic()
    gap = now - _NET_USE_LAST_TS
    if gap < _NET_USE_MIN_GAP:
        time.sleep(_NET_USE_MIN_GAP - gap)

    rc, out, err = _run(["net", "use", unc_root, "/persistent:yes"], timeout=timeout)
    _NET_USE_LAST_TS = time.monotonic()
    txt = (out + err).lower()

    if rc == 0 or "already exists" in txt:
        logging.info(f"[net_use] Session OK for {unc_root}")
        return True

    # 1219: multiple connections with different creds → clear and retry once
    if "1219" in txt or "multiple connections" in txt:
        logging.warning(f"[net_use] Error 1219 detected, clearing connections for {unc_root}")
        host = unc_root.split("\\")[2] if unc_root.startswith("\\\\") and len(unc_root.split("\\")) > 2 else ""
        _run(["net", "use", unc_root, "/delete", "/y"], timeout=5)
        if host:
            _run(["net", "use", f"\\\\{host}\\IPC$", "/delete", "/y"], timeout=5)
            _run(["cmdkey", f"/delete:{host}"], timeout=5)
        rc2, out2, err2 = _run(["net", "use", unc_root, "/persistent:yes"], timeout=timeout)
        result = rc2 == 0 or "already exists" in (out2 + err2).lower()
        if result:
            logging.info(f"[net_use] Session OK after retry for {unc_root}")
        else:
            logging.error(f"[net_use] Failed after retry: {out2} {err2}")
        return result

    logging.warning(f"[net_use] Failed for {unc_root}: {txt}")
    return False

def ensure_unc_session_once(unc_root: str, *, first_timeout=6.0) -> bool:
    """
    Ensure a UNC session exists in THIS process token.
    Caches success for _UNC_SESS_COOLDOWN seconds.
    """
    if not unc_root or not unc_root.startswith("\\\\"):
        return False

    with _UNC_SESS_LOCK:
        info = _UNC_SESS_CACHE.get(unc_root)
        if info and (time.monotonic() - info["ts"]) < _UNC_SESS_COOLDOWN and info["ok"]:
            logging.debug(f"[unc_session] Using cached session for {unc_root}")
            return True

        # First check: allow a bit more time on a cold connect
        if quick_unc_check(unc_root, timeout=first_timeout):
            logging.info(f"[unc_session] Quick check passed for {unc_root}")
            _UNC_SESS_CACHE[unc_root] = {"ok": True, "ts": time.monotonic()}
            return True
        logging.info(f"[unc_session] Attempting throttled net use for {unc_root}")
        ok = _try_net_use_unc_throttled(unc_root, timeout=first_timeout)
        if not ok:
            time.sleep(0.6)
            ok = quick_unc_check(unc_root, timeout=3)
            if ok:
                logging.info(f"[unc_session] Recheck passed for {unc_root}")

        _UNC_SESS_CACHE[unc_root] = {"ok": ok, "ts": time.monotonic()}
        return ok

# Backward compatibility wrapper
def _try_net_use_unc(unc_root, username=None, password=None):
    """
    Legacy wrapper for compatibility. New code should use ensure_unc_session_once().
    """
    if username or password:
        logging.warning("[net_use] Credentials not supported in throttled mode, ignoring")
    return _try_net_use_unc_throttled(unc_root)

def _store_creds_in_cmdkey(host, username, password):
    """Persist credentials for SMB to avoid re-prompt on next boot.
    
    Stores credentials for BOTH IP and hostname (if resolvable) to ensure
    elevated and non-elevated contexts can both access the share.
    This fixes the split-token issue where Explorer works but elevated Toolkit doesn't.
    """
    try:
        # Store for the provided host (IP or name)
        _run(["cmdkey", f"/delete:{host}"], timeout=3)
        rc, stdout, stderr = _run(["cmdkey", f"/add:{host}", f"/user:{username}", f"/pass:{password}"], timeout=5)
        logging.info(f"[cmdkey] Stored credentials for {username}@{host}, return code: {rc}")
        if stderr:
            logging.warning(f"[cmdkey] Stderr: {stderr}")
        
        # Also store for the opposite (hostname if given IP, or IP if given hostname)
        try:
            import socket
            # If host is an IP, try to get hostname
            if host.replace('.', '').isdigit():  # Simple IP check
                try:
                    hostname = socket.gethostbyaddr(host)[0]
                    if hostname and hostname != host:
                        _run(["cmdkey", f"/delete:{hostname}"], timeout=3)
                        rc2, _, _ = _run(["cmdkey", f"/add:{hostname}", f"/user:{username}", f"/pass:{password}"], timeout=5)
                        logging.info(f"[cmdkey] Also stored credentials for hostname: {username}@{hostname}, rc={rc2}")
                except Exception:
                    pass
            # If host is a name, try to get IP
            else:
                try:
                    ip = socket.gethostbyname(host)
                    if ip and ip != host:
                        _run(["cmdkey", f"/delete:{ip}"], timeout=3)
                        rc3, _, _ = _run(["cmdkey", f"/add:{ip}", f"/user:{username}", f"/pass:{password}"], timeout=5)
                        logging.info(f"[cmdkey] Also stored credentials for IP: {username}@{ip}, rc={rc3}")
                except Exception:
                    pass
        except Exception as e:
            logging.debug(f"[cmdkey] Could not resolve alternate host form: {e}")
            
    except Exception as e:
        logging.error(f"[cmdkey] Exception storing credentials: {e}")

def _test_network_connectivity(host):
    """Test basic network connectivity to a host."""
    try:
        # Try to ping the host
        rc, stdout, stderr = _run(["ping", "-n", "1", "-w", "3000", host])
        if rc == 0:
            logging.info(f"[ping] Host {host} is reachable")
            return True
        else:
            logging.warning(f"[ping] Host {host} is not reachable: {stderr}")
            return False
    except Exception as e:
        logging.error(f"[ping] Exception testing connectivity to {host}: {e}")
        return False

def debug_network_connection(unc_path):
    """Debug helper to test network connectivity and UNC access."""
    if not unc_path or not unc_path.startswith("\\\\"):
        print(f"Invalid UNC path: {unc_path}")
        return
    parts = unc_path.split("\\")
    if len(parts) < 4:
        print(f"Invalid UNC format: {unc_path}")
        return
    
    host = parts[2]
    share = parts[3]
    unc_root = f"\\\\{host}\\{share}"
    
    print(f"Testing connection to: {unc_path}")
    print(f"Host: {host}")
    print(f"Share: {share}")
    print(f"UNC Root: {unc_root}")
    print()
    
    # Test 1: Ping connectivity
    print("1. Testing ping connectivity...")
    if _test_network_connectivity(host):
        print("   ✓ Host is reachable")
    else:
        print("   ✗ Host is not reachable")
        return
    
    # Test 2: Check if UNC is already accessible
    print("2. Testing UNC accessibility...")
    if can_access_unc(unc_root):
        print("   ✓ UNC is accessible")
        return
    else:
        print("   ✗ UNC is not accessible")
    
    # Test 3: Try net use without credentials
    print("3. Testing net use without credentials...")
    if _try_net_use_unc(unc_root):
        print("   ✓ Connected without credentials")
        if can_access_unc(unc_root):
            print("   ✓ UNC is now accessible")
        else:
            print("   ✗ Connected but UNC still not accessible")
    else:
        print("   ✗ Cannot connect without credentials")
        print("   → You may need to provide username and password")

def clear_offline_ip_configuration():
    """Clear the offline IP configuration to stop automatic connection attempts."""
    try:
        global config
        
        # Clear the offline host IP
        if "Offline" in config:
            if "host_ip" in config["Offline"]:
                old_ip = config["Offline"]["host_ip"]
                config["Offline"]["host_ip"] = ""
                logging.info(f"[clear_offline] Cleared host IP: {old_ip}")
            
            # Also clear other related offline settings
            if "host_name" in config["Offline"]:
                config["Offline"]["host_name"] = ""
                logging.info(f"[clear_offline] Cleared host name")
        
        # Clear network host as well
        if "Network" in config:
            if "host" in config["Network"]:
                config["Network"]["host"] = ""
                logging.info(f"[clear_offline] Cleared network host")
        
        # Clear fuser shared path
        if "Fusers" in config:
            if "shared_working_unc" in config["Fusers"]:
                config["Fusers"]["shared_working_unc"] = ""
                logging.info(f"[clear_offline] Cleared fuser shared UNC")
            if "working_folder_host" in config["Fusers"]:
                config["Fusers"]["working_folder_host"] = ""
                logging.info(f"[clear_offline] Cleared fuser working folder host")
        
        # Save the configuration
        save_config()
        logging.info("[clear_offline] Configuration cleared and saved")
        return True
        
    except Exception as e:
        logging.error(f"[clear_offline] Failed to clear configuration: {e}")
        return False

def validate_and_configure_network_connection(host_ip: str = None) -> bool:
    """
    Validate network connection to host and configure client properly.
    Returns True if connection is successful and configured.
    """
    try:
        if not host_ip:
            # Try to get from current config
            o = get_offline_cfg()
            host_ip = o.get("host_ip", "").strip()
            
        if not host_ip:
            logging.error("[network_config] No host IP provided or configured")
            return False
            
        # Test basic connectivity
        unc_root = f"\\\\{host_ip}\\SharedMeshDrive"
        if not quick_unc_check(unc_root):
            # Try to establish connection
            if not connect_working_share_interactive(parent=None, silent=True):
                logging.error(f"[network_config] Cannot connect to {unc_root}")
                return False
                
        # Test WorkingFolder specifically
        working_folder = f"\\\\{host_ip}\\SharedMeshDrive\\WorkingFuser"
        if not quick_unc_check(working_folder):
            logging.error(f"[network_config] WorkingFolder not accessible: {working_folder}")
            return False
            
        # Configure for network use
        config.setdefault("Offline", {})
        config["Offline"]["enabled"] = "True"
        config["Offline"]["host_ip"] = host_ip
        config["Offline"]["share_name"] = "SharedMeshDrive"
        config["Offline"]["working_fuser_subdir"] = "WorkingFuser"
        config["Offline"]["use_ip_unc"] = "True"
        config.setdefault("Network", {})
        config["Network"]["host"] = host_ip
        
        # Update fuser configuration
        config.setdefault("Fusers", {})
        config["Fusers"]["shared_working_unc"] = working_folder
        config["Fusers"]["working_folder_host"] = host_ip
        save_config()
        update_fuser_shared_path()
        logging.info(f"[network_config] Successfully configured for host {host_ip}")
        return True 
    except Exception as e:
        logging.error(f"[network_config] Configuration failed: {e}")
        return False

def optimize_memory():
    """Optimize memory usage by running garbage collection and clearing caches."""
    try:
        collected = gc.collect()
        if hasattr(sys, '_clear_type_cache'):
            sys._clear_type_cache()
            
        if hasattr(sys.modules, 'clear'):
            pass
        
        logging.info(f"[memory] Garbage collection freed {collected} objects")
        return collected
        
    except Exception as e:
        logging.error(f"[memory] Failed to optimize memory: {e}")
        return 0

def get_memory_usage():
    """Get current memory usage information."""
    try:
        if sys.platform == 'win32':
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            return {
                'rss': memory_info.rss,  # Resident Set Size
                'vms': memory_info.vms,  # Virtual Memory Size
                'percent': process.memory_percent(),
                'available': psutil.virtual_memory().available
            }
    except ImportError:
        # Fallback if psutil not available
        try:
            import tracemalloc
            if tracemalloc.is_tracing():
                current, peak = tracemalloc.get_traced_memory()
                return {
                    'current': current,
                    'peak': peak,
                    'tracing': True
                }
        except:
            pass
    except:
        pass
    
    return {'error': 'Memory info not available'}

def start_memory_monitoring():
    """Start memory monitoring if available."""
    try:
        import tracemalloc
        if not tracemalloc.is_tracing():
            tracemalloc.start()
            logging.info("[memory] Memory monitoring started")
    except ImportError:
        logging.info("[memory] tracemalloc not available, memory monitoring disabled")
    except Exception as e:
        logging.warning(f"[memory] Failed to start memory monitoring: {e}")

def periodic_memory_cleanup():
    """Periodic memory cleanup function to be called during app runtime."""
    try:
        collected = gc.collect()       
        # Log memory
        memory_info = get_memory_usage()
        if 'percent' in memory_info:
            percent = memory_info['percent']
            if percent > 80:  # If using more than 80% of system memory
                logging.warning(f"[memory] High memory usage: {percent:.1f}%")
                for _ in range(3):
                    gc.collect()       
        if collected > 0:
            logging.debug(f"[memory] Periodic cleanup freed {collected} objects")
            
    except Exception as e:
        logging.error(f"[memory] Periodic cleanup failed: {e}")

def check_network_share_status():
    """
    Check if the configured network share is accessible.
    Returns tuple: (status_code: str, status_message: str, color: str)
    
    Status codes:
    - 'connected': Share is fully accessible
    - 'checking': Currently verifying connection
    - 'local': Host PC using local path
    - 'disconnected': Share not accessible
    - 'unconfigured': No share configured
    - 'error': Error during check
    
    Uses aggressive timeouts (1s quick check, 2s fallback) to rapidly detect
    drive disconnection events like USB unplugging.
    """
    try:
        unc_path = resolve_shared_access_path()
        if not unc_path:
            return 'unconfigured', "● No network path configured", "#FFA500"  # Orange
        
        # If it's a local path (Host PC), just check if it exists
        if not unc_path.startswith("\\\\"):
            if os.path.exists(unc_path):
                return 'local', f"● Local: {os.path.basename(unc_path)}", "#00BFFF"  # Sky blue
            else:
                return 'error', f"● Local path missing: {os.path.basename(unc_path)}", "#FF4500"  # Orange-red
        
        # Quick check first (fast path) - aggressive 1 second timeout for fast disconnect detection
        if quick_unc_check(unc_path, timeout=1):
            # Extract just the share name for cleaner display
            share_name = unc_path.split('\\')[3] if len(unc_path.split('\\')) > 3 else unc_path
            return 'connected', f"● Connected: {share_name}", "#00FF00"  # Green
        
        # Fallback: slower filesystem check with 2 second timeout
        try:
            result_queue = Queue()
            def _check_exists():
                try:
                    result_queue.put(os.path.exists(unc_path))
                except:
                    result_queue.put(False)
            
            t = threading.Thread(target=_check_exists, daemon=True)
            t.start()
            t.join(2.0)  # 2 second timeout for fallback check
            
            if not result_queue.empty() and result_queue.get_nowait():
                share_name = unc_path.split('\\')[3] if len(unc_path.split('\\')) > 3 else unc_path
                return 'connected', f"● Connected: {share_name}", "#00FF00"  # Green
        except:
            pass
        
        # Not accessible - drive may be disconnected/unplugged
        host_ip = config.get("Offline", "host_ip", fallback="").strip()
        share_name = config.get("Offline", "share_name", fallback="").strip()
        if host_ip and share_name:
            return 'disconnected', f"○ Disconnected from {host_ip}", "#FF0000"  # Red
        else:
            return 'unconfigured', "○ Share not configured", "#FFA500"  # Orange
            
    except Exception as e:
        logging.error(f"[share-status] Error checking share: {e}")
        return 'error', f"● Error: {str(e)[:30]}", "#FF4500"  # Orange-red

def _compute_working_unc_from_cfg():
    """
    Build the WorkingFuser UNC using the live Offline config.
    Returns (unc_root, working_unc) or ('','') if not available.
    """
    o = get_offline_cfg()
    root = build_unc_from_cfg(o)  # \\10.0.0.5\SharedMeshDrive
    if not root:
        return "", ""
    wf_sub = (o.get("working_fuser_subdir") or "WorkingFuser").strip() or "WorkingFuser"
    working = os.path.join(root, wf_sub).replace("/", "\\")
    return root, working

def connect_working_share_interactive(parent=None, silent=True):
    """
    Auto-connect to the configured WorkingFuser UNC without ever prompting
    for credentials. Uses the current Windows session or cached credentials.
    Uses the new SMB session cache to prevent ERROR 1219 collisions.
    Returns True if the working UNC is accessible.
    """
    unc_root, working_unc = _compute_working_unc_from_cfg()
    if not unc_root:
        logging.warning("[connect] No UNC root configured")
        return False

    # Already accessible?
    if quick_unc_check(working_unc, timeout=2):
        logging.info(f"[connect] Already accessible: {working_unc}")
        return True

    # Use the new cached session manager
    logging.info(f"[connect] Attempting to establish session for {unc_root}")
    if ensure_smb_session_cached(unc_root):
        # Verify the working folder is accessible
        if quick_unc_check(working_unc, timeout=2):
            logging.info(f"[connect] Successfully connected to {working_unc}")
            return True
        else:
            logging.warning(f"[connect] Session established but {working_unc} not accessible")
            return False

    # If still failing, check if we need credentials
    try:
        cfg = get_offline_cfg()
        username = cfg.get("username", "").strip()
        password = cfg.get("password", "").strip()
        
        if username:
            logging.info(f"[connect] Retrying with configured credentials for user: {username}")
            if ensure_smb_session_cached(unc_root, username=username, password=password):
                if quick_unc_check(working_unc, timeout=2):
                    logging.info(f"[connect] Successfully connected with credentials to {working_unc}")
                    return True
    except Exception as e:
        logging.error(f"[connect] Error trying credential fallback: {e}")
    logging.error(f"[connect] Failed to connect to {working_unc}")
    return False

def _unc_usable(unc_root: str) -> bool:
    """Tolerant UNC availability check.
    Accepts cases where Windows has a session but Python's os.path may lag.
    Never prompts; treats success of dir or net use as usable.
    """
    try:
        if not unc_root or not unc_root.startswith("\\\\"):
            return False
        # Fast-path if filesystem already sees it
        if os.path.exists(unc_root):
            return True
        # Try a quick directory listing without opening Explorer/UI
        rc, _out, _err = _run(["cmd", "/c", "dir", unc_root], timeout=5)
        if rc == 0:
            return True
        if _try_net_use_unc(unc_root):
            time.sleep(0.6)
            return True
    except Exception:
        pass
    return False

# =============================================================================
# PRESENCE HEARTBEAT (Connected Fuser PCs tracking)
# =============================================================================

HEARTBEAT_DIR_NAME = "_clients"
HEARTBEAT_TTL_SECS = 90
_HB_STOP = threading.Event()
_HB_THREAD = None

def _machine_ip_fast() -> str:
    """Get machine IP quickly without blocking."""
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return ""

def _working_clients_dir() -> str:
    """Return path to _clients dir in WorkingFuser, or '' if not available.
    On host, normalizes UNC to local path so heartbeats can be written without loopback session."""
    try:
        wf = working_fuser_unc()
    except Exception:
        wf = ""
    if not wf:
        return ""
    try:
        wf = unc_to_local_if_host(wf)
    except Exception:
        pass
    
    # Build clients directory path
    clients_dir = os.path.join(wf, HEARTBEAT_DIR_NAME).replace("/", "\\")
    
    # Ensure directory exists
    try:
        os.makedirs(clients_dir, exist_ok=True)
    except Exception:
        pass
    
    return clients_dir

def _heartbeat_path_for_this_pc() -> str:
    """Return path to this PC's heartbeat JSON file."""
    root = _working_clients_dir()
    if not root:
        return ""
    
    # For UNC paths, check connectivity; for local paths (on host), just verify existence
    if root.startswith("\\\\"):
        try:
            if not quick_unc_check(root, timeout=1):
                return ""
        except Exception:
            return ""
    else:
        # Local path - ensure directory exists
        try:
            os.makedirs(root, exist_ok=True)
        except Exception:
            return ""
    
    name = f"{platform.node()}({_machine_ip_fast()})"
    return os.path.join(root, f"{name}.json")

def _atomic_write_json(path: str, data: dict) -> None:
    """Atomically write JSON to path (best effort)."""
    try:
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(tmp, path)
    except Exception:
        pass

def write_presence_heartbeat() -> None:
    """Write/update our presence file on the WorkingFuser share."""
    p = _heartbeat_path_for_this_pc()
    if not p:
        logging.warning("[presence] Cannot write heartbeat: empty path")
        return
    
    # Diagnostic logging
    clients_dir = _working_clients_dir()
    logging.debug(f"[presence] clients_dir={clients_dir} exists={os.path.isdir(clients_dir) if clients_dir else False}")
    logging.debug(f"[presence] heartbeat_path={p}")
    
    payload = {
        "pc": platform.node(),
        "ip": _machine_ip_fast(),
        "pid": os.getpid(),
        "ts": int(time.time()),
        "fusers": count_local_fusers(),
    }
    _atomic_write_json(p, payload)
    logging.debug(f"[presence] Heartbeat written successfully to {p}")

def cleanup_stale_presence() -> None:
    """Delete very old heartbeats (> 24h) to keep the folder tidy."""
    root = _working_clients_dir()
    if not root:
        return
    try:
        if not quick_unc_check(root, timeout=1):
            return
    except Exception:
        return
    now = time.time()
    for fp in glob.glob(os.path.join(root, "*.json")):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                d = json.load(f)
            if now - float(d.get("ts", 0)) > (24 * 3600):
                os.remove(fp)
        except Exception:
            pass

def scan_connected_fuser_pcs(active_only: bool = True) -> list[dict]:
    """Return list of active PCs by scanning fuser folders created by Fuser.exe.
    
    PhotoMesh Fuser.exe creates folders directly in WorkingFuser root with naming pattern:
    <PCNAME>(<IP>)_<FuserName> (e.g., HAMMERKIT1-4(192.168.10.243)_SeedFuser)
    
    We scan the WorkingFuser root directory for these folders and extract unique PC names.
    """
    # Get WorkingFuser root
    try:
        root = working_fuser_unc()
    except Exception:
        root = ""
    
    if not root:
        logging.debug("[presence] scan: no WorkingFuser root available")
        return []
    
    # Convert to local path if we're on the Host PC
    root = unc_to_local_if_host(root)
    logging.debug(f"[presence] scan: checking WorkingFuser root={root}")
    
    # For UNC paths, check connectivity before accessing; for local paths, just check existence
    if root.startswith("\\\\"):
        try:
            if not quick_unc_check(root, timeout=1):
                logging.debug(f"[presence] scan: UNC check failed for {root}")
                return []
        except Exception:
            logging.debug(f"[presence] scan: UNC check exception for {root}")
            return []
    else:
        # Local path - just verify it exists
        if not os.path.exists(root):
            logging.debug(f"[presence] scan: local path doesn't exist: {root}")
            return []
    
    # Scan for fuser folders created by Fuser.exe in the WorkingFuser root
    # Pattern: PCNAME(IP)_FuserName or KeepAlive_PCNAME(IP)_FuserName
    out = []
    pc_fusers = {}  # Track fusers per PC: {pc_name: count}
    
    try:
        for item in os.listdir(root):
            item_path = os.path.join(root, item)
            
            # Check both folders (KeepAlive heartbeats)
            if os.path.isdir(item_path) or item.endswith('.json'):
                if item == '_clients' or item == HEARTBEAT_DIR_NAME:
                    continue
                
                # Skip SeedFuser directories - they are not real fusers
                if 'SeedFuser' in item or 'seedfuser' in item.lower():
                    logging.debug(f"[presence] scan: skipping SeedFuser: {item}")
                    continue
                
                # Extract PC name and IP from folder/file name
                # Patterns: 
                #   PCNAME(IP)_FuserName
                #   KeepAlive_PCNAME(IP)_FuserName.json
                #   PCNAME(IP).json
                name = item.replace('KeepAlive_', '').replace('.json', '')
                
                # Extract PC name (everything before the first parenthesis)
                if '(' in name and ')' in name:
                    pc_name = name.split('(')[0]
                    # Extract IP
                    ip_part = name.split('(')[1].split(')')[0]
                    
                    # Only count LocalFuser1, LocalFuser2, LocalFuser3 folders
                    # Skip if fuser name doesn't match LocalFuserN pattern
                    if '_' in name:
                        fuser_name = name.split('_', 1)[1] if '_' in name else ''
                        # Only count LocalFuser with numbers 1-3
                        if fuser_name.startswith('LocalFuser'):
                            try:
                                fuser_num = int(fuser_name.replace('LocalFuser', ''))
                                if fuser_num < 1 or fuser_num > 3:
                                    logging.debug(f"[presence] scan: skipping invalid fuser number: {item}")
                                    continue
                            except ValueError:
                                logging.debug(f"[presence] scan: skipping non-numeric fuser: {item}")
                                continue
                        else:
                            logging.debug(f"[presence] scan: skipping non-LocalFuser: {item}")
                            continue
                    
                    if pc_name not in pc_fusers:
                        pc_fusers[pc_name] = {"pc": pc_name, "ip": ip_part, "fusers": 0}
                    pc_fusers[pc_name]["fusers"] += 1
                    
                    logging.debug(f"[presence] scan: found valid fuser from {pc_name} ({ip_part}): {item}")
        
        out = list(pc_fusers.values())
        logging.debug(f"[presence] scan: found {len(out)} unique PCs with {sum(pc['fusers'] for pc in out)} total valid fusers")
        
    except Exception as e:
        logging.warning(f"[presence] scan: error scanning directory {root}: {e}")
    
    return out

def count_connected_fuser_pcs() -> int:
    """
    Return count of unique active fuser PCs (not individual fusers, but unique PC names).
    Includes ALL PCs running fusers (both Host and User PCs).
    """
    pc_names = list_connected_fuser_pc_names()
    
    logging.debug(f"[connected_pcs] Total unique PCs running fusers: {len(pc_names)}")
    logging.debug(f"[connected_pcs] PC names: {pc_names}")
    
    return len(pc_names)

def list_connected_fuser_pc_names() -> list[str]:
    """Return sorted list of unique PC names with active heartbeats."""
    return sorted({ (d.get("pc") or "unknown") for d in scan_connected_fuser_pcs(True) })

def get_connected_pcs_summary() -> dict:
    """
    Return summary of connected PCs with their fuser counts.
    Returns dict: {pc_name: {"ip": str, "fusers": int, "last_seen": float}}
    """
    all_heartbeats = scan_connected_fuser_pcs(True)
    summary = {}
    
    for hb in all_heartbeats:
        pc_name = hb.get("pc") or "unknown"
        if pc_name not in summary:
            summary[pc_name] = {
                "ip": hb.get("ip", "unknown"),
                "fusers": hb.get("fusers", 0),
                "last_seen": hb.get("ts", 0)
            }
        else:
            # Update with latest info (in case multiple heartbeats per PC)
            if hb.get("ts", 0) > summary[pc_name]["last_seen"]:
                summary[pc_name]["fusers"] = hb.get("fusers", 0)
                summary[pc_name]["last_seen"] = hb.get("ts", 0)
    
    return summary

def _presence_loop():
    """Background thread that writes heartbeat every ~20s."""
    while not _HB_STOP.is_set():
        try:
            write_presence_heartbeat()
            cleanup_stale_presence()
        except Exception:
            pass
        _HB_STOP.wait(20.0)

def start_presence_service():
    """Start the background heartbeat thread."""
    global _HB_THREAD
    if _HB_THREAD and _HB_THREAD.is_alive():
        return
    # Ensure stop flag is clear before starting
    try:
        _HB_STOP.clear()
    except Exception:
        pass
    _HB_THREAD = threading.Thread(target=_presence_loop, name="presence", daemon=True)
    _HB_THREAD.start()
    logging.info("[presence] Heartbeat service started")
    try:
        write_presence_heartbeat()
        logging.info("[presence] Initial heartbeat written")
    except Exception as e:
        logging.warning(f"[presence] Initial heartbeat write failed: {e}")

def stop_presence_service():
    """Stop heartbeat thread and cleanup our presence file."""
    try:
        _HB_STOP.set()
        global _HB_THREAD
        if _HB_THREAD and _HB_THREAD.is_alive():
            try:
                _HB_THREAD.join(timeout=2.0)
            except Exception:
                pass
        _HB_THREAD = None
        p = _heartbeat_path_for_this_pc()
        if p and os.path.isfile(p):
            os.remove(p)
            logging.info("[presence] Heartbeat file removed")
    except Exception:
        pass

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
    """Return True when TerraExplorer.exe is observed (windowless check)."""
    want = "terraexplorer.exe"
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            if psutil:
                # Best: psutil API (no console)
                for p in psutil.process_iter(["name"]):
                    if (p.info.get("name") or "").lower() == want:
                        log("[watch] TerraExplorer.exe detected")
                        return True
            else:
                # Fallback: hidden tasklist (no console window)
                result = run_hidden(["tasklist", "/FI", f"IMAGENAME eq {want}"], timeout=3)
                if result.returncode == 0 and result.stdout and want in result.stdout.lower():
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

def get_vbs4_install_path(*, time_budget_sec=0.9, allow_full_drive=False) -> str:
    """Return the best VBS4.exe path found on the system.

    Searches common installation roots, preferring the highest file version and
    using the newest modification time as a tiebreaker.  The discovered path is
    cached in ``config['General']['vbs4_path']`` and paths_cache.json.
    
    Args:
        time_budget_sec: Maximum time to spend searching (default 0.9s)
        allow_full_drive: Whether to search entire C:\\\\ drive as fallback
        
    Returns:
        Path to VBS4.exe or empty string if not found within budget
    """
    t0 = time.time()
    deadline = t0 + time_budget_sec
    
    # Check config first
    path = config['General'].get('vbs4_path', '').strip()
    if path and os.path.isfile(path):
        logging.info("VBS4 path found in config: %s", path)
        return path

    # Check cache
    cache = _load_paths_cache()
    cache_key = "vbs4_install_path"
    if cache_key in cache:
        cached_path = cache[cache_key]
        if cached_path and os.path.isfile(cached_path):
            logging.info("VBS4 path found in cache: %s", cached_path)
            # Update config from cache
            config['General']['vbs4_path'] = cached_path
            try:
                save_config()
            except Exception:
                logging.exception("Failed to write VBS4 path to config from cache")
            return cached_path

    # Build search roots with expanded VBS4 version paths
    roots = []
    
    # Add version-specific paths first (most likely to contain latest VBS4)
    builds_vbs4_base = r"C:\Builds\VBS4"
    if os.path.isdir(builds_vbs4_base):
        try:
            # Look for version-numbered subdirectories first
            version_folders = []
            for entry in os.listdir(builds_vbs4_base):
                entry_path = os.path.join(builds_vbs4_base, entry)
                if os.path.isdir(entry_path):
                    # Add version folders like "VBS4 25.1 YYMEA_General"
                    if "VBS4" in entry or "YYMEA" in entry or re.search(r'\d+\.\d+', entry):
                        version_folders.append(entry_path)
                        roots.append(entry_path)
            if version_folders:
                logging.info("[discover] Found %d VBS4 version folders in %s", len(version_folders), builds_vbs4_base)
        except (OSError, PermissionError) as e:
            logging.warning("[discover] Could not list %s: %s", builds_vbs4_base, e)
    
    # Add standard search roots
    roots.extend([
        r"C:\BISIM\VBS4",
        r"C:\Builds\VBS4",
        r"C:\Builds",
        r"C:\Bohemia Interactive Simulations",
    ])

    if allow_full_drive:
        roots.append(r"C:\\")

    best_path = ""
    best_key: tuple[int, tuple[int, ...], float] = (0, (), 0.0)

    for root in roots:
        if time.time() > deadline:
            logging.info("[discover] VBS4 budget exceeded; will index in background")
            return ""
            
        try:
            os.makedirs(root, exist_ok=True)
        except Exception:
            continue
        if not os.path.isdir(root):
            continue
            
        for dirpath, _dirnames, filenames in os.walk(root):
            if time.time() > deadline:
                logging.info("[discover] VBS4 budget exceeded during os.walk; will index in background")
                return ""
                
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
        # Save to both config and cache
        config['General']['vbs4_path'] = best_path
        cache[cache_key] = best_path
        _save_paths_cache(cache)
        
        try:
            save_config()
        except Exception:
            logging.exception("Failed to write VBS4 path to config")
            
        elapsed = time.time() - t0
        logging.info("[discover] VBS4 found: %s (took %.2fs, budget %.2fs)", best_path, elapsed, time_budget_sec)
        return best_path

    elapsed = time.time() - t0
    logging.info("[discover] VBS4 not found (took %.2fs, budget %.2fs)", elapsed, time_budget_sec)
    return ""

def get_vbs4_launcher_path(*, time_budget_sec=0.9, allow_full_drive=False) -> str:
    """
    Return the best path to the VBS4 launcher (VBSLauncher.exe or VBS4Launcher.exe).

    Strategy:
      1) Respect a valid path already saved in config.
      2) Check cache for previously discovered path.
      3) Prefer a launcher that sits next to the discovered VBS4.exe.
      4) Search common VBS roots for either filename.
      5) Only if allow_full_drive=True, scan C:\\\\ recursively for either filename.
      6) Among all candidates, prefer highest FileVersion then newest mtime.

    The chosen path is saved to config['General']['vbs4_setup_path'] and cache.
    
    Args:
        time_budget_sec: Maximum time to spend searching (default 0.9s)
        allow_full_drive: Whether to search entire C:\\\\ drive as fallback
        
    Returns:
        Path to VBS4 launcher or empty string if not found within budget
    """
    t0 = time.time()
    deadline = t0 + time_budget_sec

    def _save_and_return(p: str) -> str:
        if p:
            config['General']['vbs4_setup_path'] = os.path.normpath(p)
            cache = _load_paths_cache()
            cache["vbs4_launcher_path"] = p
            _save_paths_cache(cache)
            save_config()
            try:
                refresh_settings_panel_from_config()
            except Exception:
                pass
                
            elapsed = time.time() - t0
            logging.info("[discover] VBS4 Launcher found: %s (took %.2fs, budget %.2fs)", p, elapsed, time_budget_sec)
        return p
    cfg_path = config['General'].get('vbs4_setup_path', '').strip()
    if cfg_path and os.path.isfile(cfg_path):
        logging.info("VBS4 Launcher (from config): %s", cfg_path)
        return cfg_path

    cache = _load_paths_cache()
    cache_key = "vbs4_launcher_path"
    if cache_key in cache:
        cached_path = cache[cache_key]
        if cached_path and os.path.isfile(cached_path):
            logging.info("VBS4 Launcher (from cache): %s", cached_path)
            return _save_and_return(cached_path)

    launcher_names = ("VBSLauncher.exe", "VBS4Launcher.exe", "VBSLauncher.bat", "VBS4Launcher.bat")

    # 1) Prefer same folder as discovered VBS4.exe (with time budget)
    vbs4_exe = get_vbs4_install_path(time_budget_sec=min(0.3, time_budget_sec * 0.3), allow_full_drive=False)
    if vbs4_exe:
        base = os.path.dirname(vbs4_exe)
        for name in launcher_names:
            cand = os.path.join(base, name)
            if os.path.isfile(cand):
                logging.info("VBS4 Launcher (next to VBS4.exe): %s", cand)
                return _save_and_return(cand)

    if time.time() > deadline:
        logging.info("[discover] VBS4 Launcher budget exceeded after VBS4.exe check; will index in background")
        return ""

    # 2) Search common roots for either name
    # Build search roots with expanded VBS4 version paths
    roots = []
    
    # If we already found VBS4.exe, prioritize its directory
    if vbs4_exe:
        roots.append(os.path.dirname(vbs4_exe))
    
    # Add version-specific paths that may contain VBSLauncher.exe
    # These cover patterns like "C:\Builds\VBS4\VBS4 25.1 YYMEA_General"
    builds_vbs4_base = r"C:\Builds\VBS4"
    if os.path.isdir(builds_vbs4_base):
        try:
            # Look for version-numbered subdirectories first (most specific)
            version_folders = []
            for entry in os.listdir(builds_vbs4_base):
                entry_path = os.path.join(builds_vbs4_base, entry)
                if os.path.isdir(entry_path):
                    # Add version folders like "VBS4 25.1 YYMEA_General"
                    if "VBS4" in entry or "YYMEA" in entry or re.search(r'\d+\.\d+', entry):
                        version_folders.append(entry_path)
                        roots.append(entry_path)
            if version_folders:
                logging.info("[discover] Found %d VBS4 version folders in %s", len(version_folders), builds_vbs4_base)
        except (OSError, PermissionError) as e:
            logging.warning("[discover] Could not list %s: %s", builds_vbs4_base, e)
    
    # Add standard search roots
    roots.extend([
        r"C:\BISIM\VBS4",
        r"C:\Builds\VBS4",
        r"C:\Builds",
        r"C:\Bohemia Interactive Simulations",
        r"C:\Program Files\Bohemia Interactive Simulations",
    ])

    def _iter_candidates(search_roots, respect_deadline=True):
        seen = set()
        for root in search_roots:
            if respect_deadline and time.time() > deadline:
                logging.info("[discover] VBS4 Launcher budget exceeded during iteration; will index in background")
                return
                
            if not os.path.isdir(root):
                continue
            for dirpath, _dirs, files in os.walk(root):
                if respect_deadline and time.time() > deadline:
                    logging.info("[discover] VBS4 Launcher budget exceeded during os.walk; will index in background")
                    return
                    
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
    candidates = list(_iter_candidates(roots, respect_deadline=True))
    if time.time() > deadline:
        elapsed = time.time() - t0
        logging.info("[discover] VBS4 Launcher budget exceeded (took %.2fs, budget %.2fs)", elapsed, time_budget_sec)
        return ""
        
    candidates = sorted(candidates, key=_rank, reverse=True)
    if candidates:
        logging.info("VBS4 Launcher (common roots): %s", candidates[0])
        return _save_and_return(candidates[0])

    # 3) Last resort: walk the entire C:\ drive 
    if allow_full_drive and time.time() <= deadline:
        candidates = list(_iter_candidates([r"C:\\" ], respect_deadline=True))
        if time.time() <= deadline:
            candidates = sorted(candidates, key=_rank, reverse=True)
            if candidates:
                logging.info("VBS4 Launcher (C:\\\\ scan): %s", candidates[0])
                return _save_and_return(candidates[0])

    elapsed = time.time() - t0
    logging.info("[discover] VBS4 Launcher not found (took %.2fs, budget %.2fs)", elapsed, time_budget_sec)
    return ''

def get_blueig_install_path() -> str:
    path = config['General'].get('blueig_path', '')
    if not path or not os.path.isfile(path):
        path = find_executable('BlueIG.exe', time_budget_sec=0.5, allow_full_drive=False)
        if path:
            config['General']['blueig_path'] = path
            save_config()
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
    found = find_executable("ares.manager.exe", additional_paths=candidates, time_budget_sec=0.5, allow_full_drive=False)
    if not found:
        found = find_executable("ARES.Manager.exe", additional_paths=candidates, time_budget_sec=0.5, allow_full_drive=False)

    if found:
        config['General']['bvi_manager_path'] = clean_path(found)
        save_config()
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

def find_executable(name, additional_paths=[], *, time_budget_sec=0.9, allow_full_drive=False, full_drive_root="C:\\"):
    """
    Try to find either ``name`` (e.g. ``VBS4.exe``) or its ``.bat`` sibling
    (e.g. ``VBS4.bat``) under standard paths or any ``additional_paths``.
    If multiple matching files are found, the newest one (by modification time)
    is returned.
    
    Args:
        name: Executable name to find
        additional_paths: Additional directories to search
        time_budget_sec: Maximum time to spend searching (default 0.9s)
        allow_full_drive: Whether to fall back to full drive scan if not found in known paths
        full_drive_root: Root drive to scan if allow_full_drive is True
        
    Returns:
        Best path found or empty string if not found within budget
    """
    t0 = time.time()
    deadline = t0 + time_budget_sec
    
    base, ext = os.path.splitext(name)
    # build list of filenames
    candidates = [name]
    if ext.lower() == '.exe':
        candidates.append(base + '.bat')
    elif ext.lower() == '.bat':
        candidates.append(base + '.exe')

    # Check cache first
    cache = _load_paths_cache()
    cache_key = f"find_executable:{name}"
    if cache_key in cache:
        cached_path = cache[cache_key]
        if cached_path and os.path.isfile(cached_path):
            logging.info("[discover] %s found in cache: %s", name, cached_path)
            return cached_path

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
        if time.time() > deadline:
            logging.info("[discover] %s budget exceeded in exact path search; will index in background", name)
            return ""
            
        for cand in candidates:
            full_path = os.path.join(path, cand)
            if os.path.isfile(full_path):
                mtime = os.path.getmtime(full_path)
                if mtime > best_mtime:
                    best_mtime = mtime
                    best_path = os.path.normpath(full_path)

    # If not found, search subdirectories in known paths
    if not best_path:
        for path in possible_paths:
            if time.time() > deadline:
                logging.info("[discover] %s budget exceeded in subdirectory search; will index in background", name)
                return ""
                
            if os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    if time.time() > deadline:
                        logging.info("[discover] %s budget exceeded during os.walk; will index in background", name)
                        return ""
                        
                    for cand in candidates:
                        if cand in files:
                            full_path = os.path.join(root, cand)
                            mtime = os.path.getmtime(full_path)
                            if mtime > best_mtime:
                                best_mtime = mtime
                                best_path = os.path.normpath(full_path)

    # Last resort: full drive scan
    if not best_path and allow_full_drive and os.path.isdir(full_drive_root):
        if time.time() > deadline:
            logging.info("[discover] %s budget exceeded before full drive scan; will index in background", name)
            return ""
            
        logging.info("[discover] %s scanning full drive %s (this may take time)", name, full_drive_root)
        for root, dirs, files in os.walk(full_drive_root):
            if time.time() > deadline:
                logging.info("[discover] %s budget exceeded during full drive scan; will index in background", name)
                return ""
                
            for cand in candidates:
                if cand in files:
                    full_path = os.path.join(root, cand)
                    mtime = os.path.getmtime(full_path)
                    if mtime > best_mtime:
                        best_mtime = mtime
                        best_path = os.path.normpath(full_path)

    # Cache and return result
    if best_path:
        cache[cache_key] = best_path
        _save_paths_cache(cache)
        elapsed = time.time() - t0
        logging.info("[discover] %s found: %s (took %.2fs, budget %.2fs)", name, best_path, elapsed, time_budget_sec)
    else:
        elapsed = time.time() - t0
        logging.info("[discover] %s not found (took %.2fs, budget %.2fs)", name, elapsed, time_budget_sec)

    return best_path or ""

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
            save_config()
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
    save_config()

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

def find_local_rm_link() -> str: 
    return find_local_rm_shortcut(get_rm_local_root())

def is_valid_rm_root(local_root: str, data_marker: str = RM_LNK_NAME) -> bool: 
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

# --- Config path resolution (single source of truth) ---
def _site_dir() -> str:
    """Return the directory where the app should store its config."""
    return os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) \
           else os.path.abspath(os.path.dirname(__file__))

BASE_DIR = _site_dir()

def _get_bundled_resource_dir():
    """Get the directory where bundled resources are located.
    
    When frozen (PyInstaller): sys._MEIPASS (temporary extraction directory)
    When not frozen: same directory as this script
    """
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.abspath(os.path.dirname(__file__))

# Use bundled resource directory for UI assets and bundled files
_BUNDLE_DIR = _get_bundled_resource_dir()

# Image cache for UI performance optimization
# Caches resized images to avoid repeated PIL operations
_IMAGE_CACHE = {}

DEFAULT_CONFIG_PATH = _resource_path('config.ini')          # bundled
SITE_CONFIG_PATH    = os.path.join(BASE_DIR, 'config.ini')  # next to EXE

def _arg_value(flag: str) -> str | None:
    """Get command line argument value for given flag."""
    try:
        i = sys.argv.index(flag)
        return sys.argv[i + 1]
    except Exception:
        return None

_cli_cfg = _arg_value('--config')
if _cli_cfg:
    CONFIG_PATH = os.path.abspath(_cli_cfg)                  # accept even if not yet created
else:
    CONFIG_PATH = SITE_CONFIG_PATH if os.path.exists(SITE_CONFIG_PATH) else DEFAULT_CONFIG_PATH

PATHS_CACHE = os.path.join(BASE_DIR, "paths_cache.json")
ICON_NAME   = 'icon.ico'
SPLASH_NAME = 'splash.png'

config = configparser.ConfigParser()
# Read bundled defaults then overlay site/explicit if present
if CONFIG_PATH == DEFAULT_CONFIG_PATH:
    config.read([DEFAULT_CONFIG_PATH, SITE_CONFIG_PATH], encoding='utf-8')
else:
    config.read([DEFAULT_CONFIG_PATH, CONFIG_PATH], encoding='utf-8')

# Share config with photomesh_launcher module to prevent conflicts
import photomesh_launcher
photomesh_launcher.config = config
photomesh_launcher.CONFIG_PATH = CONFIG_PATH
photomesh_launcher.BASE_DIR = BASE_DIR

# Initialize fuser defaults now that config is shared
photomesh_launcher._ensure_fuser_defaults()

# Run hostname to IP migration now that config is available
try:
    photomesh_launcher.migrate_hostname_to_ip_once()
except Exception as e:
    logging.warning(f"[migrate] hostname->ip skipped: {e}")

# Sync all IP references from the single source of truth ([Offline] host_ip)
def sync_host_ip_references():
    """
    Ensure all IP references in config are synced from [Offline] host_ip (single source of truth).
    This fixes configs where IP addresses got out of sync across different sections.
    """
    try:
        primary_ip = config.get("Offline", "host_ip", fallback="").strip()
        if not primary_ip:
            logging.info("[sync_ip] No primary host IP configured, skipping sync")
            return
        
        changed = False
        
        # Sync [Network] host
        if config.get("Network", "host", fallback="").strip() != primary_ip:
            if "Network" not in config:
                config["Network"] = {}
            config["Network"]["host"] = primary_ip
            changed = True
            logging.info(f"[sync_ip] Synced [Network] host to {primary_ip}")
        
        # Sync [Fusers] working_folder_host
        if config.get("Fusers", "working_folder_host", fallback="").strip() != primary_ip:
            if "Fusers" not in config:
                config["Fusers"] = {}
            config["Fusers"]["working_folder_host"] = primary_ip
            changed = True
            logging.info(f"[sync_ip] Synced [Fusers] working_folder_host to {primary_ip}")
        
        # Rebuild [Fusers] shared_working_unc from IP + share_name
        offline = config.get("Offline", "share_name", fallback="SharedMeshDrive").strip() or "SharedMeshDrive"
        wf_subdir = config.get("Offline", "working_fuser_subdir", fallback="WorkingFuser").strip() or "WorkingFuser"
        expected_unc = f"\\\\{primary_ip}\\{offline}\\{wf_subdir}"
        current_unc = config.get("Fusers", "shared_working_unc", fallback="").strip()
        if current_unc != expected_unc:
            config["Fusers"]["shared_working_unc"] = expected_unc
            changed = True
            logging.info(f"[sync_ip] Rebuilt [Fusers] shared_working_unc to {expected_unc}")
        
        if changed:
            save_config()
            logging.info("[sync_ip] Config IP references synced and saved")
        else:
            logging.info("[sync_ip] All IP references already in sync")
            
    except Exception as e:
        logging.warning(f"[sync_ip] Failed to sync IP references: {e}")

# Run IP sync at startup to fix any inconsistencies
try:
    sync_host_ip_references()
except Exception as e:
    logging.warning(f"[sync_ip] Startup sync failed: {e}")

# --- Config flags (global enforcement) ---
# Strict enforcement: refuse to launch fusers if shared working folder is not accessible
# This prevents User installations from creating local working folders
ENFORCE_SHARED_WORKING_ONLY = config.getboolean('Fusers', 'enforce_shared_only', fallback=True)

# Log config paths for diagnostics
try:
    log_dir = os.path.join(os.path.expandvars(r'%ProgramData%'), 'STE_Toolkit')
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, 'startup.log'), 'a', encoding='utf-8') as lf:
        lf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} CONFIG_PATH={CONFIG_PATH} SITE={SITE_CONFIG_PATH}\n")
except Exception:
    pass

# Parse CLI arguments for fast startup
FAST_START_CLI = "--fast-start" in sys.argv

# Global handle to the running MainApp instance so background helpers can
# synchronize UI state (e.g., refresh Settings fields after config updates).
APP_INSTANCE = None

def save_config() -> None:
    """Save to the active CONFIG_PATH (respects --config CLI override) with atomic write."""
    target = CONFIG_PATH
    
    # Fallback to site config if active path isn't writable
    if not os.path.dirname(target) or not os.access(os.path.dirname(target), os.W_OK):
        target = SITE_CONFIG_PATH
    
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        
        # Atomic write using temp file + rename
        tmp = target + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            config.write(f)
        os.replace(tmp, target)  # Atomic on both Windows and Unix
        
    except Exception as e:
        # Final fallback to site config
        if target != SITE_CONFIG_PATH:
            try:
                target = SITE_CONFIG_PATH
                os.makedirs(os.path.dirname(target), exist_ok=True)
                tmp = target + ".tmp"
                with open(tmp, 'w', encoding='utf-8') as f:
                    config.write(f)
                os.replace(tmp, target)
            except Exception as e2:
                print(f"[WARN] Unable to write config to '{target}': {e2}")
        else:
            print(f"[WARN] Unable to write config to '{target}': {e}")

def _save_config():
    """Legacy wrapper - use save_config() instead."""
    save_config()

def _load_paths_cache() -> dict:
    """Load the paths cache from JSON file."""
    try:
        with open(PATHS_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_paths_cache(d: dict) -> None:
    """Save the paths cache to JSON file."""
    try:
        with open(PATHS_CACHE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except Exception:
        logging.exception("paths_cache write failed")

def _ensure_fuser_defaults() -> None:
    """Legacy fuser defaults - basic config only."""
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
    # Track the last number of fusers launched for restoration on restart
    if "last_launched_count" not in fusers:
        fusers["last_launched_count"] = "0"
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
        ip = config.get("Offline", "host_ip", fallback="").strip()
        return ip
    except Exception as e:
        return ""

def set_host_ip(ip: str) -> None:
    """
    Persist *ip* to Offline.host_ip (single source of truth) and sync all dependent config values.
    
    This updates:
    - [Offline] host_ip (PRIMARY - single source of truth)
    - [Network] host (synced from Offline.host_ip)
    - [Fusers] working_folder_host (synced from Offline.host_ip)
    - [Fusers] shared_working_unc (rebuilt from Offline.host_ip + share_name)
    """
    trimmed = ip.strip()
    if "Offline" not in config:
        config["Offline"] = {}
    offline = config["Offline"]
    
    # PRIMARY: Set the single source of truth
    offline["host_ip"] = trimmed
    if trimmed:
        offline["use_ip_unc"] = "True"
    else:
        offline["use_ip_unc"] = offline.get("use_ip_unc", "True")
    
    # SYNC: Update all dependent config values to match
    if trimmed:
        # Sync [Network] host
        if "Network" not in config:
            config["Network"] = {}
        config["Network"]["host"] = trimmed
        
        # Sync [Fusers] working_folder_host
        if "Fusers" not in config:
            config["Fusers"] = {}
        config["Fusers"]["working_folder_host"] = trimmed
        
        # Rebuild [Fusers] shared_working_unc from IP + share_name
        share_name = offline.get("share_name", "SharedMeshDrive").strip() or "SharedMeshDrive"
        wf_subdir = offline.get("working_fuser_subdir", "WorkingFuser").strip() or "WorkingFuser"
        config["Fusers"]["shared_working_unc"] = f"\\\\{trimmed}\\{share_name}\\{wf_subdir}"
        
        logging.info(f"[set_host_ip] Updated host IP to {trimmed} (synced to Network.host, Fusers.working_folder_host, Fusers.shared_working_unc)")
    else:
        logging.info("[set_host_ip] Cleared host IP")
        
    save_config()

    apply_offline_settings()
    update_fuser_shared_path()
    
    # Try to establish the UNC session
    if trimmed:  # Only try to connect if an IP was actually set
        connect_working_share_interactive(parent=None, silent=True)

def build_unc_from_cfg(o: dict | None = None) -> str:
    """Return ``\\\\<ip>\\<share>`` based on Offline config (IP only)."""

    if o is None:
        o = get_offline_cfg()
    ip = (o.get("host_ip") or "").strip()
    share = (o.get("share_name") or "SharedMeshDrive").strip() or "SharedMeshDrive"
    if not ip:
        return ""
    return f"\\\\{ip}\\{share}"

def is_this_pc_the_real_host() -> bool:
    """
    Determine if this PC is the actual host by checking if the SharedMeshDrive share exists locally.
    
    This is more reliable than just comparing IPs, because:
    - Config might have stale/incorrect host IP
    - IP addresses can change
    - Only the true host will have the share folder as a local directory
    
    Returns:
        True if this PC has the SharedMeshDrive share configured locally
    """
    try:
        o = get_offline_cfg()
        share_name = (o.get("share_name") or "SharedMeshDrive").strip() or "SharedMeshDrive"
        
        # Query Windows for the share
        rc, out, err = _run(["net", "share", share_name], timeout=3.0)
        if rc == 0:
            # Parse output for the "Path" line
            for line in out.split('\n'):
                line_stripped = line.strip()
                if line_stripped.lower().startswith("path"):
                    parts_line = line.split(maxsplit=1)
                    if len(parts_line) >= 2:
                        local_path = parts_line[1].strip()
                        if os.path.exists(local_path):
                            logging.info(f"[host-detect] This PC IS the host - share '{share_name}' exists at {local_path}")
                            return True
        
        logging.info(f"[host-detect] This PC is NOT the host - share '{share_name}' not found locally")
        return False
    except Exception as e:
        logging.warning(f"[host-detect] Failed to check if host: {e}")
        return False

def unc_to_local_if_host(unc_path: str) -> str:
    r"""
    Convert UNC path to local path if we're on the Host PC.
    This prevents SMB loopback issues where a PC can't access its own shares via \\IP\share.
    
    Examples:
        \\192.168.10.243\SharedMeshDrive\WorkingFuser -> E:\SharedMeshDrive\WorkingFuser (if on host)
        \\192.168.10.243\SharedMeshDrive\WorkingFuser -> \\192.168.10.243\SharedMeshDrive\WorkingFuser (if not host)
    """
    if not unc_path or not unc_path.startswith("\\\\"):
        return unc_path
    
    # Check if this is pointing to the configured host IP
    o = get_offline_cfg()
    host_ip = (o.get("host_ip") or "").strip()
    
    if not host_ip:
        return unc_path
    
    # Check if UNC path starts with the host IP
    if not unc_path.lower().startswith(f"\\\\{host_ip.lower()}\\"):
        return unc_path
    
    # IMPROVED: Check if we ARE the host by verifying the share exists locally
    # Don't rely solely on IP matching - config might be stale
    if not is_this_pc_the_real_host():
        return unc_path  # We're not the host, use UNC
    
    # We ARE the host - convert to local path
    # Extract the share name and remaining path
    parts = unc_path.split("\\")
    if len(parts) < 4:
        return unc_path
    
    share_name = parts[3]  # SharedMeshDrive
    remaining_path = "\\".join(parts[4:]) if len(parts) > 4 else ""
    
    # Query Windows to find the actual local path for this share
    try:
        rc, out, err = _run(["net", "share", share_name], timeout=3.0)
        if rc == 0:
            # Parse the output for the "Path" line
            # Example output:
            # Share name   SharedMeshDrive
            # Path         E:\SharedMeshDrive
            # Remark
            for line in out.split('\n'):
                line_stripped = line.strip()
                if line_stripped.lower().startswith("path"):
                    # Split on whitespace, taking everything after "Path"
                    parts_line = line.split(maxsplit=1)
                    if len(parts_line) >= 2:
                        local_base = parts_line[1].strip()
                        if os.path.exists(local_base):
                            local_path = os.path.join(local_base, remaining_path) if remaining_path else local_base
                            logging.info(f"[unc_to_local] Converted {unc_path} -> {local_path} (Host PC via 'net share')")
                            return local_path
    except Exception as e:
        logging.warning(f"[unc_to_local] Failed to query share '{share_name}': {e}")
    
    # Fallback: Try to find the local path by checking common drive letters
    logging.info(f"[unc_to_local] 'net share' query failed, trying common drives")
    for drive in ["C:", "D:", "E:", "F:", "G:", "H:"]:
        local_share = f"{drive}\\{share_name}"
        if os.path.exists(local_share):
            local_path = os.path.join(local_share, remaining_path) if remaining_path else local_share
            logging.info(f"[unc_to_local] Converted {unc_path} -> {local_path} (Host PC via drive scan)")
            return local_path
    
    # If we can't find it, return the original UNC path
    logging.warning(f"[unc_to_local] Could not find local path for {unc_path}, using UNC (may fail due to loopback)")
    return unc_path

def resolve_shared_access_path() -> str:
    """Return the root UNC path for the shared mesh drive using the host IP."""

    unc = build_unc_from_cfg()
    # Convert to local path if we're on the Host PC
    if unc:
        unc = unc_to_local_if_host(unc)
    return unc or ""

def get_host() -> str:
    """
    Return the host identifier (IP preferred, fallback to hostname).
    Always reads from [Offline] host_ip as the single source of truth.
    """
    ip = get_host_ip()
    if ip:
        return ip
    # Fallback to hostname if no IP configured
    return config.get("Offline", "host_name", fallback="").strip()

def set_host(host: str) -> None:
    """
    DEPRECATED: Use set_host_ip() instead for IP addresses.
    This function is kept for backwards compatibility with legacy hostname-based configs.
    For IP addresses, call set_host_ip() which properly syncs all dependent config values.
    """
    host = host.strip()
    if not host:
        return

    # Check if this looks like an IP address
    import re
    if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', host):
        # It's an IP - delegate to set_host_ip() which handles all syncing
        logging.info(f"[set_host] Detected IP address, delegating to set_host_ip(): {host}")
        set_host_ip(host)
        return
    
    # It's a hostname - store in Offline.host_name only (legacy support)
    if "Offline" not in config:
        config["Offline"] = {}
    config["Offline"]["host_name"] = host
    logging.info(f"[set_host] Set hostname (not IP): {host}")
    
    save_config()
    refresh_settings_panel_from_config()

def bootstrap_first_run_if_needed(log=None):
    """Host: ensure IP present and share exists. User: leave blanks."""
    o = config.setdefault('Offline', {})
    general = config.setdefault('General', {})
    mode = general.get('first_run_mode', '').upper()

    # Only set default if missing; do not flip an explicit False to True
    if "use_ip_unc" not in o:
        o['use_ip_unc'] = 'True'

    if mode == 'HOST':
        if not o.get('host_ip'):
            ip = get_primary_ipv4()
            if ip:
                o['host_ip'] = ip
        o['use_ip_unc'] = 'True'
        ensure_offline_share_exists(log=log or (lambda m: None))
        save_config()
        # Start host beacon to advertise IP on LAN
        try:
            start_host_beacon()
        except Exception:
            pass
        # ALSO listen for user beacons to collect their fuser counts for display
        try:
            start_user_listener()
        except Exception:
            pass
    elif mode == 'USER':
        # Default User mode behavior: run fusers locally and listen for Host beacons
        try:
            fsec = config.setdefault('Fusers', {})
            if 'fuser_computer' not in fsec:
                fsec['fuser_computer'] = 'True'
            if 'desired_count' not in fsec:
                fsec['desired_count'] = '3'
            save_config()
        except Exception:
            pass
        # Listen for host beacons (auto-discovery)
        try:
            start_user_listener()
        except Exception:
            pass
        # ALSO broadcast our own beacon with fuser counts for host to display
        try:
            start_host_beacon()
        except Exception:
            pass
    # UPDATE mode: no changes so far

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
        icon_path = _resource_path(ICON_NAME)
        widget.iconbitmap(icon_path)
    except Exception as e:
        pass

_orig_toplevel_init = tk.Toplevel.__init__   

def _toplevel_init_with_icon(self, *args, **kwargs):
    _orig_toplevel_init(self, *args, **kwargs)

    def _maybe_icon():
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
save_config()
def load_image(path, size=None):
    img = Image.open(path)
    if size:
        img = img.resize(size, Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(img)
if 'fullscreen' not in config['General']:
    config['General']['fullscreen'] = 'False' 
    save_config()

# Set fast startup config defaults (only if not already present)
config_changed = False
if not config.has_section('General'):
    config.add_section('General')
    config_changed = True

if 'fast_startup' not in config['General']:
    config['General']['fast_startup'] = 'True'
    config_changed = True

if 'path_scan_budget_ms' not in config['General']:
    config['General']['path_scan_budget_ms'] = '900'
    config_changed = True

if 'allow_c_drive_scan' not in config['General']:
    config['General']['allow_c_drive_scan'] = 'False'
    config_changed = True

# Override fast_startup if --fast-start CLI flag is present
if FAST_START_CLI:
    config['General']['fast_startup'] = 'True'
    config_changed = True

if config_changed:
    save_config()

# =============================================================================
# Background warm-up tasks (run off the UI thread)
# =============================================================================

def check_network_status_during_warmup():
    """Non-blocking network status check during startup warmup."""
    global APP_INSTANCE
    try:
        # Get working folder UNC for testing
        wf_unc = working_fuser_unc()
        if wf_unc and wf_unc.startswith("\\\\"):
            # Extract host IP from UNC path
            parts = wf_unc.strip("\\").split("\\")
            if len(parts) >= 1:
                host_ip = parts[0]
                
                # Quick ping check first to avoid SMB startup costs
                if not quick_ping_check(host_ip, timeout=0.5):
                    if APP_INSTANCE:
                        APP_INSTANCE.network_status = "offline"
                    logging.info(f"[startup] Host {host_ip} not reachable via ping, continuing in offline mode")
                    return False
                
                # If ping succeeds, do quick UNC check
                if quick_unc_check(wf_unc, timeout=2):
                    if APP_INSTANCE:
                        APP_INSTANCE.network_status = "online"
                    logging.info("[startup] Network connectivity confirmed")
                    return True
                else:
                    if APP_INSTANCE:
                        APP_INSTANCE.network_status = "offline"
                    logging.info("[startup] Network not accessible, continuing in offline mode")
                    return False
            else:
                if APP_INSTANCE:
                    APP_INSTANCE.network_status = "offline"
                logging.info("[startup] Invalid UNC path, running in local mode")
                return False
        else:
            # No UNC configured, assume local mode
            if APP_INSTANCE:
                APP_INSTANCE.network_status = "offline"
            logging.info("[startup] No network UNC configured, running in local mode")
            return False
    except Exception as e:
        logging.warning(f"[startup] Network check failed: {e}")
        if APP_INSTANCE:
            APP_INSTANCE.network_status = "offline"
        return False

def apply_offline_settings_with_skip_guard() -> None:
    """Apply offline settings with skip_startup_connect guard for first boot."""
    # Check if we should skip network connection attempts on startup
    skip = config.getboolean('General', 'skip_startup_connect', fallback=False)
    if skip:
        logging.info("[warmup] skip_startup_connect=True, deferring network connection")
        # Clear the flag so next launch will try
        config['General']['skip_startup_connect'] = 'False'
        save_config()
        enforce_photomesh_settings()
        update_fuser_shared_path()
        _assert_shared_path_is_unc()  # Self-heal check 
        enforce_local_fuser_policy()
        
        # Schedule network connection check for after UI is loaded
        global APP_INSTANCE
        if APP_INSTANCE:
            APP_INSTANCE.after(2000, lambda: run_in_thread(lambda: apply_offline_settings()))      
        return
    apply_offline_settings()

def warm_up_environment(progress=lambda _msg: None, update_progress=lambda _val: None):
    """
    Do small, IO-bound checks in sequence to keep perceived startup snappy.
    Each step reports a user-friendly message via `progress(msg)` and
    updates the progress bar via update_progress(value).
    """
    try:
        logging.info("[warmup] ====== WARMUP STARTED ======")
    except:
        pass
    
    # Read configuration flags for startup behavior
    fast = config.getboolean("General", "fast_startup", fallback=True)
    budget = max(0.3, config.getfloat("General", "path_scan_budget_ms", fallback=900) / 1000.0)
    allow_c = config.getboolean("General", "allow_c_drive_scan", fallback=False)
    
    logging.info("[warmup] fast_startup=%s, budget=%.1fs, allow_c_drive_scan=%s", fast, budget, allow_c)
    
    # Small initial delay to ensure the splash is visible first
    time.sleep(0.05)
    update_progress(0.15)
    
    try:
        progress("Checking configuration…")
        bootstrap_first_run_if_needed(log=log_to_console)
        update_progress(0.25)
    except Exception as e:
        log_to_console(f"[warmup] bootstrap: {e}")
        update_progress(0.25)

    steps = [
        ("Detecting VBS4…",          lambda: get_vbs4_install_path(time_budget_sec=budget, allow_full_drive=allow_c and not fast)),
        ("Detecting VBS4 Launcher…", lambda: get_vbs4_launcher_path(time_budget_sec=budget, allow_full_drive=allow_c and not fast)),
        ("Detecting Blue IG…",       get_blueig_install_path),
        ("Detecting ARES Manager…",  get_ares_manager_path),
        ("Checking network connectivity…", check_network_status_during_warmup),
        ("Applying offline settings…", apply_offline_settings_with_skip_guard),
        ("Warming shared working folder…", auto_connect_shared_working_folder),
    ]
    
    # Calculate progress increment per step
    step_progress = 0.55 / len(steps)  # Distribute remaining 55% among steps
    current_progress = 0.25  # Starting from 25%
    
    for i, (label, fn) in enumerate(steps):
        try:
            progress(label)
            t0 = time.time()
            _ = fn() if callable(fn) else None
            elapsed = time.time() - t0
            if elapsed > budget * 1.2:  # Log if significantly over budget
                logging.info("[warmup] %s took %.2fs (budget was %.2fs)", label, elapsed, budget)
        except Exception as e:
            log_to_console(f"[warmup] {label}: {e}")
        
        # Update progress after each step
        current_progress += step_progress
        update_progress(current_progress)
        
        # Minimal delay for animation smoothness only
        time.sleep(0.05)
    
    # Final progress update and message
    update_progress(0.9)
    progress("Finalizing startup...")
    time.sleep(0.05) 
    update_progress(1.0)
    progress("Ready.")
    
    try:
        logging.info("[warmup] ====== WARMUP COMPLETED ======")
    except:
        pass

def _background_index_paths():
    """
    Background task that does expensive path discovery after the UI is live.
    Uses larger budgets but still finite to avoid hanging the system.
    """
    try:
        # Use larger budgets for background work but still time-bounded
        for label, fn in [
            ("VBS4", lambda: get_vbs4_install_path(time_budget_sec=6, allow_full_drive=True)),
            ("VBS4 Launcher", lambda: get_vbs4_launcher_path(time_budget_sec=6, allow_full_drive=True)),
            ("BlueIG", lambda: get_blueig_install_path()), 
            ("ARES Manager", lambda: get_ares_manager_path()),
        ]:
            try:
                path = fn()  # each is internally budgeted
                logging.info("[indexer] %s => %s", label, path or "<not found>")
            except Exception as e:
                logging.exception("[indexer] %s failed: %s", label, e)
    except Exception as e:
        logging.exception("[indexer] failed: %s", e)
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
    save_config()

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
    save_config()
elif 'fuser_computer' not in config['Fusers']:
    config['Fusers']['fuser_computer'] = 'False'
    save_config()
if 'working_folder_host' not in config['Fusers']:
    config['Fusers']['working_folder_host'] = ''
    save_config()

# --- Fuser helpers ---

def get_machine_name() -> str:
    return socket.gethostname().split('.')[0].upper()

def get_working_folder_host() -> str:
    return config['Fusers'].get('working_folder_host', '').split('.')[0].upper()

def is_host_machine() -> bool:
    """
    Determine if this PC is the Host machine.
    Checks multiple indicators:
    1. If local_data_root is set (Host has local shared drive)
    2. If machine name matches working_folder_host
    3. If this PC's IP matches the configured host_ip
    """
    # Method 1: Check if local_data_root is configured (strongest indicator)
    local_root = config.get('Offline', 'local_data_root', fallback='').strip()
    if local_root and os.path.isdir(local_root):
        return True
    
    # Method 2: Check if machine name matches working_folder_host
    if get_machine_name() == get_working_folder_host():
        return True
    
    # Method 3: Check if this PC's IP matches the configured host_ip
    try:
        host_ip = config.get('Offline', 'host_ip', fallback='').strip()
        if host_ip:
            # Get this PC's primary IP
            my_ip = get_primary_ipv4()
            if my_ip and my_ip == host_ip:
                return True
    except Exception:
        pass
    
    return False

def find_fuser_exe() -> str:
    """
    Try common install paths; fall back to walking PhotoMesh install folder.
    Emits detailed logs to help diagnose install-path issues on packaged builds.
    """
    try:
        import time as _time
        t0 = _time.time()
        candidates = [
            r"C:\\Program Files\\Skyline\\PhotoMesh\\Fuser\\PhotoMeshFuser.exe",
            r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\Fuser\\PhotoMeshFuser.exe",
            r"C:\\Program Files (x86)\\Skyline\\PhotoMesh\\Fuser\\PhotoMeshFuser.exe",
        ]
        for c in candidates:
            if os.path.isfile(c):
                logging.info(f"[find_fuser_exe] Found in candidates: {c}")
                return c

        root = r"C:\\Program Files\\Skyline\\PhotoMesh"
        logging.info(f"[find_fuser_exe] Walking install root: {root}")
        for dp, dn, fn in os.walk(root):
            if "PhotoMeshFuser.exe" in fn:
                found = os.path.join(dp, "PhotoMeshFuser.exe")
                dt = _time.time() - t0
                logging.info(f"[find_fuser_exe] Discovered via walk in {dt:.2f}s: {found}")
                return found
        dt = _time.time() - t0
        logging.error(f"[find_fuser_exe] NOT FOUND after {dt:.2f}s. Checked candidates and walked: {root}")
        return ""
    except Exception as e:
        logging.error(f"[find_fuser_exe] Exception: {e}")
        return ""

def photomesh_fuser_installed() -> bool:
    """Check if PhotoMesh Fuser is installed on this PC."""
    return bool(find_fuser_exe())

def ensure_fuser_defaults():
    """
    Set default fuser configuration if not already set.
    Only applies defaults when PhotoMesh Fuser is installed.
    Should be called once after config is loaded.
    """
    try:
        if not photomesh_fuser_installed():
            logging.info("[fuser] defaults: PhotoMesh Fuser not installed, skipping defaults")
            return
        
        if "Fusers" not in config:
            config.add_section("Fusers")
        
        fusers = config["Fusers"]
        changed = False
        
        # Set defaults if missing
        if not fusers.get("fuser_computer"):
            fusers["fuser_computer"] = "True"
            changed = True
            logging.info("[fuser] defaults: set fuser_computer=True")
        
        if not fusers.get("desired_count"):
            fusers["desired_count"] = "3"
            changed = True
            logging.info("[fuser] defaults: set desired_count=3")
        
        if not fusers.get("work_mode"):
            fusers["work_mode"] = "local"
            changed = True
            logging.info("[fuser] defaults: set work_mode=local")
        
        if not fusers.get("autostart_on_launch"):
            fusers["autostart_on_launch"] = "True"
            changed = True
            logging.info("[fuser] defaults: set autostart_on_launch=True")
        
        # In local mode, disable shared working folder enforcement
        if fusers.get("work_mode", "").lower() == "local":
            if not fusers.get("enforce_shared_only") or fusers.get("enforce_shared_only", "").lower() != "false":
                fusers["enforce_shared_only"] = "False"
                changed = True
                logging.info("[fuser] defaults: set enforce_shared_only=False for local mode")
        
        # Default behavior: allow killing on exit unless explicitly disabled
        try:
            if not fusers.get("kill_on_exit"):
                fusers["kill_on_exit"] = "True"
                changed = True
                logging.info("[fuser] defaults: set kill_on_exit=True")
        except Exception:
            pass

        if changed:
            _save_config()
            logging.info("[fuser] defaults: saved config with fuser defaults")
    except Exception as e:
        logging.error(f"[fuser] defaults: failed to set defaults: {e}")

# Call ensure_fuser_defaults() once at module load
ensure_fuser_defaults()

# ============================================================================
# PHOTOMESH FUSER MANAGEMENT
# Controls distributed PhotoMesh Fuser instances across multiple PCs
# ============================================================================

def list_local_fusers() -> list:
    """
    Query running PhotoMeshFuser.exe processes on this machine (windowless).
    
    Prefers psutil (pure API, no console). Falls back to hidden tasklist.
    Returns list of processes (psutil.Process objects or dict-like info).
    """
    procs = []
    target = 'photomeshfuser.exe'
    
    if psutil:
        # Best path: use psutil API (no console, no window)
        try:
            for p in psutil.process_iter(['name', 'exe', 'cmdline', 'pid']):
                nm = (p.info.get('name') or '').lower().strip()
                ex = (p.info.get('exe') or '').lower().strip()
                base = os.path.basename(ex) if ex else ''
                if nm == target or base == target or ('photomeshfuser' in nm) or ('photomeshfuser' in base):
                    procs.append(p)
        except Exception:
            pass
    else:  
        # Fallback: hidden tasklist (no console window)
        try:
            result = run_hidden(['tasklist', '/FI', 'IMAGENAME eq PhotoMeshFuser.exe', '/FO', 'CSV', '/NH'], timeout=3)
            if result.returncode == 0 and result.stdout:
                import csv, io
                for row in csv.reader(io.StringIO(result.stdout)):
                    if not row or not row[0].strip():
                        continue
                    name = row[0].strip().strip('"').lower()
                    if name == 'photomeshfuser.exe':
                        try:
                            pid = int(row[1].strip().strip('"'))
                        except Exception:
                            pid = None
                        procs.append({'pid': pid, 'name': name})
        except Exception:
            pass
    return procs

def count_local_fusers() -> int:
    """
    Return count of ALL running PhotoMeshFuser.exe processes on this machine.
    This includes both our fusers and any foreign fusers (e.g., from scheduled tasks).
    This checks actual running processes in Task Manager, NOT seeded directories.
    
    Uses debounce lock to prevent overlapping checks (avoids console window bursts).
    """
    global _LAST_FUSER_CHECK
    
    # Quick non-blocking check: skip if another check is in progress
    if not _FUSER_CHECK_LOCK.acquire(blocking=False):
        # Return cached count if a check is already running
        cached = getattr(count_local_fusers, '_cached_count', 0)
        return cached
    
    try:
        _LAST_FUSER_CHECK = time.time()
        count = len(list_local_fusers())
        
        # Cache the result for rapid subsequent calls
        count_local_fusers._cached_count = count
        
        # Log for debugging when count seems wrong
        if count > 0:
            logging.debug(f"[fuser-count] Detected {count} PhotoMeshFuser.exe process(es) running locally")
        
        return count
    finally:
        _FUSER_CHECK_LOCK.release()

def count_all_fusers_from_shared() -> int:
    """
    Count total ACTIVE fusers across ALL PCs by scanning the shared WorkingFuser directory.
    Returns the total count of fuser subdirectories (e.g., MACHINE(IP)_FuserName) that have
    been modified within the last 60 seconds (indicating an active fuser process).
    """
    try:
        # Get the shared working path
        o = get_offline_cfg()
        if not o.get("enabled"):
            return 0
        
        shared_path = None
        if o.get("local_data_root"):
            # Host PC using local path
            local_root = o.get("local_data_root", "").strip()
            wf_sub = (o.get("working_fuser_subdir") or "WorkingFuser").strip()
            shared_path = os.path.join(local_root, wf_sub) if local_root else None
        else:
            # User PC using UNC path
            shared_path = config.get('Fusers', 'shared_working_unc', fallback='').strip()
        
        if not shared_path or not os.path.isdir(shared_path):
            return 0
        
        # Count fuser directories matching pattern: MACHINE(IP)_FuserName
        # Only count directories modified within the last 60 seconds (active fusers)
        pattern = re.compile(r"([^()]+)\(([^()]+)\)_(.+)")
        count = 0
        current_time = time.time()
        activity_threshold = 60  # seconds - fusers should write/update files within this window
        
        for entry in os.scandir(shared_path):
            if entry.is_dir() and pattern.match(entry.name):
                try:
                    # Check if directory has been modified recently
                    mtime = entry.stat().st_mtime
                    age_seconds = current_time - mtime
                    
                    if age_seconds <= activity_threshold:
                        count += 1
                        logging.debug(f"[count_all_fusers] Active fuser: {entry.name} (age: {age_seconds:.1f}s)")
                    else:
                        logging.debug(f"[count_all_fusers] Stale fuser directory: {entry.name} (age: {age_seconds:.1f}s)")
                except Exception as e:
                    logging.debug(f"[count_all_fusers] Error checking {entry.name}: {e}")
                    continue
        
        logging.debug(f"[count_all_fusers] Total active fusers: {count}")
        return count
    except Exception as e:
        logging.debug(f"[count_all_fusers] Error: {e}")
        return 0


# Fuser instance limits
MIN_LOCAL_FUSERS = 1
MAX_LOCAL_FUSERS = 3
MAX_TOTAL_FUSERS = 10  # Maximum fusers across all PCs

# Fuser enforcement control flags
_FUSER_ENFORCE_LOCK = threading.Lock()
_last_enforce_target: int | None = None
_last_enforce_ts: float = 0.0
_skip_fuser_enforcement_at_startup: bool = True

# Keep process references to prevent garbage collection from terminating fusers
_FUSER_PROCESSES: list = []

# Gate enforcement until UNC is confirmed ready (prevents startup race condition)
_allow_fuser_enforcement: bool = False

# -----------------------------------------------------------------------------
# First-run readiness gating and diagnostics
# -----------------------------------------------------------------------------
def _is_admin() -> bool:
    """Return True if process has administrative privileges on Windows."""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def _safe_stat(path: str) -> dict:
    """Return a small dict with exists/size/mtime for a path, swallowing errors."""
    info = {"exists": False, "size": None, "mtime": None, "len": len(path) if isinstance(path, str) else None}
    try:
        if path and os.path.exists(path):
            info["exists"] = True
            try:
                st = os.stat(path)
                info["size"] = st.st_size
                info["mtime"] = st.st_mtime
            except Exception:
                pass
    except Exception:
        pass
    return info

def _explain_winerror(err: BaseException) -> str:
    """Translate common Windows error codes to friendly text."""
    try:
        import errno
        we = getattr(err, 'winerror', None) or getattr(err, 'errno', None)
        if we is None:
            return ""
        mapping = {
            2: "File not found",
            3: "Path not found",
            5: "Access denied",
            13: "Permission denied",
            32: "Sharing violation",
            193: "Not a valid Win32 application (architecture mismatch or corrupt)",
            206: "Filename or path too long",
            740: "Elevation required (run as Administrator)",
        }
        txt = mapping.get(we)
        if not txt and isinstance(we, int):
            txt = f"WinError {we}"
        return txt or ""
    except Exception:
        return ""

def _write_launch_diag(workdir: str, idx: int, diag: dict) -> None:
    """Best-effort write of per-ID launch diagnostics to the workdir for offline review."""
    try:
        sub = os.path.join(workdir, "_launch_debug")
        os.makedirs(sub, exist_ok=True)
        fname = os.path.join(sub, f"launch_diag_{idx}.txt")
        with open(fname, 'w', encoding='utf-8') as f:
            for k, v in diag.items():
                f.write(f"{k}: {v}\n")
    except Exception:
        # Ignore failures (e.g., no permissions); diagnostics are also in logging
        pass
def _resolve_working_root_for_checks() -> tuple[str | None, str]:
    """Return (working_root_path, mode) where mode is 'host' or 'user'."""
    try:
        if is_host_machine():
            o = get_offline_cfg()
            local_root = (o.get("local_data_root") or "").strip()
            wf_sub = (o.get("working_fuser_subdir") or "WorkingFuser").strip()
            if local_root:
                return os.path.join(local_root, wf_sub), 'host'
        # User mode fallback: UNC
        path = config.get('Fusers', 'shared_working_unc', fallback='').strip() or working_fuser_unc()
        return (path if path else None), 'user'
    except Exception:
        return None, 'user'

def _probe_write_test(root: str) -> tuple[bool, str | None]:
    """Create/Read/Delete a tiny probe file under WorkingFuser to confirm write access."""
    try:
        probe_dir = os.path.join(root, "_probe")
        os.makedirs(probe_dir, exist_ok=True)
        pc = os.environ.get('COMPUTERNAME') or platform.node() or 'PC'
        fname = f"{pc}_probe.txt"
        fpath = os.path.join(probe_dir, fname)
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write("ok\n")
        with open(fpath, 'r', encoding='utf-8') as f:
            data = f.read().strip()
        os.remove(fpath)
        return (data == 'ok'), None
    except Exception as e:
        return False, str(e)

def _kill_seed_fusers(max_wait_s: float = 3.0) -> tuple[bool, list[int]]:
    """Find and terminate SeedFuser helper instances if present. Returns (all_gone, pids)."""
    pids: list[int] = []
    if not psutil:
        return True, pids
    try:
        for proc in psutil.process_iter(['name', 'cmdline', 'pid']):
            try:
                if (proc.info.get('name', '').lower() != 'photomeshfuser.exe'):
                    continue
                cmd = proc.info.get('cmdline') or []
                joined = ' '.join(cmd).lower()
                arg1 = cmd[1] if len(cmd) > 1 else ''
                non_numeric_id = False
                try:
                    int(arg1)
                except Exception:
                    non_numeric_id = True
                if ('seedfuser' in joined) or non_numeric_id:
                    pids.append(proc.info['pid'])
                    try:
                        proc.terminate()
                    except Exception:
                        pass
            except Exception:
                continue
        # Wait up to max_wait_s for them to exit
        if pids:
            end_t = time.time() + max_wait_s
            while time.time() < end_t:
                alive = False
                for pid in list(pids):
                    try:
                        psutil.Process(pid)
                        alive = True
                        break
                    except Exception:
                        # Gone
                        pids.remove(pid)
                        continue
                if not alive:
                    break
                time.sleep(0.2)
        return (len(pids) == 0), pids
    except Exception:
        return True, pids

def ready_for_fusers() -> tuple[bool, dict]:
    """Check if environment is ready to launch fusers. Returns (ready, diagnostics)."""
    diag: dict = {}
    # Exe check
    exe = find_fuser_exe()
    exe_ok = bool(exe and os.path.isfile(exe))
    diag['exe_ok'] = exe_ok
    diag['exe_path'] = exe or ''
    
    # Working root and loopback rule
    root, mode = _resolve_working_root_for_checks()
    diag['working_root'] = root or ''
    is_host = is_host_machine()
    loopback_ok = True
    if is_host and root and root.startswith('\\\\'):
        loopback_ok = False
    diag['loopback_ok'] = loopback_ok
    
    # Share reachable
    share_ok = bool(root and os.path.isdir(root))
    diag['share_ok'] = share_ok
    
    # Write probe
    write_ok = False
    write_err = None
    if share_ok and root:
        write_ok, write_err = _probe_write_test(root)
    diag['write_test'] = 'ok' if write_ok else (f"fail:{write_err}" if write_err else 'fail')
    
    # SeedFuser handling
    seed_all_gone, seed_pids = _kill_seed_fusers(max_wait_s=3.0)
    diag['seed_ok'] = seed_all_gone
    diag['seed_pids'] = seed_pids
    
    ready = bool(exe_ok and loopback_ok and share_ok and write_ok and seed_all_gone)
    diag['ready'] = ready
    return ready, diag

def _clamp_fusers(n: int, is_fuser_computer: bool) -> int:
    """Constrain fuser count to valid range based on machine role."""
    if not is_fuser_computer:
        return 0
    return max(MIN_LOCAL_FUSERS, min(MAX_LOCAL_FUSERS, int(n)))

def create_fuser_bat_wrappers(max_fusers: int = 8) -> None:
    """
    Create LocalFuser{n}.bat files that embed the correct UNC path.
    This provides a fallback method to ensure fusers always get the right working folder.
    """
    try:
        # Check system resources before creating files
        try:
            memory_info = get_memory_usage()
            if 'percent' in memory_info and memory_info['percent'] > 90:
                logging.warning("[create_fuser_bats] Skipping due to high memory usage")
                return
        except:
            pass  # If memory check fails, continue anyway
        
        exe = find_fuser_exe()
        if not exe:
            logging.warning("[create_fuser_bats] PhotoMeshFuser.exe not found")
            return

        shared = working_fuser_unc()
        if not shared:
            logging.warning("[create_fuser_bats] No shared working UNC configured")
            return

        fuser_dir = os.path.dirname(exe)
        if not os.access(fuser_dir, os.W_OK):
            logging.warning(f"[create_fuser_bats] No write access to {fuser_dir}")
            return
            
        shared_normalized = os.path.normpath(shared).replace("/", "\\")
        
        # Limit the number of batch files to reduce resource usage
        safe_max_fusers = min(max_fusers, 3)      
        created_count = 0
        for i in range(1, safe_max_fusers + 1):
            bat_name = f"LocalFuser{i}.bat"
            bat_path = os.path.join(fuser_dir, bat_name)
            
            # Skip if file already exists and is recent
            if os.path.exists(bat_path):
                try:
                    stat = os.stat(bat_path)
                    age_hours = (time.time() - stat.st_mtime) / 3600
                    if age_hours < 24:  
                        logging.debug(f"[create_fuser_bats] Skipping recent {bat_path}")
                        created_count += 1
                        continue
                except:
                    pass
            
            # Create batch file content with memory-optimized approach
            bat_content = f'@echo off\nstart "" "{exe}" "LocalFuser{i}" "{shared_normalized}" 0 true\n'
            
            try:
                # Use context manager for proper file handling
                with open(bat_path, 'w', encoding='ansi') as f:
                    f.write(bat_content)
                created_count += 1
                logging.debug(f"[create_fuser_bats] Created {bat_path}")
                
                # Force garbage collection after each file
                gc.collect()
                
            except Exception as e:
                logging.warning(f"[create_fuser_bats] Failed to create {bat_path}: {e}")
                # Continue with other files
        
        if created_count > 0:
            logging.info(f"[create_fuser_bats] Created/verified {created_count} batch wrappers in {fuser_dir}")
        else:
            logging.warning("[create_fuser_bats] No batch wrappers created")
            
    except Exception as e:
        logging.error(f"[create_fuser_bats] Unexpected error: {e}")

# Fuser launch throttling to prevent spawn storms
_SPAWN_LOCK = threading.Lock()
_SPAWN_FAILS = {}   # Track failure counts per fuser index
_LAST_TRY = {}      # Track last launch attempt timestamp per index

def _resolve_fuser_workdir(idx: int) -> str:
    r"""
    Resolve the per-instance working directory for a fuser.
    
    Naming scheme (restored): <MACHINE>-<idx>(<IPv4>)_LocalFuser<idx>
    Examples:
      - Host local:  E:\SharedMeshDrive\WorkingFuser\KIT1-1-1(192.168.10.10)_LocalFuser1
      - User UNC:    \\192.168.10.201\SharedMeshDrive\WorkingFuser\KIT2-3-1(192.168.10.22)_LocalFuser1
    
    Creates the directory if it doesn't exist.
    """
    if is_host_machine():
        # Host: Use local path to avoid UNC loopback
        o = get_offline_cfg()
        local_root = o.get("local_data_root", r"D:\\SharedMeshDrive").strip()
        wf_sub = o.get("working_fuser_subdir", "WorkingFuser").strip()
        base_path = os.path.join(local_root, wf_sub)
    else:
        # User: Use UNC path
        base_path = working_fuser_unc()

    # Build the folder name with PC name and IP prefix for uniqueness across machines
    try:
        pc = get_machine_name()
    except Exception:
        pc = os.environ.get('COMPUTERNAME', 'PC').upper()
    try:
        ip = get_primary_ipv4() or "0.0.0.0"
    except Exception:
        ip = "0.0.0.0"

    # IMPORTANT: Do NOT include the index in the machine prefix, so host UI groups by PC correctly
    folder_name = f"{pc}({ip})_LocalFuser{idx}"
    workdir = os.path.join(base_path, folder_name)
    os.makedirs(workdir, exist_ok=True)
    normalized = os.path.normpath(workdir).replace("/", "\\")
    logging.info(f"[_resolve_fuser_workdir] idx={idx} -> {normalized}")
    return normalized


def _detect_running_fusers() -> dict:
    """
    Detect running PhotoMesh fusers by analyzing their command lines.
    
    Returns:
        dict mapping idx (1,2,3) -> psutil.Process for OUR fusers only.
        Foreign fusers (different working dirs) are logged but not returned.
    """
    result = {}
    foreign_count = 0
    
    if not psutil:
        return result
    
    try:
        for proc in psutil.process_iter(['name', 'cmdline', 'pid']):
            try:
                if proc.info.get('name', '').lower() != 'photomeshfuser.exe':
                    continue
                
                cmdline = proc.info.get('cmdline') or []
                if len(cmdline) < 3:
                    continue
                
                # Expected format: ["PhotoMeshFuser.exe", "ID", "WorkingFolder"]
                fuser_id_str = cmdline[1]
                fuser_workdir = cmdline[2]
                # Exclude SeedFuser or any non-standard launch with non-numeric ID
                try:
                    _ = int(fuser_id_str)
                except Exception:
                    foreign_count += 1
                    logging.info(f"[fuser-detect] Excluding non-numeric/Seed fuser PID={proc.info['pid']} arg1={fuser_id_str}")
                    continue
                
                # Try to parse ID
                try:
                    fuser_id = int(fuser_id_str)
                except (ValueError, IndexError):
                    foreign_count += 1
                    logging.info(f"[fuser-detect] Foreign fuser PID={proc.info['pid']}, ID={fuser_id_str}, counting toward target")
                    continue
                
                # Normalize paths for comparison
                fuser_workdir_normalized = os.path.normpath(fuser_workdir).replace("/", "\\").lower()
                
                # Check if this matches one of our expected work dirs
                expected_workdir = _resolve_fuser_workdir(fuser_id).lower()
                
                if fuser_workdir_normalized == expected_workdir:
                    result[fuser_id] = proc
                    logging.debug(f"[fuser-detect] Our fuser #{fuser_id} found: PID={proc.info['pid']}, dir={fuser_workdir}")
                else:
                    foreign_count += 1
                    logging.info(f"[fuser-detect] Foreign fuser PID={proc.info['pid']}, ID={fuser_id}, dir={fuser_workdir}, counting toward target")
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    
    except Exception as e:
        logging.error(f"[fuser-detect] Error detecting fusers: {e}")
    
    total_detected = len(result) + foreign_count
    
    # DEBUG: Print detection results to console
    print(f"🔍 _detect_running_fusers() → Found {len(result)} OUR fusers, {foreign_count} foreign → TOTAL={total_detected}")
    if result:
        print(f"   Our fuser IDs: {sorted(result.keys())}")
    
    if total_detected > 0:
        logging.info(f"[fuser-detect] Total fusers: {total_detected} (ours: {len(result)}, foreign: {foreign_count})")
    
    return result


def start_fuser_instance(idx: int) -> bool:
    """
    Launch a single PhotoMeshFuser.exe instance using official calling convention.
    
    Args:
        idx: Fuser instance ID (1, 2, or 3)
    
    Returns:
        True if launch succeeded and process stabilized, False otherwise
    
    Launch format: PhotoMeshFuser.exe "ID" "WorkingFolder"
    - No CMD windows (CREATE_NO_WINDOW + STARTF_USESHOWWINDOW)
    - Waits up to 7s for stabilization
    - Retries once on early exit with 2s backoff
    """
    try:
        logging.info(f"[start_fuser_instance] Launching fuser #{idx}")
        
        # Find the fuser executable
        exe = find_fuser_exe()
        if not exe:
            logging.error("[start_fuser_instance] PhotoMeshFuser.exe not found")
            return False
        if not isinstance(exe, str):
            logging.warning(f"[start_fuser_instance] exe came back non-str ({type(exe)}), coercing")
            exe = str(exe)
        logging.info(f"[start_fuser_instance] Fuser exe: {exe}")
        exe_stat = _safe_stat(exe)
        logging.info(f"[start_fuser_instance] exe_stat: exists={exe_stat['exists']} size={exe_stat['size']} mtime={exe_stat['mtime']} len={exe_stat['len']}")
        
        # Resolve the per-instance working directory
        workdir = _resolve_fuser_workdir(idx)
        if not isinstance(workdir, str):
            logging.warning(f"[start_fuser_instance] workdir came back non-str ({type(workdir)}), coercing")
            workdir = str(workdir)
        logging.info(f"[start_fuser_instance] Working directory: {workdir}")
        wd_stat = _safe_stat(workdir)
        logging.info(f"[start_fuser_instance] workdir_stat: exists={wd_stat['exists']} size={wd_stat['size']} mtime={wd_stat['mtime']} len={wd_stat['len']}")
        # Probe write permission in workdir
        try:
            probe_name = os.path.join(workdir, f".probe_{idx}.tmp")
            with open(probe_name, 'w', encoding='utf-8') as f:
                f.write("probe\n")
            os.remove(probe_name)
            logging.info("[start_fuser_instance] workdir write probe: OK")
            wd_write_ok = True
        except Exception as e:
            logging.warning(f"[start_fuser_instance] workdir write probe FAILED: {e}")
            wd_write_ok = False

        # Clear stale lock files in this instance's directory
        lock_files = ["Fuser.lock", "fuser.lock", ".lock", "PhotoMesh.lock"]
        for lock_name in lock_files:
            lock_path = os.path.join(workdir, lock_name)
            if os.path.exists(lock_path):
                try:
                    os.remove(lock_path)
                    logging.debug(f"[start_fuser_instance] Removed stale lock: {lock_name}")
                except Exception as e:
                    logging.warning(f"[start_fuser_instance] Could not remove {lock_name}: {e}")

        # Build args: PhotoMeshFuser.exe "ID" "WorkingFolder"
        args = [exe, str(idx), workdir]
        logging.info(f"[start_fuser_instance] debug args types: {[type(a).__name__ for a in args]}")
        # Build Windows cmdline for logging
        try:
            cmdline_txt = subprocess.list2cmdline(args)
        except Exception:
            cmdline_txt = ' '.join(args)
        logging.info(f"[start_fuser_instance] cmdline: {cmdline_txt}")
        logging.info(f"[start_fuser_instance] cwd(for spawn): {os.path.dirname(exe)}")
        logging.info(f"[start_fuser_instance] process: pid={os.getpid()} thread={threading.current_thread().name} admin={_is_admin()}")
        # Disk free info
        try:
            import shutil
            total, used, free = shutil.disk_usage(workdir)
            logging.info(f"[start_fuser_instance] disk: total={total} used={used} free={free}")
        except Exception:
            pass

        # Prepare hidden console spawn
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        
        creation_flags = subprocess.CREATE_NO_WINDOW | 0x00000008 | 0x00000200  # NO_WINDOW | DETACHED | NEW_PROCESS_GROUP
        # Build textual flags for logging
        try:
            parts = []
            if creation_flags & subprocess.CREATE_NO_WINDOW:
                parts.append('NO_WINDOW')
            if creation_flags & 0x00000008:
                parts.append('DETACHED')
            if creation_flags & 0x00000200:
                parts.append('NEW_GROUP')
            flags_text = '|'.join(parts) if parts else str(creation_flags)
        except Exception:
            flags_text = str(creation_flags)

        retry_attempted = False

        for attempt in range(2):  # Try twice: initial + one retry
            try:
                logging.info(f"[start_fuser_instance] Launching: {' '.join(args)}")
                proc = subprocess.Popen(
                    args,
                    cwd=os.path.dirname(exe),
                    startupinfo=si,
                    creationflags=creation_flags
                )
                logging.info(f"[launch] ID={idx} dir={workdir} flags={flags_text} pid={proc.pid}")
                logging.info(f"[start_fuser_instance] Process spawned with PID {proc.pid}, stabilizing...")
                
                # Stabilization window: wait up to 7 seconds, checking every 0.5s
                stabilization_time = 7.0
                check_interval = 0.5
                elapsed = 0.0
                
                while elapsed < stabilization_time:
                    time.sleep(check_interval)
                    elapsed += check_interval
                    
                    # Check if process is still alive
                    retcode = proc.poll()
                    if retcode is not None:
                        # Process exited early
                        if not retry_attempted:
                            logging.warning(f"[start_fuser_instance] Fuser {idx} exited early (code {retcode}) after {elapsed:.1f}s, retrying...")
                            retry_attempted = True
                            time.sleep(2.0)  # Backoff before retry
                            
                            # Clear locks again before retry
                            for lock_name in lock_files:
                                lock_path = os.path.join(workdir, lock_name)
                                if os.path.exists(lock_path):
                                    try:
                                        os.remove(lock_path)
                                    except Exception:
                                        pass
                            break  # Break inner loop to retry
                        else:
                            # Summary log: FUSER FAILED (early exit after retry)
                            print("\n" + "="*80)
                            print(f"❌ FUSER {idx} FAILED - Exited early after retry")
                            print(f"   Exit Code: {retcode}")
                            print(f"   Working Dir: {workdir}")
                            print(f"   Time Before Exit: {elapsed:.1f}s")
                            print("="*80 + "\n")
                            logging.error(f"[FUSER-FAILED] ID={idx} reason=early_exit_after_retry exitcode={retcode} workdir={workdir} elapsed={elapsed:.1f}s")
                            return False
                else:
                    # Stabilization successful (process still running after full window)
                    try:
                        log_dir = os.path.join(workdir, "_logs")
                        created_log = os.path.isdir(log_dir)
                    except Exception:
                        created_log = False
                    logging.info(f"[launch] stabilize: alive=✓, created_log={'✓' if created_log else '✗'} after {stabilization_time}s")
                    logging.info(f"[start_fuser_instance] ✓ Fuser {idx} stabilized successfully after {stabilization_time}s (PID: {proc.pid})")
                    
                    # Summary log: FUSER STARTED
                    print("\n" + "="*80)
                    print(f"✅ FUSER {idx} STARTED SUCCESSFULLY")
                    print(f"   PID: {proc.pid}")
                    print(f"   Working Dir: {workdir}")
                    print(f"   Stabilization: {stabilization_time}s")
                    print("="*80 + "\n")
                    logging.info(f"[FUSER-SUCCESS] ID={idx} PID={proc.pid} workdir={workdir} stabilized_after={stabilization_time}s")
                    
                    try:
                        try:
                            import platform
                        except Exception:
                            platform = None
                        pc = os.environ.get('COMPUTERNAME') or (platform.node() if platform else None) or 'UnknownPC'
                        print(f"{pc}: ✓ Fuser {idx} stabilized and running (PID: {proc.pid})")
                    except Exception:
                        pass
                    
                    # Keep reference to prevent GC termination
                    global _FUSER_PROCESSES
                    _FUSER_PROCESSES.append(proc)
                    
                    return True
            
            except Exception as e:
                hint = _explain_winerror(e)
                logging.error(f"[start_fuser_instance] Launch failed: {e} {('['+hint+']') if hint else ''}", exc_info=True)
                
                # Summary log: FUSER FAILED (exception)
                if retry_attempted:
                    print("\n" + "="*80)
                    print(f"❌ FUSER {idx} FAILED - Launch exception after retry")
                    print(f"   Error: {e}")
                    print(f"   Hint: {hint if hint else 'N/A'}")
                    print(f"   Working Dir: {workdir}")
                    print(f"   Command: {cmdline_txt}")
                    print("="*80 + "\n")
                    logging.error(f"[FUSER-FAILED] ID={idx} reason=launch_exception_after_retry error={e} hint={hint} workdir={workdir}")
                
                # Persist quick diag for offline review
                try:
                    _write_launch_diag(workdir, idx, {
                        'exe': exe,
                        'workdir': workdir,
                        'args': cmdline_txt,
                        'flags': flags_text,
                        'admin': _is_admin(),
                        'wd_write_ok': wd_write_ok,
                        'exe_stat': exe_stat,
                        'wd_stat': wd_stat,
                        'error': str(e),
                        'hint': hint,
                    })
                except Exception:
                    pass
                try:
                    try:
                        import platform
                    except Exception:
                        platform = None
                    pc = os.environ.get('COMPUTERNAME') or (platform.node() if platform else None) or 'UnknownPC'
                    print(f"{pc}: ✗ Fuser {idx} launch failed: {e} {('['+hint+']') if hint else ''}")
                except Exception:
                    pass
                if retry_attempted:
                    return False
                retry_attempted = True
                time.sleep(2.0)

        return False
    except Exception as e:
        # Summary log: FUSER FAILED (uncaught exception)
        print("\n" + "="*80)
        print(f"❌ FUSER {idx} FAILED - Uncaught exception")
        print(f"   Error: {e}")
        print("="*80 + "\n")
        logging.error(f"[FUSER-FAILED] ID={idx} reason=uncaught_exception error={e}", exc_info=True)
        logging.error(f"[start_fuser_instance] UNCAUGHT exception for idx {idx}: {e}", exc_info=True)
        try:
            pc = os.environ.get('COMPUTERNAME') or platform.node() or 'UnknownPC'
            print(f"{pc}: ✗ Fuser {idx} start exception: {e}")
        except Exception:
            pass
        return False

def kill_fusers() -> None:
    """
    Kill ALL local PhotoMeshFuser.exe instances using psutil (no CMD windows).
    Attempts graceful termination first, then force kill if needed.
    """
    global _FUSER_PROCESSES
    
    # DEBUG: Log who is calling this function
    import traceback
    stack_trace = ''.join(traceback.format_stack())
    print("\n" + "="*80)
    print("🔴 kill_fusers() CALLED - Full stack trace:")
    print(stack_trace)
    print("="*80 + "\n")
    logging.error(f"[kill_fusers] 🔴 KILL REQUEST - Full stack trace:\n{stack_trace}")
    
    if not psutil:
        logging.warning("[kill_fusers] psutil not available, cannot kill fusers")
        return
    
    killed_count = 0
    
    try:
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                if proc.info.get('name', '').lower() == 'photomeshfuser.exe':
                    pid = proc.info['pid']
                    logging.info(f"[kill_fusers] Terminating PID {pid}")
                    
                    try:
                        proc.terminate()  # Graceful termination
                        proc.wait(timeout=5)  # Wait up to 5 seconds
                        logging.info(f"[kill_fusers] PID {pid} terminated gracefully")
                        killed_count += 1
                    except psutil.TimeoutExpired:
                        # Force kill if termination didn't work
                        logging.warning(f"[kill_fusers] PID {pid} did not terminate, force killing")
                        proc.kill()
                        proc.wait(timeout=2)
                        logging.info(f"[kill_fusers] PID {pid} force killed")
                        killed_count += 1
                        
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logging.debug(f"[kill_fusers] Process already gone or access denied: {e}")
                continue
                
    except Exception as e:
        logging.error(f"[kill_fusers] Error during kill: {e}")
    
    logging.info(f"[kill_fusers] Killed {killed_count} fuser process(es)")
    
    # Clear the process reference list after killing
    _FUSER_PROCESSES.clear()
    
    # Trigger immediate status update on OneClick panel if it exists
    try:
        from __main__ import app
        if hasattr(app, 'panels') and 'OneClick' in app.panels:
            oc_panel = app.panels['OneClick']
            if hasattr(oc_panel, 'force_update_host_status'):
                post_ui(oc_panel.force_update_host_status)
    except Exception:
        pass

def ensure_fuser_instances(desired: int):
    """
    Scale PhotoMeshFuser.exe processes to match the desired count.
    
    Args:
        desired: Target number of fuser instances
        
    Behavior:
    - Detects OUR fusers (matching LocalFuser1/2/3 directories)
    - Adopts foreign fusers and counts them toward target
    - If current < desired: Launch missing instances in parallel
    - If current > desired: Kill only OUR extra fusers (never foreign)
    - If current == desired: No action needed
    
    Uses locking to prevent concurrent enforcement attempts.
    Respects _skip_fuser_enforcement_at_startup flag during application startup.
    Saves final count for session restoration on next launch.
    """
    global _skip_fuser_enforcement_at_startup
    
    print("\n" + "="*80)
    print(f"===== Calling ensure_fuser_instances({desired}) =====")
    print("="*80 + "\n")
    logging.info(f"[fuser-scale] ===== ensure_fuser_instances({desired}) called =====")

    # Respect startup skip flag
    if _skip_fuser_enforcement_at_startup:
        logging.info("[fuser-scale] Skipping during startup phase")
        return

    # Prevent concurrent enforcement
    if not _FUSER_ENFORCE_LOCK.acquire(blocking=False):
        logging.info("[fuser-scale] Already running, skipping")
        return
    
    try:
        is_fuser = config["Fusers"].getboolean("fuser_computer", fallback=False)
        logging.info(f"[fuser-scale] is_fuser_computer: {is_fuser}")
    
        desired = _clamp_fusers(desired, is_fuser)
        logging.info(f"[fuser-scale] Clamped target: {desired}")

        # Detect OUR fusers (returns dict: {idx -> Process})
        our_fusers = _detect_running_fusers()
        
        # Count total fusers (including foreign)
        total_count = count_local_fusers()
        our_count = len(our_fusers)
        foreign_count = total_count - our_count
        
        logging.info(f"[fuser-scale] Current fusers: total={total_count}, ours={our_count}, foreign={foreign_count}")
    
        # IMPORTANT: Only manage OUR fusers, ignore foreign ones
        # Check if OUR count matches desired, not total count
        if our_count >= desired:
            if our_count == desired:
                logging.info(f"[fuser-scale] ✓ Already at target (ours={our_count}), no action needed")
                if foreign_count > 0:
                    logging.info(f"[fuser-scale] Note: {foreign_count} foreign fuser(s) also running (ignored)")
            else:
                # More of ours than desired - need to trim OUR extras only
                to_kill = our_count - desired
                
                # DEBUG: Print to console when trimming
                import traceback
                trim_trace = ''.join(traceback.format_stack())
                print("\n" + "="*80)
                print(f"🔴 ensure_fuser_instances() TRIM: total={total_count} > desired={desired}, will trim {to_kill}")
                print("Called from:")
                print(trim_trace)
                print("="*80 + "\n")
                
                logging.warning(f"[fuser-scale] ⚠️ TRIM NEEDED: total={total_count} > desired={desired}, will trim {to_kill} fuser(s)")
                logging.error(f"[fuser-scale] TRIM stack trace:\n{trim_trace}")
                
                # Kill only OUR extra fusers, starting from highest ID
                killed = 0
                for idx in sorted(our_fusers.keys(), reverse=True):
                    if killed >= to_kill:
                        break
                    
                    proc = our_fusers[idx]
                    try:
                        logging.info(f"[fuser-scale] Trimming our fuser #{idx}, PID={proc.pid}")
                        proc.terminate()
                        proc.wait(timeout=5)
                        killed += 1
                    except psutil.TimeoutExpired:
                        proc.kill()
                        killed += 1
                    except Exception as e:
                        logging.error(f"[fuser-scale] Failed to kill fuser #{idx}: {e}")
                
                logging.info(f"[fuser-scale] Trimmed {killed} fuser(s)")
            
            if is_fuser:
                save_last_launched_fuser_count(desired)
            return

        # Need to launch more of OUR fusers (ignore foreign count)
        to_start = desired - our_count
        logging.info(f"[fuser-scale] Starting {to_start} new instance(s) in PARALLEL")
        
        # Find which IDs are missing (1, 2, 3)
        available_ids = [i for i in range(1, 4) if i not in our_fusers]
        
        # Launch in parallel so multiple fusers start at about the same time
        launched = 0
        # Resolve PC name once for consistent prefixing
        try:
            import platform
        except Exception:
            platform = None
        pc_name = os.environ.get('COMPUTERNAME') or (platform.node() if platform else None) or 'UnknownPC'
        try:
            import concurrent.futures
            start_time = time.time()
            ids_to_launch = available_ids[:to_start]
            logging.info(f"[fuser-scale] Parallel launch IDs: {ids_to_launch}")
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(ids_to_launch) or 1) as executor:
                future_map = {executor.submit(start_fuser_instance, idx): idx for idx in ids_to_launch}
                failed_ids = []
                for future in concurrent.futures.as_completed(future_map):
                    idx = future_map[future]
                    try:
                        result = future.result()
                    except Exception as e:
                        logging.error(f"[fuser-scale] ✗ Fuser #{idx} raised during launch: {e}")
                        try:
                            print(f"{pc_name}: ✗ Fuser {idx} failed to start (exception): {e}")
                        except Exception:
                            pass
                        result = False
                    if result:
                        logging.info(f"[fuser-scale] ✓ Fuser #{idx} stabilized successfully (parallel)")
                        try:
                            print(f"{pc_name}: ✓ Fuser {idx} started successfully (parallel)")
                        except Exception:
                            pass
                        launched += 1
                    else:
                        logging.error(f"[fuser-scale] ✗ Fuser #{idx} failed to launch (parallel)")
                        try:
                            print(f"{pc_name}: ✗ Fuser {idx} failed to start (parallel)")
                        except Exception:
                            pass
                        failed_ids.append(idx)
            # Retry failed ones sequentially as a safety net
            if 'failed_ids' in locals() and failed_ids:
                logging.info(f"[fuser-scale] Retrying failed IDs sequentially: {failed_ids}")
                for idx in failed_ids:
                    logging.info(f"[fuser-scale] ► Retry launch fuser #{idx} (sequential)")
                    result = start_fuser_instance(idx)
                    if result:
                        logging.info(f"[fuser-scale] ✓ Fuser #{idx} stabilized successfully (sequential retry)")
                        try:
                            print(f"{pc_name}: ✓ Fuser {idx} started successfully (sequential retry)")
                        except Exception:
                            pass
                        launched += 1
                    else:
                        logging.error(f"[fuser-scale] ✗ Fuser #{idx} failed to launch (sequential retry)")
                        try:
                            print(f"{pc_name}: ✗ Fuser {idx} failed to start (sequential retry)")
                        except Exception:
                            pass
            dur = time.time() - start_time
            logging.info(f"[fuser-scale] Launch complete in {dur:.1f}s: started={launched} requested={to_start} ids={ids_to_launch} failed={failed_ids if 'failed_ids' in locals() else []}")
        except Exception as e:
            # Fallback to sequential on error
            logging.warning(f"[fuser-scale] Parallel launch unavailable, falling back to sequential: {e}")
            for idx in available_ids[:to_start]:
                logging.info(f"[fuser-scale] ► Launching fuser #{idx} (sequential fallback)")
                result = start_fuser_instance(idx)
                if result:
                    logging.info(f"[fuser-scale] ✓ Fuser #{idx} stabilized successfully")
                    try:
                        print(f"{pc_name}: ✓ Fuser {idx} started successfully")
                    except Exception:
                        pass
                    launched += 1
                else:
                    logging.error(f"[fuser-scale] ✗ Fuser #{idx} failed to launch")
                    try:
                        print(f"{pc_name}: ✗ Fuser {idx} failed to start")
                    except Exception:
                        pass
            logging.info(f"[fuser-scale] Launched {launched}/{to_start} new fuser(s) (sequential fallback)")
    
        # Persist count for next session
        if is_fuser:
            save_last_launched_fuser_count(desired)
            logging.info(f"[fuser-scale] Saved count for restoration: {desired}")
        
        # Final summary: Overall result
        final_running = count_local_fusers()
        print("\n" + "="*80)
        print(f"📊 FUSER ENFORCEMENT COMPLETE")
        print(f"   Target: {desired}")
        print(f"   Running: {final_running}")
        print(f"   Started this session: {launched}")
        if 'failed_ids' in locals() and failed_ids:
            print(f"   ⚠️ Failed IDs: {failed_ids}")
        print("="*80 + "\n")
        logging.info(f"[FUSER-SUMMARY] target={desired} running={final_running} started={launched} failed={failed_ids if 'failed_ids' in locals() and failed_ids else 'none'}")
        
        # Trigger immediate status update on OneClick panel if it exists
        try:
            from __main__ import app
            if hasattr(app, 'panels') and 'OneClick' in app.panels:
                oc_panel = app.panels['OneClick']
                if hasattr(oc_panel, 'force_update_host_status'):
                    post_ui(oc_panel.force_update_host_status)
        except Exception:
            pass
    finally:
        try:
            _FUSER_ENFORCE_LOCK.release()
        except Exception:
            pass

def save_last_launched_fuser_count(count: int):
    """Persist fuser count to config for session restoration."""
    try:
        config["Fusers"]["last_launched_count"] = str(count)
        _save_config()
    except Exception as e:
        pass

def get_last_launched_fuser_count() -> int:
    """Retrieve saved fuser count from previous session."""
    try:
        return int(config["Fusers"].get("last_launched_count", "0"))
    except (ValueError, KeyError):
        return 0

def kill_all_fusers_on_exit():
    """Kill all fusers when the toolkit exits (only if this is a fuser computer)."""
    try:
        is_fuser = config["Fusers"].getboolean("fuser_computer", fallback=False)
        kill_on_exit = config["Fusers"].getboolean("kill_on_exit", fallback=True)
        if is_fuser and kill_on_exit:
            logging.info("[on_exit] kill_on_exit=True -> terminating local fusers")
            kill_fusers()
            # Reset the launched count since we killed everything
            config["Fusers"]["last_launched_count"] = "0"
            _save_config()
        else:
            if is_fuser and not kill_on_exit:
                logging.info("[on_exit] kill_on_exit=False -> leaving local fusers running")
            else:
                logging.info("[on_exit] Not a fuser computer -> no fusers to terminate")
    except Exception as e:
        pass

def kill_fusers_on_disable():
    """Kill all fusers and reset count when fuser computer setting is disabled."""
    try:
        kill_fusers()
        # Reset the launched count since we killed everything
        config["Fusers"]["last_launched_count"] = "0"
        _save_config()
    except Exception as e:
        pass

def restore_fusers_on_startup():
    """
    Restore fuser instances from previous session on designated fuser computers.
    If this is first run (last_count=0), uses desired_count from config.
    
    This function is called during startup initialization and directly launches
    fusers without going through ensure_fuser_instances() to avoid the startup
    skip flag that would block normal enforcement.
    """
    try:
        is_fuser = config["Fusers"].getboolean("fuser_computer", fallback=False)
        is_host = is_host_machine()
        
        if not is_fuser and not is_host:
            logging.info("[restore-fusers] Not a fuser or host machine, skipping")
            return
            
        last_count = get_last_launched_fuser_count()
        
        # Determine target count for restoration
        if last_count > 0:
            target = last_count
            logging.info(f"[restore-fusers] Restoring {target} fusers from previous session")
        else:
            # First run or clean boot: use config defaults
            if is_host:
                host_ct, _ = get_fuser_counts()
                target = host_ct
                logging.info(f"[restore-fusers] First run as HOST, starting {target} fuser(s)")
            elif is_fuser:
                _, desired_ct = get_fuser_counts()
                target = desired_ct
                logging.info(f"[restore-fusers] First run as FUSER, starting {target} fuser(s)")
            else:
                target = 0
        
        if target > 0:
            # Clamp to valid range
            target = _clamp_fusers(target, True)
            logging.info(f"[restore-fusers] Clamped target: {target}")
            
            # Directly launch fusers without going through ensure_fuser_instances()
            # to avoid the startup enforcement skip flag
            current = count_local_fusers()
            logging.info(f"[restore-fusers] Current count: {current}")
            
            if current < target:
                logging.info(f"[restore-fusers] Launching {target - current} additional fuser(s)")
                for idx in range(current + 1, target + 1):
                    try:
                        if start_fuser_instance(idx):
                            logging.info(f"[restore-fusers] Started fuser #{idx}")
                        else:
                            logging.warning(f"[restore-fusers] Failed to start fuser #{idx}")
                    except Exception as e:
                        logging.error(f"[restore-fusers] Error starting fuser #{idx}: {e}")
                        
                # Save the count we actually launched
                save_last_launched_fuser_count(target)
                logging.info(f"[restore-fusers] Completed startup launch of {target} fuser(s)")
            else:
                logging.info(f"[restore-fusers] Already have {current} fusers running (target: {target})")
    except Exception as e:
        logging.error(f"[restore-fusers] Failed: {e}")
        pass

def enforce_local_fuser_policy():
    """
    Apply configured fuser instance policy based on machine role and work mode.
    
    Determines target fuser count based on:
    - Machine role (host vs fuser vs neither)
    - Work mode (local vs shared/UNC)
    - UNC accessibility (only checked in shared mode)
    - Configuration settings (desired_count, host_count)
    
    Gated by _allow_fuser_enforcement flag to prevent premature execution during startup.
    Includes throttling to prevent redundant enforcement within 8-second windows.
    """
    global _allow_fuser_enforcement, _last_enforce_target, _last_enforce_ts, _skip_fuser_enforcement_at_startup
    
    try:
        logging.info(f"[fuser-policy] enforce_local_fuser_policy() called")
        
        # CRITICAL: Block ALL enforcement during startup, regardless of mode
        if _skip_fuser_enforcement_at_startup:
            logging.info("[fuser-policy] GATED: enforcement blocked during startup phase")
            return
        
        # Gate: Don't enforce until UNC is confirmed ready (only for shared mode)
        work_mode = config.get("Fusers", "work_mode", fallback="local").strip().lower()
        
        if not _allow_fuser_enforcement and work_mode != "local":
            logging.info("[fuser-policy] GATED: enforcement disabled until UNC ready (shared mode)")
            return
        
        is_fuser = config["Fusers"].getboolean("fuser_computer", fallback=False)
        logging.info(f"[fuser-policy] is_fuser_computer: {is_fuser}")
        
        host_ct, desired_ct = get_fuser_counts()
        logging.info(f"[fuser-policy] get_fuser_counts() returned: host_ct={host_ct}, desired_ct={desired_ct}")
        
        is_host = is_host_machine()
        logging.info(f"[fuser-policy] is_host_machine(): {is_host}, work_mode: {work_mode}")
        
        # Compute target based on work mode
        if work_mode == "local":
            # LOCAL MODE: Target is always desired_count if fuser_computer=True
            # No UNC checks, no network dependencies
            if is_fuser:
                target = desired_ct
                logging.info(f"[fuser-policy] policy: mode=local is_fuser={is_fuser} desired={desired_ct} -> target={target}")
            else:
                target = 0
                logging.info(f"[fuser-policy] policy: mode=local is_fuser={is_fuser} -> target={target} (not a fuser PC)")
        else:
            # SHARED/UNC MODE: Original behavior with network checks
            # Check UNC accessibility
            unc_ok = False
            try:
                unc_root, _ = _compute_working_unc_from_cfg()
                if unc_root and unc_root.startswith("\\\\"):
                    unc_ok = quick_unc_check(unc_root, timeout=2.0)
                    logging.info(f"[fuser-policy] UNC check for {unc_root}: {unc_ok}")
            except Exception as e:
                logging.warning(f"[fuser-policy] UNC check failed: {e}")
            
            # Compute target with explicit decision logging
            if is_host:
                target = host_ct
                logging.info(f"[fuser-policy] policy: mode={work_mode} is_host=True -> target={target}")
            elif is_fuser and unc_ok:
                target = desired_ct
                logging.info(f"[fuser-policy] policy: mode={work_mode} is_fuser={is_fuser} unc_ok=True desired={desired_ct} -> target={target}")
            elif is_fuser and not unc_ok:
                # UNC not ready: ALWAYS use desired_ct, don't kill running fusers
                # The fusers can still work with UNC paths even if our quick check fails
                current = count_local_fusers()
                target = desired_ct  # Always use desired, don't depend on current count
                if current > 0:
                    logging.warning(f"[fuser-policy] policy: mode={work_mode} is_fuser={is_fuser} unc_ok=False -> keeping target={target} (current={current})")
                else:
                    logging.info(f"[fuser-policy] policy: mode={work_mode} is_fuser={is_fuser} unc_ok=False no_running -> target={target}")
            elif is_fuser:
                # Fuser computer but in a mode we don't understand - use desired_ct to be safe
                target = desired_ct
                logging.info(f"[fuser-policy] policy: mode={work_mode} is_fuser={is_fuser} -> target={target} (fallback to desired)")
            else:
                target = 0
                logging.info(f"[fuser-policy] policy: mode={work_mode} is_fuser={is_fuser} -> target={target} (not a fuser PC)")

        # Throttle duplicate enforcements with the same target within a short window
        now = time.time()
        if _last_enforce_target == target and (now - _last_enforce_ts) < 8.0:
            logging.info(f"[fuser-policy] SKIP: recent identical target={target} within 8s window")
            return

        logging.info(f"[fuser-policy] EXECUTE: ensure_fuser_instances({target})")
        ensure_fuser_instances(target)
        _last_enforce_target = target
        _last_enforce_ts = now
        logging.info(f"[fuser-policy] COMPLETE: target={target} applied")
    except Exception as e:
        logging.error(f"[fuser-policy] EXCEPTION: {e}")
        pass

def _assert_shared_path_is_unc():
    """
    Startup self-heal check: Ensure the working fuser path is a valid UNC.
    
    If the path has drifted to a local folder (e.g., due to manual config edits
    or migration issues), this will attempt to auto-fix it back to the proper
    UNC path using the configured host_ip and share_name.
    
    Called during startup warmup before enforce_local_fuser_policy().
    """
    if not ENFORCE_SHARED_WORKING_ONLY:
        logging.info("[self-heal] ENFORCE_SHARED_WORKING_ONLY disabled, skipping check")
        return
    
    try:
        shared = working_fuser_unc()
        logging.info(f"[self-heal] Current working folder: {shared}")
        
        # Check if path is a valid UNC
        if shared and shared.startswith("\\\\"):
            logging.info("[self-heal] ✓ Working folder is already a UNC path")
            return
        
        # Path is NOT a UNC - attempt to fix it
        logging.warning(f"[self-heal] ✗ Working folder is NOT a UNC path: {shared}")
        
        # Get host IP and share name from config
        host_ip = config.get("Offline", "host_ip", fallback="").strip()
        share_name = config.get("Offline", "share_name", fallback="SharedMeshDrive").strip()
        
        if not host_ip:
            logging.error("[self-heal] Cannot fix: host_ip not configured")
            return
        
        # Rebuild the proper UNC path
        expected_unc = f"\\\\{host_ip}\\{share_name}\\WorkingFuser"
        logging.info(f"[self-heal] Attempting to fix to: {expected_unc}")
        
        # Update the config
        if "Offline" not in config:
            config["Offline"] = {}
        
        # Clear any local path that might be set
        if config.has_option("Offline", "local_data_root"):
            old_local = config.get("Offline", "local_data_root", fallback="")
            if old_local and not old_local.startswith("\\\\"):
                logging.info(f"[self-heal] Found local path in config: {old_local}")
                # We won't remove it entirely, but the UNC should take precedence
        
        # Ensure enabled flag is set
        config["Offline"]["enabled"] = "True"
        
        # Save and sync
        save_config()
        update_fuser_shared_path()
        
        # Verify the fix
        new_shared = working_fuser_unc()
        if new_shared and new_shared.startswith("\\\\"):
            logging.info(f"[self-heal] ✓ Successfully fixed to UNC: {new_shared}")
        else:
            logging.warning(f"[self-heal] ⚠ Fix incomplete, path is still: {new_shared}")
            
    except Exception as e:
        logging.error(f"[self-heal] Exception during path check: {e}")

def relaunch_fusers():
    """Restart local fusers to match the configured target count."""

    try:
        kill_fusers()
        enforce_local_fuser_policy()
    except Exception as e:
        pass

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

    save_config()

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
    # Ensure Network.host is set from Offline.host_ip for proper initialization
    try:
        host_ip = config.get("Offline", "host_ip", fallback="").strip()
        if host_ip:
            if "Network" not in config:
                config["Network"] = {}
            # Ensure Network.host matches Offline.host_ip for proper initialization
            if config.get("Network", "host", fallback="").strip() != host_ip:
                config["Network"]["host"] = host_ip
                save_config()
    except Exception as e:
        logging.warning(f"Failed to sync Network.host with Offline.host_ip: {e}")
    
    enforce_photomesh_settings()
    update_fuser_shared_path()
    
    # Optional: Seed fuser default when working UNC becomes valid
    try:
        wf_unc = working_fuser_unc()
        if wf_unc and wf_unc.startswith("\\\\"):
            # Only seed if the UNC is accessible (best effort, don't block UI)
            def _seed_in_background():
                try:
                    if quick_unc_check(wf_unc):
                        from update_photomesh_config import seed_fuser_default
                        seed_fuser_default(wf_unc)
                        logging.info(f"[apply_offline] Background fuser seeding completed for {wf_unc}")
                    else:
                        logging.info(f"[apply_offline] UNC not accessible, skipping background seeding: {wf_unc}")
                except Exception as e:
                    logging.warning(f"[apply_offline] Background fuser seeding failed: {e}")
            
            # Run seeding in background thread to avoid UI blocking
            run_in_thread(_seed_in_background)
    except Exception as e:
        logging.warning(f"[apply_offline] Failed to start background fuser seeding: {e}")
    
    # Create batch wrappers as a fallback method for reliable fuser launches
    try:
        # Only create batch wrappers if we have sufficient system resources
        memory_info = get_memory_usage()
        if 'percent' in memory_info and memory_info['percent'] > 85:
            logging.warning("[apply_offline] Skipping batch wrapper creation due to high memory usage")
        else:
            create_fuser_bat_wrappers()
    except Exception as e:
        logging.warning(f"Failed to create fuser batch wrappers: {e}")
        # Don't let this failure stop the application

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

    _assert_shared_path_is_unc()  # Self-heal check before enforcing policy
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
    selected_root = safe_filedialog_askdirectory(
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
    
    # Ask user about network type instead of auto-enabling offline mode
    network_choice = messagebox.askyesno(
        "Network Configuration", 
        f"This PC will be the HOST for WorkingFolder sharing.\n\n"
        f"Host: {host_name} ({host_ip})\n"
        f"Share: {share_root}\n\n"
        f"Network Type:\n"
        f"• YES = Standard Ethernet Network (recommended for switched networks)\n"
        f"• NO = Isolated/Offline LAN (for airgapped or direct-connected PCs)\n\n"
        f"Are you using a standard ethernet network with a switch/router?"
    )
    
    if "Offline" not in config:
        config["Offline"] = {}
    offline = config["Offline"]
    
    if network_choice:
        # Standard ethernet network - don't enable offline mode by default
        offline["enabled"] = "False"
        log_to_console("[first-run] Configured for standard ethernet network")
    else:
        # Isolated/offline LAN - enable offline mode
        offline["enabled"] = "True"
        log_to_console("[first-run] Configured for isolated/offline LAN")
    
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
            safe_messagebox_showwarning(
                "First-Run Setup",
                "Some installers reported issues:\n- " + "\n- ".join(failures) +
                "\n\nYou can retry from the Settings panel.",
            )

    log_to_console("[first-run] First-run setup completed.")

def first_run_setup_user(master=None) -> None:
    """Configure first-run defaults for non-host machines."""

    log_to_console("[first-run] Starting first-run USER configuration (no sharing)…")

    # Ask user about network type for client PCs too
    network_choice = messagebox.askyesno(
        "Client Network Configuration", 
        f"This PC will be a CLIENT connecting to a host's WorkingFolder.\n\n"
        f"Network Type:\n"
        f"• YES = Standard Ethernet Network (recommended for switched networks)\n"
        f"• NO = Isolated/Offline LAN (for airgapped or direct-connected PCs)\n\n"
        f"Are you using a standard ethernet network with a switch/router?\n\n"
        f"Note: You can configure the host IP later in Settings."
    )

    if "Offline" not in config:
        config["Offline"] = {}
    offline = config["Offline"]
    
    if network_choice:
        # Standard ethernet network 
        offline["enabled"] = "False"
        log_to_console("[first-run] Client configured for standard ethernet network")
    else:
        # Isolated/offline LAN - enable offline mode
        offline["enabled"] = "True"
        log_to_console("[first-run] Client configured for isolated/offline LAN")
    
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
    log_to_console("[first-run] User configuration saved. Configure host IP in Settings if needed.")

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
        safe_messagebox_showinfo("Settings", "Launch on startup ▶ Disabled")
    else:
        exe_path = sys.executable
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
        safe_messagebox_showinfo("Settings", "Launch on startup ▶ Enabled")

def toggle_close_on_launch():
    """Toggle whether the main window closes when you launch a tool."""
    enabled = not is_close_on_launch_enabled()
    config['General']['close_on_launch'] = str(enabled)
    save_config()
    status = "Enabled" if enabled else "Disabled"
    safe_messagebox_showinfo("Settings", f"Close on Software Launch? ▶ {status}")

# =============================================================================
# GENERIC COMMAND LAUNCH HELPERS
# =============================================================================
# Batch file creation and executable resolution utilities.
BATCH_FOLDER = os.path.join(_BUNDLE_DIR, "Autolaunch_Batchfiles")
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
    response = safe_messagebox_askyesno(
        f"Set {app_name} Path",
        f"Do you want to set the path for {app_name}?\n\nClick 'No' to skip.",
        icon='question'
    )
    if not response:
        return True 

    path = safe_filedialog_askopenfilename(
        title=f"Select {app_name} Executable",
        filetypes=[("Executable Files", "*.exe")]
    )
    if path and os.path.exists(path):
        config['General'][config_key] = clean_path(path)
        save_config()
        safe_messagebox_showinfo("Success", f"{app_name} path set to:\n{path}")
        return True
    else:
        safe_messagebox_showerror("Error", f"Invalid {app_name} path selected.")
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
            # Increased time budget for launcher search (needs to scan deeper folders)
            path = get_vbs4_launcher_path(time_budget_sec=2.5, allow_full_drive=False)
        else:
            path = find_executable(exe_name)
    else:
        for name in exe_name:
            low = name.lower()
            if low in ('vbslauncher.exe', 'vbs4launcher.exe'):
                # Increased time budget for launcher search (needs to scan deeper folders)
                path = get_vbs4_launcher_path(time_budget_sec=2.5, allow_full_drive=False)
            else:
                path = find_executable(name)
            if path:
                break

    if path and os.path.isfile(path):
        if config_key != 'vbs4_path':
            config['General'][config_key] = clean_path(path)
            save_config()
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
        if APP_INSTANCE:
            APP_INSTANCE.launch_app_foreground(path)
        else:
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
        save_config()

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
        # Use cmd /c to run .bat without shell=True (avoids console flash)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        subprocess.Popen(
            ["cmd", "/c", batch_file],
            creationflags=CREATE_NO_WINDOW,
            startupinfo=si
        )
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

background_image_path = os.path.join(_BUNDLE_DIR, "20240206_101613_026.jpg")
logo_STE_path         = os.path.join(_BUNDLE_DIR, "logos", "STE_CFT_Logo.png")
logo_AFC_army         = os.path.join(_BUNDLE_DIR, "logos", "US_Army_AFC_Logo.png")
logo_first_army       = os.path.join(_BUNDLE_DIR, "logos", "First_Army_Logo.png")
logo_us_army_path     = os.path.join(_BUNDLE_DIR, "logos", "New_US_Army_Logo.png")
prompt_box_image_path = os.path.join(_BUNDLE_DIR, "promptbox.jpg")
_cached_bg_photo = None
_cached_bg_size = (0, 0)
_PANEL_BG_WIDTH = 1920  # Fixed background width
_PANEL_BG_HEIGHT = 1080  # Fixed background height

def set_background(window, widget=None):
    """Apply a consistent-sized cached background to a widget."""
    global _cached_bg_photo, _cached_bg_size
    
    # Use fixed size so all panels have same background dimensions
    bg_width = _PANEL_BG_WIDTH
    bg_height = _PANEL_BG_HEIGHT

    # wallpaper - use cached version if already created
    if os.path.exists(background_image_path):
        if _cached_bg_photo is None or _cached_bg_size != (bg_width, bg_height):
            img = Image.open(background_image_path)
            img = img.resize((bg_width, bg_height), Image.Resampling.LANCZOS)
            _cached_bg_photo = ImageTk.PhotoImage(img)
            _cached_bg_size = (bg_width, bg_height)
        
        lbl = tk.Label(widget or window, image=_cached_bg_photo)
        lbl.image = _cached_bg_photo
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

# ─── UI Performance Helpers ──────────────────────────────────────────────────

def load_cached_image(path: str, size: tuple[int, int]) -> ImageTk.PhotoImage:
    """Load and cache resized images for better UI performance.
    
    Args:
        path: Absolute path to the image file
        size: Tuple of (width, height) for resizing
    
    Returns:
        Cached PhotoImage object
    
    This prevents repeated PIL resize operations by caching the result.
    Significantly improves panel switching and dialog creation speed.
    """
    global _IMAGE_CACHE
    cache_key = f"{path}_{size[0]}x{size[1]}"
    
    if cache_key not in _IMAGE_CACHE:
        if not os.path.exists(path):
            logging.warning(f"[ui-cache] Image not found: {path}")
            return None
        try:
            img = Image.open(path).resize(size, Image.Resampling.LANCZOS)
            _IMAGE_CACHE[cache_key] = ImageTk.PhotoImage(img)
            logging.debug(f"[ui-cache] Cached image: {cache_key}")
        except Exception as e:
            logging.error(f"[ui-cache] Failed to load {path}: {e}")
            return None
    
    return _IMAGE_CACHE[cache_key]

def add_button_hover_effect(button: tk.Button, normal_bg: str = "#444444", hover_bg: str = "#555555"):
    """Add smooth hover effect to a button for better visual feedback.
    
    Args:
        button: tkinter Button widget
        normal_bg: Normal background color (default: #444444)
        hover_bg: Hover background color (default: #555555)
    
    Makes the UI feel more responsive by providing immediate visual feedback.
    Only applies effect if button is not disabled.
    """
    def on_enter(event):
        if button['state'] != 'disabled':
            button.config(bg=hover_bg)
    
    def on_leave(event):
        if button['state'] != 'disabled':
            button.config(bg=normal_bg)
    
    button.bind("<Enter>", on_enter)
    button.bind("<Leave>", on_leave)

def set_busy_cursor(widget, busy: bool = True):
    """Set or clear busy cursor to indicate processing.
    
    Args:
        widget: tkinter widget (typically root window)
        busy: True to show wait cursor, False to restore normal cursor
    
    Provides visual feedback during blocking operations like file dialogs.
    Prevents users from thinking the app has frozen.
    """
    try:
        if busy:
            widget.config(cursor="wait")
        else:
            widget.config(cursor="")
    except Exception:
        pass  # Widget may be destroyed
    
# =============================================================================
# HELP/TUTORIALS & DOCUMENT OPENERS
# =============================================================================
# Static references and routines for help menus.

tutorials_items = {
    "VBS4 Documentation": lambda: launch_vbs4_documentation(),
    "Script Wiki":         lambda: launch_vbs4_script_wiki(),
    "BVI PDF Docs":        lambda: messagebox.showinfo("BVI Docs","Open BVI PDF docs"),
}
blueig_help_items = {
    "Blue IG Official Documentation": lambda: launch_blueig_documentation(),
    "Video Tutorials":                lambda: messagebox.showinfo("Coming Soon", "Not implemented yet"),
    "Support Website":                lambda: webbrowser.open("https://bisimulations.com/support/", new=2),
}
# ─── help MENUS ────────────────────────────
VBS4_HTML = r"C:\Builds\VBS4\VBS4 25.1 YYMEA_General\docs\VBS4_Manuals_EN.htm"
BlueIG_HTML = r"C:\Builds\BlueIG\Blue IG 24.2 YYMEA_General\docs\Blue_IG_EN.htm"
SCRIPT_WIKI  = r"C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\Help_Tutorials\Wiki\SQF_Reference.html"
SUPPORT_SITE = "https://bisimulations.com/support/"
STE_SMTP_KIT_GUIDE = os.path.join(_BUNDLE_DIR, "Help_Tutorials", "STE_SMTP_KIT_GUIDE.pdf")

# ─── Dynamic VBS4 Documentation Path Helpers ───────────────────────────────
def find_vbs4_documentation_path() -> str:
    """Find the VBS4_Manuals_EN.htm file dynamically based on VBS4 installation."""
    vbs4_exe = get_vbs4_install_path()
    if not vbs4_exe or not os.path.exists(vbs4_exe):
        return ""
    
    vbs4_dir = os.path.dirname(vbs4_exe)
    doc_path = os.path.join(vbs4_dir, "docs", "VBS4_Manuals_EN.htm")
    return doc_path if os.path.exists(doc_path) else ""

def find_vbs4_admin_manual_path() -> str:
    """Find the VBS4 Administrator Manual PDF dynamically based on VBS4 installation."""
    vbs4_exe = get_vbs4_install_path()
    if not vbs4_exe or not os.path.exists(vbs4_exe):
        return ""
    
    vbs4_dir = os.path.dirname(vbs4_exe)
    manual_path = os.path.join(vbs4_dir, "docs", "PDF_EN", "VBS4_Administrator_Manual.pdf")
    return manual_path if os.path.exists(manual_path) else ""

def find_vbs4_script_wiki_path() -> str:
    """Find the SQF Reference wiki dynamically based on VBS4 installation."""
    vbs4_exe = get_vbs4_install_path()
    if not vbs4_exe or not os.path.exists(vbs4_exe):
        # Fallback to local copy if VBS4 not found
        return SCRIPT_WIKI if os.path.exists(SCRIPT_WIKI) else ""
    
    vbs4_dir = os.path.dirname(vbs4_exe)
    wiki_path = os.path.join(vbs4_dir, "docs", "Wiki", "SQF_Reference.html")
    if os.path.exists(wiki_path):
        return wiki_path
    # Fallback to local copy
    return SCRIPT_WIKI if os.path.exists(SCRIPT_WIKI) else ""

def find_blueig_documentation_path() -> str:
    """Find the Blue_IG_EN.htm file dynamically based on BlueIG installation."""
    blueig_exe = get_blueig_install_path()
    if not blueig_exe or not os.path.exists(blueig_exe):
        return ""
    
    blueig_dir = os.path.dirname(blueig_exe)
    doc_path = os.path.join(blueig_dir, "docs", "Blue_IG_EN.htm")
    return doc_path if os.path.exists(doc_path) else ""

def launch_vbs4_documentation():
    """Launch VBS4 official documentation, finding the path dynamically."""
    doc_path = find_vbs4_documentation_path()
    if not doc_path:
        # Fallback to hardcoded path if dynamic search fails
        doc_path = VBS4_HTML
    
    if os.path.exists(doc_path):
        if APP_INSTANCE:
            APP_INSTANCE.launch_app_foreground(doc_path)
        else:
            # Open with default browser/viewer (no console window)
            os.startfile(doc_path)
    else:
        messagebox.showerror("Error", 
            f"VBS4 documentation not found.\n\n"
            f"Searched for: VBS4_Manuals_EN.htm\n"
            f"Expected location: <VBS4_Install>/docs/VBS4_Manuals_EN.htm\n\n"
            f"Please ensure VBS4 is properly installed and the path is set in Settings.")

def launch_vbs4_admin_manual():
    """Launch VBS4 Administrator Manual, finding the path dynamically."""
    manual_path = find_vbs4_admin_manual_path()
    
    if manual_path:
        if APP_INSTANCE:
            APP_INSTANCE.launch_app_foreground(manual_path)
        else:
            # Open with default PDF viewer (no console window)
            os.startfile(manual_path)
    else:
        messagebox.showerror("Error",
            f"VBS4 Administrator Manual not found.\n\n"
            f"Searched for: VBS4_Administrator_Manual.pdf\n"
            f"Expected location: <VBS4_Install>/docs/PDF_EN/VBS4_Administrator_Manual.pdf\n\n"
            f"Please ensure VBS4 is properly installed and the path is set in Settings.")

def launch_vbs4_script_wiki():
    """Launch VBS4 Script Wiki, finding the path dynamically."""
    wiki_path = find_vbs4_script_wiki_path()
    
    if os.path.exists(wiki_path):
        if APP_INSTANCE:
            APP_INSTANCE.launch_app_foreground(wiki_path)
        else:
            # Open with default browser (no console window)
            os.startfile(wiki_path)
    else:
        messagebox.showerror("Error",
            f"VBS4 Script Wiki not found.\n\n"
            f"Searched for: SQF_Reference.html\n"
            f"Expected locations:\n"
            f"  • <VBS4_Install>/docs/Wiki/SQF_Reference.html\n"
            f"  • {SCRIPT_WIKI}\n\n"
            f"Please ensure VBS4 is properly installed and the path is set in Settings.")

def launch_blueig_documentation():
    """Launch BlueIG official documentation, finding the path dynamically."""
    doc_path = find_blueig_documentation_path()
    if not doc_path:
        # Fallback to hardcoded path if dynamic search fails
        doc_path = BlueIG_HTML
    
    if os.path.exists(doc_path):
        if APP_INSTANCE:
            APP_INSTANCE.launch_app_foreground(doc_path)
        else:
            # Open with default browser (no console window)
            os.startfile(doc_path)
    else:
        messagebox.showerror("Error", 
            f"BlueIG documentation not found.\n\n"
            f"Searched for: Blue_IG_EN.htm\n"
            f"Expected location: <BlueIG_Install>/docs/Blue_IG_EN.htm\n\n"
            f"Please ensure BlueIG is properly installed and the path is set in Settings.")

# ─── PDF & VIDEO SUB-MENU DATA ───────────────────────────────────────────────
def open_vbs4_manuals():
    """Open VBS4 Manuals using dynamic path finding and foreground launch."""
    doc_path = find_vbs4_documentation_path()
    if doc_path:
        if APP_INSTANCE:
            APP_INSTANCE.launch_app_foreground(doc_path)
        else:
            # Open with default browser (no console window)
            os.startfile(doc_path)
    else:
        messagebox.showerror("Error", 
            "VBS4 Manuals not found.\n\n"
            "Expected location: <VBS4_Install>/docs/VBS4_Manuals_EN.htm\n\n"
            "Please ensure VBS4 is properly installed and the path is set in Settings.")

pdf_docs = {
    "SQF Wiki": lambda: webbrowser.open(
        os.path.join(_BUNDLE_DIR, "Help_Tutorials", "Wiki", "SQF_Reference.html"),
        new=2),
    "VBS4 Manuals": lambda: open_vbs4_manuals(),
}

# ─── VBS4 PDF Docs Helper ────────────────────────────────────────────────────

VBS4_PDF_DIR = os.path.join(BASE_DIR, "PDF_EN")

def find_vbs4_pdf_directories() -> list[str]:
    """Find potential VBS4 PDF directories, checking both local and VBS4 installation paths."""
    directories = []
    
    # Add local PDF_EN directory if it exists
    if os.path.exists(VBS4_PDF_DIR):
        directories.append(VBS4_PDF_DIR)
    
    # Add VBS4 installation PDF_EN directory if VBS4 is found
    vbs4_exe = get_vbs4_install_path()
    if vbs4_exe and os.path.exists(vbs4_exe):
        vbs4_pdf_dir = os.path.join(os.path.dirname(vbs4_exe), "docs", "PDF_EN")
        if os.path.exists(vbs4_pdf_dir) and vbs4_pdf_dir not in directories:
            directories.append(vbs4_pdf_dir)
    
    return directories

def open_vbs4_pdfs():
    """Scan VBS4 PDF folders and pop up a submenu of all the PDFs."""
    pdf_dirs = find_vbs4_pdf_directories()
    
    if not pdf_dirs:
        messagebox.showerror("Error", 
            f"VBS4 PDF folders not found.\n\n"
            f"Searched locations:\n"
            f"  • {VBS4_PDF_DIR}\n"
            f"  • <VBS4_Install>/docs/PDF_EN\n\n"
            f"Please ensure VBS4 is properly installed and the path is set in Settings.")
        return

    # Collect all PDFs from all directories
    all_pdfs = {}
    for pdf_dir in pdf_dirs:
        try:
            pdfs = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]
            for fname in pdfs:
                display = os.path.splitext(fname)[0].replace("_", " ")
                path = os.path.join(pdf_dir, fname)
                if display not in all_pdfs:
                    all_pdfs[display] = path
        except Exception as e:
            continue  # Skip directories that can't be read

    if not all_pdfs:
        messagebox.showerror("Error", "No PDF files found in VBS4 documentation folders.")
        return

    items = {}
    for display, path in sorted(all_pdfs.items()):
        items[display] = lambda p=path: (
            APP_INSTANCE.launch_app_foreground(p) if APP_INSTANCE and os.path.exists(p)
            else subprocess.Popen([p], shell=True) if os.path.exists(p)
            else messagebox.showerror("Error", f"File not found: {p}")
        )

video_items = {
    "VBS4 Video Tutorials":   lambda: messagebox.showinfo("VBS4 Videos", "Play VBS4 tutorial videos"),
    "BlueIG Video Tutorials": lambda: messagebox.showinfo("BlueIG Videos", "Play BlueIG tutorial videos"),
    "BVI Video Tutorials":    lambda: messagebox.showinfo("BVI Videos", "Play BVI tutorial videos"),
}
vbs4_help_items = {
    "VBS4 Official Documentation": lambda: launch_vbs4_documentation(),
    "VBS4 Admin Manual": lambda: launch_vbs4_admin_manual(),
    "Script Wiki": lambda: launch_vbs4_script_wiki(),
    "Video Tutorials":              lambda: messagebox.showinfo("Video Tutorials","Coming soon…"),
    "Support Website":              lambda: webbrowser.open(SUPPORT_SITE, new=2),
    "Gaming Help": lambda: webbrowser.open("https://example.com/vbs4-gaming-help", new=2),
}
def open_bvi_quickstart():
    # List of possible locations for the BVI technical document
    possible_paths = [
        os.path.join(_BUNDLE_DIR, "BVI_Documentation", "BVI_TECHNICAL_DOC.pdf"),
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
                if APP_INSTANCE:
                    APP_INSTANCE.launch_app_foreground(path)
                else:
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
        save_config()
        
        try:
            if APP_INSTANCE:
                APP_INSTANCE.launch_app_foreground(user_path)
            else:
                subprocess.Popen([user_path], shell=True)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open Quick-Start Guide:\n{e}")
    else:
        messagebox.showinfo("BVI Quick-Start Guide", "No file selected. The Quick-Start Guide will not be opened.")

def open_bvi_documentation():
    possible_paths = [
        os.path.join(_BUNDLE_DIR, "BVI_Documentation", "BVI_User_Instructions.pdf"),
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
                if APP_INSTANCE:
                    APP_INSTANCE.launch_app_foreground(path)
                else:
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
        save_config()
        
        try:
            if APP_INSTANCE:
                APP_INSTANCE.launch_app_foreground(user_path)
            else:
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

def find_reality_mesh_documentation_path() -> str:
    """Find the Reality_Mesh_EN.htm file using multiple search strategies."""
    # Try configured Reality Mesh local root first
    rm_root = get_rm_local_root()
    search_paths = []
    
    if rm_root and os.path.exists(rm_root):
        search_paths.append(rm_root)
    
    # Add common installation locations
    search_paths.extend([
        r"C:\Bohemia Interactive Simulations",
        r"C:\Program Files\Bohemia Interactive Simulations",
        r"C:\Program Files (x86)\Bohemia Interactive Simulations",
    ])
    
    # Also check ProgramData
    program_data = os.environ.get("ProgramData", "")
    if program_data:
        search_paths.append(os.path.join(program_data, "Bentley"))
    
    return _find_file("Reality_Mesh_EN.htm", search_paths)

def open_reality_mesh_docs():
    """Open the Reality Mesh HTML help documentation."""
    path = find_reality_mesh_documentation_path()
    if path:
        if APP_INSTANCE:
            APP_INSTANCE.launch_app_foreground(path)
        else:
            subprocess.Popen([path], shell=True)
    else:
        messagebox.showerror("Error", 
            "Reality Mesh documentation not found.\n\n"
            "Searched for: Reality_Mesh_EN.htm\n"
            "Expected locations:\n"
            "  • Reality Mesh local root (if configured)\n"
            r"  • C:\Bohemia Interactive Simulations" + "\n"
            r"  • C:\Program Files\Bohemia Interactive Simulations" + "\n"
            r"  • C:\Program Files (x86)\Bohemia Interactive Simulations" + "\n\n"
            "Please ensure Reality Mesh is properly installed.")

def open_photomesh_help():
    """Open the PhotoMesh help PDF, searching development and production paths."""
    roots = [
        os.path.join(BASE_DIR, "Help_Tutorials"),
        r"C:\\Program Files (x86)\\STE Toolkit\\_internal\\Help_Tutorials",
    ]
    path = _find_file("PM804_Wizard_141_Training.pdf", roots)
    if path:
        try:
            if APP_INSTANCE:
                APP_INSTANCE.launch_app_foreground(path)
            else:
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
        save_config()
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
        save_config()
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
    save_config()

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
        save_config()
        messagebox.showinfo("Settings", f"VBS4 path set to:\n{path}")
    else:
        messagebox.showerror("Settings", "Invalid VBS4 path selected.")

def set_ares_manager_path():
    path = filedialog.askopenfilename(title="Select ARES Manager.exe", filetypes=[("Executable", "*.exe")])
    if path:
        config['General']['bvi_manager_path'] = path
        save_config()
        messagebox.showinfo("Settings", f"ARES Manager path set to:\n{path}")
    else:
        messagebox.showinfo("Settings", "No ARES Manager path selected.")

def select_vbs_map_profile():
    """Prompt user to set VBS Map profile/username."""
    username = simpledialog.askstring(
        "VBS Map Profile",
        "Enter VBS Map username:",
        initialvalue=config['General'].get('vbs_map_user', '')
    )
    if username:
        config['General']['vbs_map_user'] = username.strip()
        save_config()
        messagebox.showinfo("VBS Map", f"VBS Map username set to: {username}")
    else:
        messagebox.showinfo("VBS Map", "No username entered.")

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
        # Use cached image for better performance
        ph = load_cached_image(prompt_box_image_path, (801, 506))
        if ph:
            lbl = tk.Label(top, image=ph)
            lbl.image = ph
            lbl.place(relwidth=1, relheight=1)
        else:
            top.configure(bg="#333333")
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
        # Use cached image for better performance
        ph = load_cached_image(prompt_box_image_path, (801, 506))
        if ph:
            lbl = tk.Label(top, image=ph)
            lbl.image = ph
            lbl.place(relwidth=1, relheight=1)
        else:
            top.configure(bg="#333333")
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

# ============================================================================
# MAIN APPLICATION CLASS
# ============================================================================

class MainApp(tk.Tk):
    """
    STE Toolkit main application window.
    
    Provides tabbed interface for:
    - One-Click: Launch VBS4, BlueIG, BVI with automated configuration
    - PhotoMesh: Manage terrain processing and fuser instances
    - Reality Mesh: Control 3D mesh datasets and integration
    - Settings: Configure network paths, executables, and system behavior
    
    Features:
    - Fullscreen mode with ESC key support
    - Network status monitoring (online/offline modes)
    - Splash screen with progress tracking
    - Memory optimization and resource management
    - Thread-safe UI updates via message queue
    """
    
    def __init__(self):
        super().__init__()
        global APP_INSTANCE
        APP_INSTANCE = self
        
        # Start hidden to prevent window flash during initialization
        self.withdraw()
        
        apply_app_icon(self)
        self.title("STE Mission Planning Toolkit")
        self.resizable(False, False)

        # Register cleanup handler for window close
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Track focusable UI elements for keyboard navigation
        self.focusable_buttons = []

        self.fullscreen = config.getboolean('General', 'fullscreen', fallback=False)
        
        # UI initialization state flag
        self._ui_initialized = False
        
        # Network connectivity state
        self.network_status = "unknown"  # States: "online", "offline", "unknown"
        
        # Start UI message queue pump
        self.after(0, pump_ui_queue, self)

        # Splash screen reference (attached externally)
        self._splash = None

    def attach_splash(self, splash: SplashScreen | None):
        """Attach existing splash screen and maintain focus on main window."""
        self._splash = splash
        try:
            self.focus_force()
        except Exception:
            pass

    def _splash_message(self, msg: str):
        """Update splash screen progress message if active."""
        if self._splash:
            try:
                self._splash.set_message(msg)
            except Exception:
                pass
                
    def _update_splash_progress(self, value: float):
        """Update the splash screen progress bar."""
        if self._splash:
            try:
                self._splash.set_progress(value)
            except Exception:
                pass

    def _ensure_splash_gone(self):
        """Hide & destroy any splash window so it can't reappear on WM changes.
        Only targets splash screens that should already be closed from startup."""
        # 1) If we still have a handle to a splash that should be closed, clean it up
        sp = getattr(self, "_splash", None)
        if sp and sp.winfo_exists():
            try:
                sp.attributes("-topmost", False)
            except Exception:
                pass
            try:
                sp.withdraw()   
            except Exception:
                pass
            try:
                sp.destroy()   
            except Exception:
                pass
            if self._splash is sp:      # clear only after the window is really gone
                self._splash = None
        elif sp is not None and not sp.winfo_exists():
            # If the splash has already been destroyed elsewhere, clear the handle
            self._splash = None

        # 2) Clean up any orphan splash toplevels that are already marked for closing
        try:
            for w in self.winfo_children():
                if (isinstance(w, tk.Toplevel) and getattr(w, "_is_splash", False)):
                    try:
                        w.destroy()
                    except Exception:
                        pass
        except Exception:
            pass
    
    def show_warning_banner(self, message: str):
        """Show a warning banner for offline mode or network issues."""
        try:
            if hasattr(self, '_ui_initialized') and self._ui_initialized:
                # Show warning in main UI if available
                # This could be enhanced with a banner widget
                logging.warning(f"[MainApp] {message}")
            else:
                # Just log if UI not ready yet
                logging.warning(f"[MainApp] {message}")
        except Exception as e:
            logging.error(f"Failed to show warning banner: {e}")

    # --- UI initialization (deferred until after splash) -------------------
    def _build_header(self):
        """Build the header bar with logos and title. Safe to call multiple times."""
        # If we somehow already have a header, don't build another.
        if getattr(self, "header_bar", None) and self.header_bar.winfo_exists():
            logging.info("[ui-diag] header already exists; skipping")
            return

        logging.info("[ui-diag] Building header once")
        self.header_bar = tk.Frame(self, bg="black", height=120)

        # Prefer to place the header above main content; fall back only if needed.
        try:
            # Requires self.content to be packed already
            self.header_bar.pack(side="top", fill="x", before=self.content)
        except Exception as e:
            # Only pack if it's not already mapped (prevents double pack)
            if not self.header_bar.winfo_ismapped():
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

    def _initialize_ui(self):
        """Initialize the main UI components. Called after splash is shown."""
        # Double guard: both _ui_built and _ui_initialized
        if getattr(self, "_ui_built", False):
            logging.info("[startup] _initialize_ui() called again; skipping")
            return
        self._ui_built = True
        
        if self._ui_initialized:
            logging.info("[startup] UI already initialized, skipping")
            return
        
        try:
            logging.info("[startup] Starting UI initialization")
            logging.info("[ui-diag] About to create close button")
        except:
            pass
            
        # Create the main UI layout
        nav_labels = {
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
        logging.info("[ui-diag] Close button created")
        close_btn.place(relx=1.0, x=-40, y=5, width=30, height=30)
        logging.info("[ui-diag] Close button placed")
        self.configure(bg="black")
        logging.info("[ui-diag] Background configured")
        self.content = tk.Frame(self, bg="black", bd=0, highlightthickness=0)
        logging.info("[ui-diag] Content frame created")
        self.content.pack(expand=True, fill="both")
        logging.info("[ui-diag] Content frame packed")
        nav = tk.Frame(self.content, bg='#333333')
        logging.info("[ui-diag] Nav frame created")
        nav.pack(side='left', fill='y')
        logging.info("[ui-diag] Nav frame packed")
        self._init_scrollable_viewport()
        logging.info("[ui-diag] Scrollable viewport initialized")
        logging.info("[ui-diag] About to create panels (this may take time)...")
        logging.info("[ui-diag] Creating MainMenu panel...")
        main_panel = MainMenu(self.panels_container, self)
        logging.info("[ui-diag] MainMenu panel created")
        logging.info("[ui-diag] Creating VBS4Panel...")
        vbs4_panel = VBS4Panel(self.panels_container, self)
        logging.info("[ui-diag] VBS4Panel created")
        logging.info("[ui-diag] Creating OneClickPanel...")
        oneclick_panel = OneClickPanel(self.panels_container, self)
        logging.info("[ui-diag] OneClickPanel created")
        logging.info("[ui-diag] Creating BVIPanel...")
        bvi_panel = BVIPanel(self.panels_container, self)
        logging.info("[ui-diag] BVIPanel created")
        logging.info("[ui-diag] Creating SettingsPanel...")
        settings_panel = SettingsPanel(self.panels_container, self)
        logging.info("[ui-diag] SettingsPanel created")
        logging.info("[ui-diag] Creating TutorialsPanel...")
        tutorials_panel = TutorialsPanel(self.panels_container, self)
        logging.info("[ui-diag] TutorialsPanel created")
        logging.info("[ui-diag] Creating CreditsPanel...")
        credits_panel = CreditsPanel(self.panels_container, self)
        logging.info("[ui-diag] CreditsPanel created")
        logging.info("[ui-diag] Creating ContactSupportPanel...")
        contact_panel = ContactSupportPanel(self.panels_container, self)
        logging.info("[ui-diag] ContactSupportPanel created")
        logging.info("[ui-diag] All panels created successfully, assembling dictionary...")
        self.panels = {
            'Main':      main_panel,
            'VBS4':      vbs4_panel,
            'OneClick':  oneclick_panel,
            'BVI':       bvi_panel,
            'Settings':  settings_panel,
            'Tutorials': tutorials_panel,
            'Credits':   credits_panel,
            'Contact Us': contact_panel,
        }
        logging.info("[ui-diag] Panels dictionary assembled")

        logging.info("[ui-diag] About to call enforce_photomesh_settings()")
        try:
            log_fn = self.panels.get('OneClick').log_message if 'OneClick' in self.panels else print
            enforce_photomesh_settings(log=log_fn)
        except Exception as exc:
            logging.warning(f"[ui-diag] enforce_photomesh_settings() failed: {exc}")
            pass
        logging.info("[ui-diag] enforce_photomesh_settings() complete")
        logging.info("[ui-diag] About to pack_forget all panels")
        for panel in self.panels.values():
            panel.pack_forget()
        logging.info("[ui-diag] All panels pack_forget() complete")

        # Build the nav buttons
        nav_tip = Tooltip(nav)
        self._nav_buttons = {}  # Store button references for visual updates
        
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
            def make_command(k):
                """Create command function with immediate visual feedback."""
                def cmd():
                    self.after_idle(lambda: self.show(k))
                return cmd
            
            btn = tk.Button(nav, text=label,
                            font=("Helvetica", 18),
                            bg="#555", fg="white",
                            activebackground="#777",  # Better hover color
                            activeforeground="white",
                            relief="raised",
                            bd=2,
                            width=12,
                            command=make_command(key))
            btn.pack(pady=5, padx=5)
            self._nav_buttons[key] = btn
            
            # Enhanced hover effects for better feedback
            def on_enter(e, btn=btn, l=label):
                if not hasattr(self, 'current') or self.current != key:
                    btn.config(bg="#777")
                nav_tip.show(f"Go to {l}", e.x_root+10, e.y_root+10)
            
            def on_leave(e, btn=btn, k=key):
                if hasattr(self, 'current') and self.current == k:
                    btn.config(bg="#888") 
                else:
                    btn.config(bg="#555")  # Normal color
                nav_tip.hide()
            
            def on_click(e, btn=btn, k=key):
                # Immediate visual feedback on click
                btn.config(bg="#999")
                # Update all button states after a brief moment
                btn.after(50, self.update_nav_button_appearance)
            
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            btn.bind("<Button-1>", on_click)
            self.focusable_buttons.append(btn)

        tk.Button(nav, text="Exit", font=("Helvetica", 18),
                  bg="red", fg="white", command=self.destroy) \
            .pack(fill='x', pady=20, padx=5)
        tk.Label(nav, text="Use \u2191/\u2193 arrows to navigate",
                 bg="#333333", fg="white",
                 font=("Helvetica", 10)).pack(pady=(0, 10))

        logging.info("[ui-diag] Skipping enforce_local_fuser_policy() during UI init (will auto-start at 3s mark)")

        logging.info("[ui-diag] About to call apply_offline_settings()")
        try:
            apply_offline_settings()
        except Exception as exc:
            logging.warning(f"[ui-diag] apply_offline_settings() failed: {exc}")
            pass
        logging.info("[ui-diag] apply_offline_settings() complete")

        # Start by showing "Main"
        logging.info("[ui-diag] About to show Main panel")
        self.current = None
        self.show('Main')
        logging.info("[ui-diag] Main panel shown")

        # --- Keyboard navigation setup ---
        self.focus_index = 0
        for key in ("<Right>", "<Down>"):
            self.bind(key, self.focus_next)
        for key in ("<Left>", "<Up>"):
            self.bind(key, self.focus_prev)
        self.bind("<Return>", self.activate_current)
        self.update_navigation()
        
        # Mark UI as initialized
        self._ui_initialized = True
        logging.info("[ui-diag] UI initialization complete, flag set to True")

    # ---- Foreground handoff + foreground launch helpers (Windows-safe) ----
    def _handoff_foreground(self):
        """Prepare so the next launched process/window can appear above us."""
        # Never keep the main window topmost.
        try:
            self.attributes('-topmost', False)
        except Exception:
            pass

    def _ensure_dialog_visibility(self):
        """Minimal dialog visibility management - just ensure focus."""
        try:
            # Just ensure main window is ready for dialog parenting
            self.update_idletasks()
        except Exception:
            pass

    def _restore_window_state(self):
        """Minimal window state restoration."""
        try:
            # Just ensure main window regains focus after dialog
            self.after_idle(lambda: self.focus_set())
        except Exception:
            pass

    # ---- Dialog wrapper methods for proper visibility ----
    def safe_messagebox_showerror(self, title, message, **kwargs):
        """Show error messagebox with proper window management."""
        self._ensure_dialog_visibility()
        try:
            result = messagebox.showerror(title, message, parent=self, **kwargs)
        finally:
            self._restore_window_state()
        return result

    def safe_messagebox_showwarning(self, title, message, **kwargs):
        """Show warning messagebox with proper window management."""
        self._ensure_dialog_visibility()
        try:
            result = messagebox.showwarning(title, message, parent=self, **kwargs)
        finally:
            self._restore_window_state()
        return result

    def safe_messagebox_showinfo(self, title, message, **kwargs):
        """Show info messagebox with proper window management."""
        self._ensure_dialog_visibility()
        try:
            result = messagebox.showinfo(title, message, parent=self, **kwargs)
        finally:
            self._restore_window_state()
        return result

    def safe_messagebox_askyesno(self, title, message, **kwargs):
        """Show yes/no messagebox with proper window management."""
        self._ensure_dialog_visibility()
        try:
            result = messagebox.askyesno(title, message, parent=self, **kwargs)
        finally:
            self._restore_window_state()
        return result

    def safe_filedialog_askdirectory(self, **kwargs):
        """Show directory dialog with proper window management and busy cursor feedback."""
        self._ensure_dialog_visibility()
        set_busy_cursor(self, True)  # Show wait cursor
        try:
            kwargs.setdefault('parent', self)
            result = filedialog.askdirectory(**kwargs)
        finally:
            set_busy_cursor(self, False)  # Restore normal cursor
            self._restore_window_state()
        return result

    def safe_filedialog_askopenfilename(self, **kwargs):
        """Show open file dialog with proper window management and busy cursor feedback."""
        self._ensure_dialog_visibility()
        set_busy_cursor(self, True)  # Show wait cursor
        try:
            kwargs.setdefault('parent', self)
            result = filedialog.askopenfilename(**kwargs)
        finally:
            set_busy_cursor(self, False)  # Restore normal cursor
            self._restore_window_state()
        return result

    def safe_simpledialog_askstring(self, title, prompt, **kwargs):
        """Show string input dialog with proper window management."""
        self._ensure_dialog_visibility()
        try:
            kwargs.setdefault('parent', self)
            result = simpledialog.askstring(title, prompt, **kwargs)
        finally:
            self._restore_window_state()
        return result
        if sys.platform == 'win32':
            self._win_drop_topmost(self.winfo_id())
            self._win_allow_next_foreground()

    def _win_allow_next_foreground(self):
        """Allow any process to take foreground next (Windows focus rules)."""
        try:
            ctypes.windll.user32.AllowSetForegroundWindow(-1)  
        except Exception:
            pass

    def _win_drop_topmost(self, hwnd):
        """Make sure our window is not topmost (defensive)."""
        try:
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            HWND_NOTOPMOST = -2
            ctypes.windll.user32.SetWindowPos(
                ctypes.wintypes.HWND(hwnd),
                ctypes.wintypes.HWND(HWND_NOTOPMOST),
                0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
            )
        except Exception:
            pass

    def open_folder_foreground(self, path: str):
        """Open a folder so Explorer surfaces above the fullscreen Toolkit."""
        if not path or not os.path.exists(path):
            messagebox.showerror("Open Folder", "Folder not found.")
            return
        self._handoff_foreground()
        try:
            if sys.platform == 'win32':
                # Use START to promote Explorer window to foreground
                # Note: do NOT use shell=True; call cmd explicitly
                subprocess.Popen(['cmd', '/c', 'start', '', path], close_fds=True)
            else:
                # macOS/Linux fallbacks
                if sys.platform == 'darwin':
                    subprocess.Popen(['open', path])
                else:
                    subprocess.Popen(['xdg-open', path])
        except Exception as e:
            messagebox.showerror("Open Folder", f"Could not open:\n{path}\n\n{e}")

    def launch_app_foreground(self, exe: str, args=None, cwd=None):
        """Launch an app so it becomes the foreground window."""
        args = args or []
        if not exe:
            messagebox.showerror("Launch", "Executable not set.")
            return
        self._handoff_foreground()
        try:
            if sys.platform == 'win32':
                # START activates the new GUI app window
                subprocess.Popen(['cmd', '/c', 'start', '', exe, *args], cwd=cwd, close_fds=True)
            else:
                subprocess.Popen([exe, *args], cwd=cwd, close_fds=True)
        except FileNotFoundError:
            messagebox.showerror("Launch", f"Not found:\n{exe}")
        except OSError as e:
            messagebox.showerror("Launch", f"Launch failed:\n{exe}\n\n{e}")

    def start_warmup_async(self):
        """Kick off background warm-up; close splash when done."""
        self._splash_closed = False
        self._splash_close_reason = None
        def _run():
            try:
                warm_up_environment(
                    progress=lambda m: post_ui(self._splash_message, m),
                    update_progress=lambda v: post_ui(self._update_splash_progress, v)
                )
                post_ui(lambda: self._finish_warmup(reason="warmup-complete"))
            except Exception as e:
                logging.error(f"[startup] warmup thread error: {e}")
                post_ui(lambda: self._finish_warmup(reason="warmup-error"))
        run_in_thread(_run)
        
        # Schedule background indexer to run after splash is closed
        self.after(5000, lambda: run_in_thread(_background_index_paths))

        # Hard failsafe: ensure splash closes even if warmup stalls (reduced from 9s to 5s)
        def failsafe_check():
            if not self._splash_closed:
                logging.warning("[startup] Failsafe triggered - forcing splash close")
                self._finish_warmup(reason="failsafe")
        self.after(5000, failsafe_check)

    def _finish_warmup(self, reason: str = "unknown"):
        """Complete warm-up and close the splash screen with proper timing.

        reason: 'warmup-complete' or 'failsafe' (telemetry for diagnostics)
        """
        try:
            logging.info(f"[startup] _finish_warmup called, reason={reason}, already_closed={getattr(self, '_splash_closed', False)}")
        except:
            pass
        if getattr(self, '_splash_closed', False) and reason != "warmup-complete":
            # Already finalized via normal path; ignore redundant failsafe
            return
        self._splash_closed = True
        self._splash_close_reason = reason
        logging.info(f"[startup] splash-closed reason={reason}")
        # Initialize the UI first (this was previously in __init__)
        logging.info("[startup] About to call _initialize_ui()")
        self._initialize_ui()
        logging.info("[startup] _initialize_ui() completed successfully")
        
        # Update panel button states now that warmup has discovered paths
        self._refresh_panel_button_states()
        
        # Check if we're in offline mode and show appropriate warning
        if hasattr(self, 'network_status') and self.network_status == "offline":
            self.show_warning_banner("Host not reachable — running in offline mode")
        
        # Start memory monitoring
        start_memory_monitoring()
        
        # Initial memory optimization
        optimize_memory()
        
        # Close PyInstaller's native splash if present
        if pyi_splash:
            try:
                pyi_splash.close()
            except Exception:
                pass
                
        if self._splash:
            # Final message before closing
            try:
                self._splash.set_message("Ready to launch")
            except Exception:
                pass
            try:
                # The close method respects the minimum display time
                self._splash.close()
            except Exception:
                pass
            self.after(0, self._ensure_splash_gone)
            self.after(750, self._ensure_splash_gone)
                
        # Now that the splash is closed, show the main window with fade-in to prevent UI flash
        try:
            logging.info("[startup] About to set alpha=0.0")
            self.attributes('-alpha', 0.0)  # Start invisible
            logging.info("[startup] About to deiconify()")
            self.deiconify()
            logging.info("[startup] Deiconify() completed, calling update_idletasks()")
            self.update_idletasks()  # Let everything layout once
            logging.info("[startup] update_idletasks() completed, scheduling fade-in")
            self.after(50, lambda: self.attributes('-alpha', 1.0))  # Fade in after 50ms
            # Failsafe: ensure window is fully visible after 200ms
            self.after(200, lambda: self.attributes('-alpha', 1.0))
            logging.info("[startup] Main window deiconified and fade-in scheduled")

            # If a post-UI autostart scheduler was registered, trigger it now
            try:
                cb = getattr(self, "_schedule_post_ui_autostart", None)
                if callable(cb):
                    # Run shortly after the UI is visible so the message appears after splash
                    self.after(100, cb)
                    try:
                        delattr(self, "_schedule_post_ui_autostart")
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception as e:
            logging.error(f"[startup] Error showing main window: {e}")
            # Fallback: just show the window without fade
            try:
                self.attributes('-alpha', 1.0)
                self.deiconify()
            except:
                pass

        # base windowed size and scaling
        self.base_width, self.base_height = 1760, 900  
        self.base_scaling = float(self.tk.call('tk', 'scaling'))

        # screen dims
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        # scale and geometry for windowed mode so it always fits on screen
        self.window_scale = min(sw / self.base_width, sh / self.base_height, 1.0)
        win_w = int(self.base_width * self.window_scale)
        win_h = int(self.base_height * self.window_scale)
        
        # Schedule periodic memory cleanup (every 30 seconds)
        self._schedule_memory_cleanup()
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
            pass
        self.log_message = log_message

        def _on_configure(event=None):
            if self._cfg_job is not None:
                self.after_cancel(self._cfg_job)
            self._cfg_job = self.after(10, self._recompute_scale)  

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

        # Build the header bar (safe to call, checks if already exists)
        self._build_header()

    def apply_scale(self, scale: float) -> None:
        """Scale fonts and widgets proportionally using Tk scaling."""
        snapped = round(scale * 4) / 4.0
        self.tk.call('tk', 'scaling', self.base_scaling * snapped)

    def toggle_fullscreen(self):
        """Toggle fullscreen while maintaining aspect ratio, and make sure
        the splash can never resurface during WM state changes."""
        # Close PyInstaller's native splash immediately if present
        if pyi_splash:
            try:
                pyi_splash.close()
            except Exception:
                pass
                
        # Only clean up splash if there's actually one that should be closed
        if hasattr(self, '_splash') and self._splash:
            # Check if splash should already be closed before cleaning up
            if getattr(self._splash, "_ready_to_close", False) or getattr(self._splash, "_closing", False):
                self._ensure_splash_gone()

        self.fullscreen = not self.fullscreen
        config.setdefault('General', {})['fullscreen'] = 'True' if self.fullscreen else 'False'
        _save_config()

        # Compute/restore geometry exactly as you already do
        if self.fullscreen:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            scale = min(sw / self.base_width, sh / self.base_height)
            self.apply_scale(scale)
            self.geometry(f"{sw}x{sh}+0+0")
            self.attributes('-fullscreen', True)   # enter fullscreen
        else:
            self.attributes('-fullscreen', False)  # leave fullscreen first
            # windowed_geometry is already computed in _finish_warmup
            self.apply_scale(self.window_scale)
            self.geometry(self.windowed_geometry)

        # After WM changes settle, do a final check only if needed
        if hasattr(self, '_splash') and self._splash:
            if getattr(self._splash, "_ready_to_close", False) or getattr(self._splash, "_closing", False):
                self.after_idle(self._ensure_splash_gone)
                self.after(50, self._ensure_splash_gone)

        # Belt-and-suspenders: make sure no stray splash can repaint after WM state changes
        self.after_idle(self._ensure_splash_gone)

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
            # Guard against early calls before GUI is fully initialized
            if not hasattr(self, 'panels') or not hasattr(self, 'current'):
                return
                
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
            logging.warning("Error in _update_scrollability: %s", e)
            if not self._scrollbar_shown:
                self._place_overlay_scrollbar()
                self._scrollbar_shown = True

    def _reset_viewport_scroll(self):
        """Reset viewport scroll position to top."""
        self.viewport_canvas.yview_moveto(0)

    def update_button_state(self, button, path_key):
        """Update button state based on whether the executable exists."""
        path = config['General'].get(path_key, '')
        if path and os.path.exists(path):
            button.config(state="normal")
        else:
            button.config(state="disabled")

    def show(self, name):
        """Display the named panel, repacking it inside the scroll viewport."""
        logging.info(f"[ui-diag] show() called for panel: {name}")
        panel = self.panels[name]
        logging.info(f"[ui-diag] show(): got panel object")
        try:
            subtitle = self._panel_subtitles.get(name, name)
            self.header_subtitle.config(text=subtitle)
        except Exception:
            pass
        logging.info(f"[ui-diag] show(): subtitle set")
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
        logging.info(f"[ui-diag] show(): about to pack panel")
        panel.pack(fill='both', expand=True)
        logging.info(f"[ui-diag] show(): panel packed")
        self.current = name
        self._reset_viewport_scroll()
        logging.info(f"[ui-diag] show(): viewport scroll reset")
        
        # Immediate layout update for faster visual response
        logging.info(f"[ui-diag] show(): about to call update_idletasks()")
        self.update_idletasks()
        logging.info(f"[ui-diag] show(): update_idletasks() complete")
        
        # Resize canvas immediately for instant feedback
        self._resize_canvas_to_panel(panel)
        logging.info(f"[ui-diag] show(): canvas resized")
        
        # Update navigation state immediately
        self.update_navigation()
        
        # Update visual state of navigation buttons
        self.update_nav_button_appearance()
        
        # Panel-specific updates - defer heavy operations to avoid blocking UI
        if name == "VBS4":
            self.after_idle(lambda: self._update_vbs4_panel(panel))
        elif name == "OneClick":
            self.after_idle(lambda: self._update_oneclick_panel(panel))
        elif name == "BVI":
            self.after_idle(lambda: self._update_bvi_panel(panel))
        
        # Defer scrollability checks to avoid blocking initial display
        self.after_idle(self._update_scrollability)
        self.after(50, self._update_scrollability)  # Reduced from 100, 300
        
        # Restore safe scaling: defer recompute slightly so initial display isn't blocked
        try:
            self.after_idle(self._recompute_scale)
            self.after(20, self._recompute_scale)
        except Exception:
            pass

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
            pass

    def _refresh_panel_button_states(self):
        """Refresh all panel button states after warmup discovers paths."""
        try:
            # Update VBS4 panel buttons if they exist
            if hasattr(self, 'panels') and 'VBS4' in self.panels:
                panel = self.panels['VBS4']
                if hasattr(panel, 'vbs4_launcher_button'):
                    self.update_button_state(panel.vbs4_launcher_button, 'vbs4_setup_path')
                if hasattr(panel, 'vbs_license_button'):
                    self.update_button_state(panel.vbs_license_button, 'vbs_license_manager_path')
                if hasattr(panel, 'blueig_button'):
                    self.update_button_state(panel.blueig_button, 'blueig_path')
            
            # Update BVI panel button if it exists
            if hasattr(self, 'panels') and 'BVI' in self.panels:
                panel = self.panels['BVI']
                if hasattr(panel, 'bvi_button'):
                    self.update_button_state(panel.bvi_button, 'bvi_manager_path')
        except Exception as e:
            logging.error(f"[startup] Error refreshing panel button states: {e}")

    def _update_vbs4_panel(self, panel):
        """Update VBS4 panel state (deferred to avoid blocking UI)."""
        try:
            panel.update_vbs4_version()
            self.update_button_state(panel.vbs4_launcher_button, 'vbs4_setup_path')
            self.update_button_state(panel.vbs_license_button, 'vbs_license_manager_path')
            self.update_button_state(panel.blueig_button, 'blueig_path')
        except Exception:
            pass

    def _update_oneclick_panel(self, panel):
        """Update OneClick panel state (deferred to avoid blocking UI)."""
        try:
            panel.update_fuser_state()
            panel.refresh_rm_status()
        except Exception:
            pass

    def _update_bvi_panel(self, panel):
        """Update BVI panel state (deferred to avoid blocking UI)."""
        try:
            self.update_button_state(panel.bvi_button, 'bvi_manager_path')
        except Exception:
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

    def update_nav_button_appearance(self):
        """Update navigation buttons to show which panel is currently active."""
        if not hasattr(self, '_nav_buttons'):
            return
        
        current_panel = getattr(self, 'current', None)
        for key, btn in self._nav_buttons.items():
            if key == current_panel:
                btn.config(bg="#888", relief="sunken")  # Active panel
            else:
                btn.config(bg="#555", relief="raised")  # Inactive panels

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
            save_config()
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

    def _schedule_memory_cleanup(self):
        """Schedule periodic memory cleanup."""
        try:
            # Run memory cleanup
            periodic_memory_cleanup()
            
            # Schedule next cleanup in 30 seconds (30000 ms)
            self.after(30000, self._schedule_memory_cleanup)
            
        except Exception as e:
            logging.error(f"[memory] Memory cleanup scheduling failed: {e}")
            # Try to reschedule anyway in 60 seconds
            self.after(60000, self._schedule_memory_cleanup)

    def force_memory_optimization(self):
        """Manually trigger memory optimization - can be called from UI."""
        try:
            freed = optimize_memory()
            memory_info = get_memory_usage()
            
            message = f"Memory optimization completed.\nFreed {freed} objects."
            if 'percent' in memory_info:
                message += f"\nCurrent memory usage: {memory_info['percent']:.1f}%"
            
            # Use safe messagebox if in fullscreen
            if hasattr(self, 'fullscreen') and self.fullscreen:
                safe_messagebox_showinfo("Memory Optimization", message)
            else:
                messagebox.showinfo("Memory Optimization", message)
                
        except Exception as e:
            logging.error(f"[memory] Manual optimization failed: {e}")
            error_msg = f"Memory optimization failed: {e}"
            if hasattr(self, 'fullscreen') and self.fullscreen:
                safe_messagebox_showerror("Memory Error", error_msg)
            else:
                messagebox.showerror("Memory Error", error_msg)

    def on_closing(self):
        """Handle window close event - kill fusers if this is a fuser computer."""
        try:
            # Clear offline IP configuration to prevent repeated connection attempts
            clear_offline_ip_configuration()
            logging.info("[on_closing] Cleared offline configuration on exit")
        except Exception as e:
            logging.error(f"[on_closing] Failed to clear offline configuration: {e}")
        
        try:
            kill_all_fusers_on_exit()
        except Exception as e:
            pass
        finally:
            self.destroy()

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
            bg="black",
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
                width=25, height=2,
                command=cmd,
                state=state,
                bd=0,
                highlightthickness=0,
                relief="flat",
                overrelief="flat",
                takefocus=False,
            )
            button.pack(pady=10)
            # Add hover effect for better UI responsiveness
            add_button_hover_effect(button, normal_bg="#444444", hover_bg="#555555")

    def create_blueig_button(self):
        for widget in self.blueig_frame.winfo_children():
            widget.destroy()

        btn = tk.Button(
            self.blueig_frame,
            text="Launch BlueIG",
            font=("Helvetica", 24),
            bg="#888888", fg="white",
            width=25, height=2,
            state="disabled",
            bd=0,
            highlightthickness=0,
            relief="flat",
            overrelief="flat",
            takefocus=False,
        )
        btn.pack()
        # Add hover effect for better UI responsiveness
        add_button_hover_effect(btn, normal_bg="#444444", hover_bg="#555555")

        is_srv = config["General"].getboolean("is_server", fallback=False)
        if is_srv:
            return

        # Fast path: if BlueIG path is already cached/known, enable immediately
        cached_path = config['General'].get('blueig_path', '')
        if cached_path and os.path.isfile(cached_path):
            btn.config(state="normal", bg="#444444", command=self.launch_blueig_with_exercise_id)
            return

        # Otherwise, show "Checking..." and resolve asynchronously
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
        btn = tk.Button(
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
        # Add hover effect for better UI responsiveness
        add_button_hover_effect(btn, normal_bg="#444444", hover_bg="#555555")
        return btn

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
            # Use foreground launch for BlueIG GUI application
            self.controller.launch_app_foreground(exe, args[1:], cwd=os.path.dirname(exe))
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
            self.launch_app_foreground(vbs_license_manager_path)
            if is_close_on_launch_enabled():
                sys.exit(0)
        except Exception as e:
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
            self.open_folder_foreground(battlespaces_path)
        else:
            messagebox.showerror("Error", "VBS4 Battlespaces folder not found.")

    def open_vbs4_folder(self):
        vbs4_path = get_vbs4_install_path()
        if vbs4_path:
            folder_path = os.path.dirname(vbs4_path)
            if os.path.exists(folder_path):
                self.open_folder_foreground(folder_path)
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
            save_config()
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
            # Use cached image for better performance
            ph = load_cached_image(prompt_box_image_path, (801, 506))
            if ph:
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
                # Try to connect automatically before giving up
                if not connect_working_share_interactive(parent=None, silent=True):
                    # Clear offline config when network access fails after connection attempt
                    clear_offline_ip_configuration()
                    logging.info("[fuser_manager] Cleared offline configuration due to network access failure")
                    
                    # Only show error dialog once per session
                    global _NETWORK_ERROR_SHOWN
                    if not _NETWORK_ERROR_SHOWN:
                        _NETWORK_ERROR_SHOWN = True
                        messagebox.showerror("Network Connection Failed", 
                            f"Cannot access WorkingFolder at {default_path}\n\n"
                            "Please verify:\n"
                            "1. Host PC is running and accessible\n"
                            "2. Network connection is stable\n"
                            "3. SharedMeshDrive share is available\n\n"
                            "Offline configuration has been cleared.\n\n"
                            "Use Settings → Offline/Shared → Manual Connect to retry.")
                    return
        
        # Convert to local path if we're on the Host PC (prevents SMB loopback issues)
        if default_path:
            original_path = default_path
            default_path = unc_to_local_if_host(default_path)
            if default_path != original_path:
                self.log_message(f"Host PC detected: Using local path for remote fusers")
                self.log_message(f"  UNC:   {original_path}")
                self.log_message(f"  Local: {default_path}")

        # Establish UNC session ONCE before launching any fusers (only for UNC paths)
        if default_path and default_path.startswith("\\\\"):
            parts = default_path.split("\\")
            if len(parts) >= 4 and parts[0] == '' and parts[1] == '':
                unc_root = f"\\\\{parts[2]}\\{parts[3]}"
            else:
                unc_root = default_path
            
            self.log_message(f"Establishing network session to {unc_root}...")
            if not ensure_unc_session_once(unc_root, first_timeout=8.0):
                self.log_message(f"WARNING: Cannot establish network session to {unc_root}")
                # Continue anyway for remote fusers - they might be on different shares
        
        # Auto-discover fuser directories if a shared path is provided
        discovered = discover_fusers_from_shared_path(default_path)
        for ip, info in discovered.items():
            fuser_settings.setdefault(ip, []).extend(info)

        # If user did not supply IPs, run for all discovered/configured IPs
        if not ip_list:
            ip_list = list(fuser_settings.keys())

        # Launch fusers with spawn lock to prevent resource exhaustion
        with _SPAWN_LOCK:
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

                fuser_count = len(fusers)
                for fuser_idx, fuser in enumerate(fusers):
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
                        subprocess.run(cmd, shell=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                        host = machine_name or ip
                        self.log_message(f"Launched {name} on {host} at {path}")
                        # Stagger launches to prevent resource exhaustion
                        if fuser_idx < fuser_count - 1:
                            time.sleep(0.5)
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
                # Try to connect automatically before giving up
                if not connect_working_share_interactive(parent=None, silent=True):
                    # Clear offline config when network access fails after connection attempt
                    clear_offline_ip_configuration()
                    logging.info("[fuser_panel] Cleared offline configuration due to network access failure")
                    messagebox.showerror("Offline Mode", OFFLINE_ACCESS_HINT)
                    return
        else:
            default_path = shared_path
            if default_path is None:
                default_path = load_fuser_config(config_file)

        fuser_path = default_path or working_fuser_unc()
        
        # Critical fix: Prevent local fallback when network path is expected but unavailable
        if not fuser_path:
            self.log_message("ERROR: No fuser path configured. Please set up network WorkingFolder.")
            messagebox.showerror(
                "Configuration Required",
                "No WorkingFolder path configured.\n\n"
                "Please configure the host IP and WorkingFolder path in Settings."
            )
            return
        
        # Convert to local path if we're on the Host PC (prevents SMB loopback issues)
        original_path = fuser_path
        fuser_path = unc_to_local_if_host(fuser_path)
        if fuser_path != original_path:
            self.log_message(f"Host PC detected: Using local path instead of UNC")
            self.log_message(f"  UNC:   {original_path}")
            self.log_message(f"  Local: {fuser_path}")
        
        # Establish UNC session ONCE before launching any fusers (only for UNC paths)
        if fuser_path.startswith("\\\\"):
            # Extract UNC root (\\host\share)
            parts = fuser_path.split("\\")
            if len(parts) >= 4 and parts[0] == '' and parts[1] == '':
                unc_root = f"\\\\{parts[2]}\\{parts[3]}"
            else:
                unc_root = fuser_path
            
            self.log_message(f"Establishing network session to {unc_root}...")
            if not ensure_unc_session_once(unc_root, first_timeout=8.0):
                self.log_message(f"ERROR: Cannot access network WorkingFolder: {fuser_path}")
                self.log_message("Network connection required. Please verify:")
                self.log_message("1. Host PC is running and accessible")
                self.log_message("2. Network connection is stable")
                self.log_message("3. SharedMeshDrive share is available")
                messagebox.showerror(
                    "Network Required", 
                    f"Cannot access WorkingFolder at {fuser_path}\n\n"
                    "Fusers require network access to shared WorkingFolder.\n"
                    "Please check network connection and try again."
                )
                return
            self.log_message(f"Network session established successfully")

        # Launch fusers sequentially with spawn lock to prevent resource exhaustion
        with _SPAWN_LOCK:
            for idx in range(1, 4):
                name = f"LocalFuser{idx}"
                bat = rf'C:\\Program Files\\Skyline\\PhotoMesh\\Fuser\\{name}.bat'
                if os.path.isfile(bat):
                    cmd = f'start "" "{bat}"'
                else:
                    cmd = f'start "" "{fuser_exe}" "{name}" "{fuser_path}" 0 true'

                try:
                    subprocess.run(cmd, shell=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    self.log_message(f"Launched {name} at {fuser_path}")
                    # Stagger launches to prevent resource exhaustion
                    if idx < 3:
                        time.sleep(0.5)
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
                self.open_folder_foreground(project_dir)

def find_terra_explorer() -> str:
    """Find TerraExplorer executable by searching common installation paths."""
    candidates = [
        r"C:\Program Files\Skyline\TerraExplorer Pro\TerraExplorer.exe",
        r"C:\Program Files (x86)\Skyline\TerraExplorer Pro\TerraExplorer.exe",
        r"C:\Program Files\Skyline\TerraExplorer\TerraExplorer.exe",
        r"C:\Program Files (x86)\Skyline\TerraExplorer\TerraExplorer.exe",
    ]
    
    # Check explicit paths first
    for path in candidates:
        if os.path.isfile(path):
            return path
    
    # Search in Program Files directories
    program_dirs = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ]
    
    for prog_dir in program_dirs:
        if os.path.isdir(prog_dir):
            # Look for Skyline folder
            skyline_dir = os.path.join(prog_dir, "Skyline")
            if os.path.isdir(skyline_dir):
                # Search for TerraExplorer in any subdirectory
                for root, dirs, files in os.walk(skyline_dir):
                    for file in files:
                        if file.lower() == "terraexplorer.exe":
                            return os.path.join(root, file)
    
    return ""  # Not found

    def view_mesh(self):
        terra_explorer_path = r"C:\Program Files\Skyline\TerraExplorer Pro\TerraExplorer.exe"
        self.log_message("Launching TerraExplorer...")

        def start_explorer(path):
            try:
                self.launch_app_foreground(path)
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
        sys_settings_path = os.path.join(_BUNDLE_DIR, 'photomesh', 'RealityMeshSystemSettings.txt')
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

        # --- Host-only system status box -------------------------------------
        # Show fuser count and share drive status only on Host PC
        # Positioned below the log so it doesn't block main controls
        if is_host_machine():
            host_status_frame = tk.Frame(
                self.log_frame, bg="#2a2a2a", bd=2, relief="solid", highlightthickness=0
            )
            host_status_frame.pack(fill="x", pady=(10, 0))
            
            # Title
            tk.Label(
                host_status_frame,
                text="System Status (Host)",
                font=("Helvetica", 14, "bold"),
                bg="#2a2a2a",
                fg="#00BFFF",
                bd=0,
                highlightthickness=0,
            ).pack(anchor="w", padx=10, pady=(5, 2))
            
            # Fuser status label
            self.host_fuser_status_label = tk.Label(
                host_status_frame,
                text="Fusers: Checking...",
                font=("Helvetica", 12),
                bg="#2a2a2a",
                fg="#FFFF00",
                bd=0,
                highlightthickness=0,
                anchor="w",
            )
            self.host_fuser_status_label.pack(anchor="w", padx=10, pady=2)
            
            # Share drive status label
            self.host_share_status_label = tk.Label(
                host_status_frame,
                text="Share Drive: Checking...",
                font=("Helvetica", 12),
                bg="#2a2a2a",
                fg="#FFFF00",
                bd=0,
                highlightthickness=0,
                anchor="w",
            )
            self.host_share_status_label.pack(anchor="w", padx=10, pady=(2, 5))
            
            # Start periodic status updates
            self._update_host_status_box()
        else:
            # Not a Host machine, so we don't create the status box
            self.host_fuser_status_label = None
            self.host_share_status_label = None

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
        """Return a main-action button styled like the other panels with hover effect."""
        btn = tk.Button(
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
        # Add hover effect for better UI responsiveness
        add_button_hover_effect(btn, normal_bg="#444444", hover_bg="#555555")
        return btn

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

    def force_update_host_status(self):
        """Force an immediate update of the Host status box (called when fusers change)."""
        if hasattr(self, 'host_fuser_status_label') and self.host_fuser_status_label:
            # Cancel any pending periodic update to avoid conflicts
            if hasattr(self, '_pending_host_status_update'):
                try:
                    self.after_cancel(self._pending_host_status_update)
                except:
                    pass
            
            # Trigger immediate update
            self._update_host_status_box()
    
    def _update_host_status_box(self):
        """Update the Host-only status box showing fuser count and share status.
        
        This method runs every 3 seconds on the Host machine to display:
        - Current fuser count vs desired count
        - Share drive connectivity status with color coding
        
        Synced with Settings panel logic to ensure consistent status reporting.
        Only runs if the status box exists (i.e., on Host machines).
        """
        if not hasattr(self, 'host_fuser_status_label') or self.host_fuser_status_label is None:
            return  # Not on Host machine, nothing to update
        
        # Prevent overlapping background checks
        if getattr(self, "_host_status_check_busy", False):
            self.after(3000, self._update_host_status_box)
            return
        
        self._host_status_check_busy = True
        
        # Track last status to avoid unnecessary UI updates (smooth experience)
        last_fuser_status = getattr(self, "_last_host_fuser_status", None)
        last_share_status = getattr(self, "_last_host_share_status", None)
        
        def _work():
            """Background thread work - checks fuser count and share status."""
            fuser_result = None
            share_result = None
            
            try:
                # Get LIVE fuser counts from beacon broadcasts (real running processes)
                # This is more accurate than scanning directories which only shows seeded folders
                live_counts = get_live_fuser_counts_from_beacons(timeout_sec=10)
                
                # Count local running fusers (authoritative for this machine)
                local_running = count_local_fusers()

                # Desired counts
                host_target, user_target = get_fuser_counts()
                try:
                    host_target = int(host_target)
                except Exception:
                    host_target = 1
                try:
                    user_target = int(user_target)
                except Exception:
                    user_target = 3
                
                # Ensure user_target is at least 1 (if 0, default to 3)
                if user_target <= 0:
                    user_target = 3

                # Build summary from live beacon data
                hostname = platform.node()
                
                # Start with local (authoritative)
                summary = {hostname: local_running}
                
                # Add all PCs broadcasting beacons
                for pc, count in live_counts.items():
                    if pc != hostname:  # Don't overwrite local authoritative count
                        summary[pc] = count

                # Compute totals and breakdown per PC with targets
                pcs = sorted(summary.keys())
                total_running = 0
                breakdown_parts = []
                for pc in pcs:
                    running = int(summary[pc])
                    target = host_target if pc == hostname else user_target
                    total_running += running
                    breakdown_parts.append(f"{pc}: {running}/{target}")

                # Total desired across fleet: use MAX_TOTAL_FUSERS constant (10) as the target
                # This shows the maximum possible fusers that can run across all PCs
                total_target = MAX_TOTAL_FUSERS

                logging.debug(
                    f"[host-status] LIVE counts from beacons: local={local_running}, total={total_running}, pcs={len(pcs)}, total_target={total_target}"
                )

                # Compose display: TOTAL line then per-PC list (one per line)
                base_text = f"{total_running}/{total_target} TOTAL fusers running"
                if breakdown_parts:
                    # Show each PC on its own line with safe cap and ellipsis
                    max_pcs = 15
                    display_parts = breakdown_parts[:max_pcs]
                    if len(breakdown_parts) > max_pcs:
                        display_parts.append("…")
                    base_text += "\n• " + "\n• ".join(display_parts)

                # Color coding: green if at/over target, orange if some running, red if none
                if total_target > 0 and total_running >= total_target:
                    color = "#00FF00"  # Green
                elif total_running > 0:
                    color = "#FFAA00"  # Orange
                else:
                    color = "#FF0000"  # Red

                fuser_result = (base_text, color)

            except Exception as e:
                logging.error(f"[host-status] Error detecting fusers: {e}")
                fuser_result = ("Fusers: Error Detecting", "#FF4500")  # Orange-Red
            
            try:
                # Get share status (same function used by Settings panel)
                status_code, status_msg, status_color = check_network_share_status()
                
                # Format the message for the status box (consistent with Settings panel)
                if status_code == 'connected':
                    share_text = "Share Drive: Connected"
                elif status_code == 'local':
                    share_text = "Share Drive: Local Path"
                elif status_code == 'checking':
                    share_text = "Share Drive: Checking..."
                elif status_code == 'disconnected':
                    share_text = "Share Drive: Disconnected"
                elif status_code == 'unconfigured':
                    share_text = "Share Drive: Not Configured"
                elif status_code == 'error':
                    share_text = "Share Drive: Error"
                else:
                    share_text = f"Share Drive: {status_msg}"
                
                share_result = (share_text, status_color)
                
            except Exception as e:
                share_result = ("Share Drive: Error", "#FF4500")  # Orange-Red
            
            def _apply():
                """Apply results on UI thread."""
                try:
                    # Update fuser status (only if changed)
                    if fuser_result and fuser_result != last_fuser_status:
                        fuser_text, fuser_color = fuser_result
                        if hasattr(self, 'host_fuser_status_label') and self.host_fuser_status_label:
                            self.host_fuser_status_label.config(text=fuser_text, fg=fuser_color)
                        self._last_host_fuser_status = fuser_result
                    
                    # Update share status (only if changed)
                    if share_result and share_result != last_share_status:
                        share_text, share_color = share_result
                        if hasattr(self, 'host_share_status_label') and self.host_share_status_label:
                            self.host_share_status_label.config(text=share_text, fg=share_color)
                        self._last_host_share_status = share_result
                        
                        # Log disconnection events (synced with Settings panel logging)
                        if 'Disconnected' in share_text and last_share_status and 'Connected' in last_share_status[0]:
                            logging.warning(f"[oneclick-status] Share became disconnected - drive may have been unplugged")
                        elif 'Connected' in share_text and last_share_status and 'Disconnect' in last_share_status[0]:
                            logging.info(f"[oneclick-status] Share reconnected")
                    
                finally:
                    self._host_status_check_busy = False
                    # Schedule next update in 3 seconds (matches Settings panel polling rate)
                    self.after(3000, self._update_host_status_box)
            
            # Apply result on UI thread
            try:
                self.after(0, _apply)
            except Exception:
                # If widget is destroyed, just drop it
                self._host_status_check_busy = False
        
        # Run the check in background thread (same pattern as Settings panel)
        run_in_thread(_work)

    def relaunch_fusers(self):
        try:
            self.log_message("Relaunching fusers …")
            relaunch = globals().get("relaunch_fusers")
            if callable(relaunch):
                relaunch()
            running = count_local_fusers()
            self.log_message(f"Fusers relaunched. Running: {running}")
            
            # Force immediate status update
            if hasattr(self, 'force_update_host_status'):
                self.force_update_host_status()
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
            # Use cached image for better performance
            ph = load_cached_image(prompt_box_image_path, (801, 506))
            if ph:
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
                self.open_folder_foreground(project_dir)

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
        sys_settings_path = os.path.join(_BUNDLE_DIR, 'photomesh', 'RealityMeshSystemSettings.txt')
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

        self.update_bvi_version()

    def make_button(self, text, command):
        btn = tk.Button(
            self,
            text=text,
            font=("Helvetica", 24),
            bg="#444444",
            fg="white",
            activebackground="#666666",
            activeforeground="white",
            width=27,
            height=2,
            command=command,
            bd=0,
            highlightthickness=0,
            relief="flat",
            overrelief="flat",
            takefocus=False,
        )
        # Add hover effect for better UI responsiveness
        add_button_hover_effect(btn, normal_bg="#444444", hover_bg="#555555")
        return btn

    def update_bvi_version(self):
        bvi_path = get_ares_manager_path()
        version = get_bvi_version(bvi_path)
        self.version_label.config(text=f"Version: {version}")

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

# ─── SETTINGS PANEL ──────────────────────────────────────────────────────────
class SettingsPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        logging.info("[ui-diag] SettingsPanel: super().__init__ complete")
        self.controller = controller

        self.configure(bg="black")  # header removed; fixed header used
        logging.info("[ui-diag] SettingsPanel: configure complete")
        self.grid_rowconfigure(7, weight=1, minsize=400)
        self.grid_columnconfigure(0, weight=1)
        logging.info("[ui-diag] SettingsPanel: grid configuration complete")

        # --- Top toggles -------------------------------------------------
        logging.info("[ui-diag] SettingsPanel: creating toggles frame")
        toggles = tk.LabelFrame(self, text="", bg="black", fg="white", bd=0, highlightthickness=0)
        logging.info("[ui-diag] SettingsPanel: toggles frame created, about to grid")
        toggles.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        logging.info("[ui-diag] SettingsPanel: toggles gridded")
        toggles.grid_columnconfigure(0, weight=1)
        toggles.grid_columnconfigure(1, weight=1)
        logging.info("[ui-diag] SettingsPanel: toggles grid columns configured")

        logging.info("[ui-diag] SettingsPanel: about to create BooleanVars")
        self.fullscreen_var = tk.BooleanVar(value=controller.fullscreen)
        logging.info("[ui-diag] SettingsPanel: fullscreen_var created")
        self.startup_var = tk.BooleanVar(value=is_startup_enabled())
        logging.info("[ui-diag] SettingsPanel: startup_var created")
        self.close_on_launch_var = tk.BooleanVar(value=is_close_on_launch_enabled())
        logging.info("[ui-diag] SettingsPanel: close_on_launch_var created")
        logging.info("[ui-diag] SettingsPanel: about to create fuser_var")
        self.fuser_var = tk.BooleanVar(
            value=config["Fusers"].getboolean("fuser_computer", False)
        )
        logging.info("[ui-diag] SettingsPanel: fuser_var created")

        def _on_fuser_toggle():
            config["Fusers"]["fuser_computer"] = str(self.fuser_var.get())
            save_config()

            if self.fuser_var.get():
                # Ensure Fusers host matches the single Host PC Name
                ip = get_host_ip()
                if not ip:
                    ip = get_primary_ipv4()
                    if ip:
                        self.host_ip_var.set(ip)
                        try:
                            set_host_ip(ip)  # This syncs all config values including working_folder_host
                        except Exception:
                            pass
                else:
                    try:
                        set_host_ip(ip)  # This syncs all config values including working_folder_host
                    except Exception:
                        pass
                # No need to set working_folder_host directly - set_host_ip() handles it
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
                
                # Async enforcement: don't block UI while scaling
                def _enforce():
                    try:
                        ensure_fuser_instances(n)
                    except Exception as e:
                        logging.error(f"[fuser-toggle] Enforcement error after enable: {e}")
                run_in_thread(_enforce)
            else:
                # When turning off, kill all fusers and reset count
                def _disable():
                    try:
                        kill_fusers_on_disable()
                    except Exception as e:
                        logging.error(f"[fuser-toggle] Disable error: {e}")
                run_in_thread(_disable)

            save_config()

            update_fuser_shared_path()
            # Policy enforcement can be heavy; execute off UI thread
            run_in_thread(lambda: enforce_local_fuser_policy())
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

        # Check if we're on the Host PC (by verifying share exists locally)
        # This is more reliable than IP comparison - config might have stale IP
        is_host_by_ip = is_this_pc_the_real_host()
        our_ip = get_primary_ipv4()

        logging.info("[ui-diag] SettingsPanel: about to create checkbuttons")
        for i, (text, var, cmd) in enumerate(toggle_specs):
            logging.info(f"[ui-diag] SettingsPanel: creating checkbutton {i}: {text}")
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
            
            # If this is the "Fuser Computer" checkbox and we're on Host PC, disable it
            if text == "Fuser Computer" and is_host_by_ip:
                chk.config(state="disabled", fg="#888888")  # Gray out the text
                # Automatically check it since we're the host
                self.fuser_var.set(True)
                config["Fusers"]["fuser_computer"] = "True"
                save_config()
                logging.info(f"[ui-diag] SettingsPanel: Fuser Computer checkbox disabled (Host PC detected - share exists locally)")
                # Store reference for potential future updates
                self.fuser_computer_checkbox = chk
            
            logging.info(f"[ui-diag] SettingsPanel: checkbutton {i} created, about to grid")
            chk.grid(row=r, column=c, padx=6, pady=6, sticky="ew")
            logging.info(f"[ui-diag] SettingsPanel: checkbutton {i} gridded")

        # Add info label if we're on Host PC
        if is_host_by_ip:
            host_info_label = tk.Label(
                toggles,
                text=f"ℹ Host PC detected (IP: {our_ip}) - Fuser Computer is auto-enabled",
                font=("Helvetica", 11),
                bg="#444444",
                fg="#aaaaaa",
                anchor="w"
            )
            host_info_label.grid(row=2, column=0, columnspan=2, padx=6, pady=(0, 6), sticky="w")
            logging.info("[ui-diag] SettingsPanel: Host PC info label added")

        logging.info("[ui-diag] SettingsPanel: all checkbuttons complete, creating fuser controls")
        # --- Local fuser controls -----------------------------------------
        frow = tk.Frame(self, bg="black")
        logging.info("[ui-diag] SettingsPanel: frow frame created")
        frow.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))
        logging.info("[ui-diag] SettingsPanel: frow gridded")

        self.fuser_count_label = tk.Label(
            frow,
            text="Local fusers: 0 running / 0 desired",
            font=("Helvetica", 14),
            bg="black",
            fg="white",
        )
        self.fuser_count_label.pack(side="left")

        def _bump(delta: int):
            """Debounced adjust of desired fuser count; heavy scaling moved off UI thread."""
            # Read current desired
            is_fuser = config["Fusers"].getboolean("fuser_computer", fallback=False)
            try:
                current = int(config["Fusers"].get("desired_count", "3") or 3)
            except Exception:
                current = 3
            target = _clamp_fusers(current + delta, is_fuser)
            # Persist immediately so UI & other logic see latest intent
            config["Fusers"]["desired_count"] = str(target)
            save_config()
            self._refresh_fuser_counter_row()

            # Debounce: if a previous bump is pending, reschedule instead of stacking launches
            now = time.time()
            pending = getattr(self, "_fuser_scale_pending_target", None)
            self._fuser_scale_pending_target = target
            last_sched = getattr(self, "_fuser_scale_last_sched", 0.0)
            # If we scheduled <0.4s ago, just update pending target and return
            if now - last_sched < 0.4:
                return
            self._fuser_scale_last_sched = now

            # Disable buttons temporarily (if we can find them) to prevent spam
            try:
                for child in frow.winfo_children():
                    if isinstance(child, tk.Button) and child.cget("text") in {"+", "–"}:
                        child.config(state="disabled")
            except Exception:
                pass

            def _do_scale():
                try:
                    tgt = getattr(self, "_fuser_scale_pending_target", target)
                    logging.info(f"[fuser-scale-ui] Debounced enforcement start -> {tgt}")
                    ensure_fuser_instances(tgt)
                except Exception as e:
                    logging.error(f"[fuser-scale-ui] Enforcement error: {e}")
                finally:
                    # Re-enable buttons on UI thread
                    def _reenable():
                        try:
                            for child in frow.winfo_children():
                                if isinstance(child, tk.Button) and child.cget("text") in {"+", "–"}:
                                    child.config(state="normal")
                        except Exception:
                            pass
                        self._refresh_fuser_counter_row()
                    try:
                        self.after(0, _reenable)
                    except Exception:
                        pass

            # Run scaling off the UI thread
            run_in_thread(_do_scale)

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

        logging.info("[ui-diag] SettingsPanel: about to call _refresh_fuser_counter_row()")
        self._refresh_fuser_counter_row()
        self._schedule_fuser_count_refresh()
        logging.info("[ui-diag] SettingsPanel: _refresh_fuser_counter_row() complete (periodic refresh scheduled)")

        # --- Connected Fuser PCs (Host-visible indicator) ----------------
        logging.info("[ui-diag] SettingsPanel: creating conn_row frame")
        conn_row = tk.Frame(self, bg="black")
        logging.info("[ui-diag] SettingsPanel: conn_row created, about to grid (removed 'after' param to fix hang)")
        # BUGFIX: Changed to row=3 to prevent overlap with frow (Local fusers in row=2)
        conn_row.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 6))
        logging.info("[ui-diag] SettingsPanel: conn_row gridded")

        self.connected_pcs_label = tk.Label(
            conn_row,
            text="Connected fuser PCs: 0",
            font=("Helvetica", 14),
            bg="black",
            fg="#888888",
        )
        logging.info("[ui-diag] SettingsPanel: connected_pcs_label created")
        self.connected_pcs_label.pack(side="left")
        logging.info("[ui-diag] SettingsPanel: connected_pcs_label packed")

        self.connected_pcs_names_label = tk.Label(
            conn_row,
            text="",
            font=("Helvetica", 10),
            bg="black",
            fg="#666666",
            justify="left",
            anchor="w"
        )
        logging.info("[ui-diag] SettingsPanel: connected_pcs_names_label created")
        self.connected_pcs_names_label.pack(side="left", padx=(10, 0))
        logging.info("[ui-diag] SettingsPanel: connected_pcs_names_label packed")

        # Schedule periodic refresh of connected PCs count
        # CRITICAL FIX: Don't call synchronously during init - it can block on slow network
        # Schedule it to run after mainloop starts to avoid UI hang
        logging.info("[ui-diag] SettingsPanel: scheduling first _refresh_connected_pcs() after UI ready")
        self.after(500, self._refresh_connected_pcs)
        logging.info("[ui-diag] SettingsPanel: _refresh_connected_pcs() scheduled for 500ms from now")

        # --- Network Host -----------------------------------------------
        net_frame = tk.Frame(self, bg="black")
        net_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 6))
        net_frame.grid_columnconfigure(1, weight=1)

        tk.Label(
            net_frame,
            text="Host IP",
            font=("Helvetica", 14),
            bg="black",
            fg="white",
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        host_row = tk.Frame(net_frame, bg="black")
        host_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 6))

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

        # Compact host + working fuser status row with a manual retry button
        status_row = tk.Frame(net_frame, bg="black")
        status_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        self.host_status_label = tk.Label(
            status_row,
            text=self._format_host_status(None),
            font=("Helvetica", 12),
            bg="black",
            fg="#CCCCCC",
            anchor="w",
        )
        self.host_status_label.pack(side="left", fill="x", expand=True)

        self.retry_btn = tk.Button(
            status_row,
            text="Retry connect",
            command=self._retry_connect,
            font=("Helvetica", 12),
            bg="#444444",
            fg="white",
            bd=0,
            width=16,
        )
        self.retry_btn.pack(side="right", padx=(8, 0))

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
            # Refresh status after sharing
            self._update_share_status()

        tk.Button(net_frame, text="Share Folder Now", command=_share_now,
                  font=("Helvetica", 12), bg="#444444", fg="white", bd=0) \
            .grid(row=3, column=0, sticky="w", pady=(0, 6))

        # Create a frame to hold the share button and status indicator 
        share_row = tk.Frame(net_frame, bg="black")
        share_row.grid(row=3, column=1, sticky="ew", pady=(0, 6), padx=(10, 0))

        # Status indicator label
        self.share_status_label = tk.Label(
            share_row,
            text="",
            font=("Helvetica", 10),
            bg="black",
            fg="#888888",
            anchor="w"
        )
        self.share_status_label.pack(side="left", fill="x", expand=True)

        def _test_connection():
            """Test network connectivity and show detailed results."""
            o = get_offline_cfg()
            unc_root = build_unc_from_cfg(o)
            working_fuser = working_fuser_unc()
            host = o.get("host_ip", "")
            result_lines = []
            # 1. Ping host
            if host:
                ping_ok = _test_network_connectivity(host)
                result_lines.append(f"Ping {host}: {'✓' if ping_ok else '✗'}")
            else:
                result_lines.append("Ping: No host IP configured ✗")
            # 2. UNC root
            unc_ok = _unc_usable(unc_root)
            result_lines.append(f"Share {unc_root}: {'✓' if unc_ok else '✗'}")
            # 3. WorkingFuser subfolder
            fuser_ok = _unc_usable(working_fuser)
            result_lines.append(f"WorkingFuser {working_fuser}: {'✓' if fuser_ok else '✗'}")
            # Show results
            msg = "\n".join(result_lines)
            messagebox.showinfo("Connection Test", msg)
            # Trigger immediate status refresh after test
            self._force_share_status_update()

        def _refresh_status():
            """Force an immediate share status check."""
            self._force_share_status_update()

        tk.Button(
            share_row,
            text="Test Connection",
            command=_test_connection,
            font=("Helvetica", 12),
            bg="#444444",
            fg="white",
            bd=0,
        ).pack(side="left", padx=8)
        
        # Add refresh button for instant status check
        tk.Button(
            share_row,
            text="↻ Refresh",
            command=_refresh_status,
            font=("Helvetica", 10),
            bg="#555555",
            fg="white",
            bd=0,
            width=8
        ).pack(side="left", padx=(0, 8))
        
        # Add tooltip functionality to the status label
        def create_tooltip(widget, text_func):
            def on_enter(event):
                try:
                    tooltip_text = text_func()
                    # Create a simple tooltip window
                    tooltip = tk.Toplevel()
                    tooltip.wm_overrideredirect(True)
                    tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
                    tooltip.configure(bg="#333333")
                    label = tk.Label(tooltip, text=tooltip_text, bg="#333333", fg="white", 
                                   font=("Helvetica", 9), padx=5, pady=2)
                    label.pack()
                    widget.tooltip = tooltip
                except:
                    pass
                    
            def on_leave(event):
                try:
                    if hasattr(widget, 'tooltip'):
                        widget.tooltip.destroy()
                        del widget.tooltip
                except:
                    pass
            
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
        
        # Tooltip that shows detailed share status
        def get_tooltip_text():
            try:
                status_code, status_msg, _ = check_network_share_status()
                status_name = {
                    'connected': 'Connected',
                    'local': 'Local (Host PC)',
                    'disconnected': 'Disconnected',
                    'unconfigured': 'Not Configured',
                    'checking': 'Checking...',
                    'error': 'Error'
                }.get(status_code, 'Unknown')
                
                return f"Network Share Status: {status_name}\n{status_msg.replace('●', '').replace('○', '').replace('◐', '').strip()}"
            except Exception as e:
                return f"Network Share Status: Error\n{str(e)}"
        
        create_tooltip(self.share_status_label, get_tooltip_text)

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
        grp.grid(row=5, column=0, sticky="ew", padx=10, pady=10)

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
        tk.Button(row8, text="Manual Connect", bg="#446644", fg="white", command=self._manual_connect_dialog).pack(side="left", padx=8)
        tk.Button(row8, text="Open Working Folder", bg="#444", fg="white", command=self._open_working_folder).pack(side="left")
        tk.Button(row8, text="Clear Settings", bg="#664444", fg="white", command=self._clear_offline_settings).pack(side="left", padx=8)

        # Reality Mesh Install Folder
        rm_row = tk.Frame(self, bg="black")
        rm_row.grid(row=6, column=0, sticky="ew", padx=10, pady=5)
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
        # Row 7 expands for the scroller; keep Back button at row 8 non‑scrolling
        self.grid_rowconfigure(7, weight=1, minsize=600)
        locs_box.grid(row=7, column=0, sticky="nsew", padx=10, pady=(0, 10))

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
        # Use cached paths from config for instant display (no scanning during startup)
        # The paths are already cached by get_vbs4_install_path() etc. during warmup
        cached_vbs4 = config["General"].get("vbs4_path", "") or "[not set]"
        cached_blueig = config["General"].get("blueig_path", "") or "[not set]"
        cached_ares = config["General"].get("ares_manager_path", "") or "[not set]"
        
        self.lbl_vbs4 = self._create_path_row(
            "Set VBS4 Install Location",
            self._on_set_vbs4,
            cached_vbs4,
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
            cached_blueig,
            parent=self._settings_inner,
        )
        self.lbl_ares = self._create_path_row(
            "Set ARES Manager Location",
            self._on_set_ares,
            cached_ares,
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
        logging.info("[ui-diag] SettingsPanel: spacer added")

        # Force update of layout and scroll region to ensure all items are visible
        logging.info("[ui-diag] SettingsPanel: about to call _settings_inner.update_idletasks()")
        self._settings_inner.update_idletasks()
        logging.info("[ui-diag] SettingsPanel: _settings_inner.update_idletasks() complete")
        logging.info("[ui-diag] SettingsPanel: about to call _settings_canvas.update_idletasks()")
        self._settings_canvas.update_idletasks()
        logging.info("[ui-diag] SettingsPanel: _settings_canvas.update_idletasks() complete")
        self._settings_canvas.yview_moveto(0)
        logging.info("[ui-diag] SettingsPanel: yview_moveto complete")
        
        # Manually update scroll region to ensure all content is accessible
        bbox = self._settings_canvas.bbox("all")
        if bbox:
            x0, y0, x1, y1 = bbox
            self._settings_canvas.configure(scrollregion=(x0, y0, x1, y1 + _SCROLLER_BOTTOM_PAD))
        logging.info("[ui-diag] SettingsPanel: scroll region configured")

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
        ).grid(row=8, column=0, pady=10)

        logging.info("[ui-diag] SettingsPanel: about to setup auto-connect")
        # Silent auto-connect on first load (no prompts) - run in background to avoid blocking UI
        try:
            o = get_offline_cfg()
            if (o.get("host_ip") or "").strip():
                # Run connection attempt in background thread to avoid blocking UI
                def _try_connect_bg():
                    try:
                        connect_working_share_interactive(parent=None, silent=True)
                    except Exception as e:
                        logging.warning(f"Background share connection failed: {e}")
                
                # Delay slightly so the UI is responsive first, then run in background
                self.after(2000, lambda: run_in_thread(_try_connect_bg))
        except Exception:
            pass
        logging.info("[ui-diag] SettingsPanel: auto-connect setup complete")

        # Initialize share status display (async; short defer since it's non-blocking)
        logging.info("[ui-diag] SettingsPanel: scheduling share status update")
        self.after(300, self._update_share_status)
        logging.info("[ui-diag] SettingsPanel __init__ COMPLETE")

    def _format_host_status(self, connected: bool | None) -> str:
        try:
            o = get_offline_cfg()
            ip = (o.get("host_ip") or "").strip()
            root, working = _compute_working_unc_from_cfg()
            host_txt = ip if ip else "[no host set]"
            if connected is None:
                # initial/unknown state
                return f"Host: {host_txt} • WorkingFuser: (checking…)"
            return f"Host: {host_txt} • WorkingFuser: {'Connected' if connected else 'Not connected'}"
        except Exception:
            return "Host: [error] • WorkingFuser: [error]"

    def _retry_connect(self):
        # Debounce button
        try:
            self.retry_btn.config(state="disabled", text="Connecting…")
        except Exception:
            pass

        def _work():
            ok = False
            try:
                ok = connect_working_share_interactive(parent=None, silent=True)
            except Exception:
                ok = False

            def _apply():
                # Update status + re-enable button
                try:
                    if hasattr(self, "host_status_label"):
                        self.host_status_label.config(text=self._format_host_status(ok))
                    # Also refresh the share status pill
                    self._update_share_status()
                finally:
                    try:
                        self.retry_btn.config(state="normal", text="Retry connect")
                    except Exception:
                        pass

            try:
                self.after(0, _apply)
            except Exception:
                pass

        run_in_thread(_work)

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
        # Use cached values from config for instant updates (no scanning)
        general = config["General"] if "General" in config else {}
        if hasattr(self, "lbl_projects_root"):
            self.lbl_projects_root.config(text=get_projects_root() or "[not set]")
        if hasattr(self, "lbl_vbs4"):
            self.lbl_vbs4.config(text=general.get("vbs4_path", "") or "[not set]")
        if hasattr(self, "lbl_vbs4_setup"):
            self.lbl_vbs4_setup.config(general.get("vbs4_setup_path", ""))
        if hasattr(self, "lbl_blueig"):
            self.lbl_blueig.config(text=general.get("blueig_path", "") or "[not set]")
        if hasattr(self, "lbl_ares"):
            self.lbl_ares.config(text=general.get("ares_manager_path", "") or "[not set]")
        if hasattr(self, "lbl_browser"):
            self.lbl_browser.config(text=general.get("browser_path", "") or get_default_browser() or "[not set]")
        if hasattr(self, "lbl_vbs_license"):
            self.lbl_vbs_license.config(general.get("vbs_license_manager_path", ""))
        if hasattr(self, "lbl_oneclick"):
            self.lbl_oneclick.config(text=general.get("oneclick_output", "") or get_oneclick_output_path() or "[not set]")

        self._refresh_fuser_counter_row()

    def _update_share_status(self):
        """Update the share status indicator based on current network share availability.

        Runs the check on a background thread to avoid blocking the UI thread. UI is updated via after().
        Only shows "Checking..." if the check takes longer than 500ms to avoid flashing.
        Only updates UI if status actually changed for smooth experience.
        
        Checks every 3 seconds to quickly detect drive disconnection events (e.g., USB unplugged).
        """
        # Prevent overlapping background checks
        if getattr(self, "_share_check_busy", False):
            # Try again a bit later if a previous check is still running
            self.after(3000, self._update_share_status)
            return

        self._share_check_busy = True
        
        # Track the last known status to avoid unnecessary UI updates
        last_status = getattr(self, "_last_share_status", None)
        check_start_time = time.time()
        checking_shown = False

        def _work():
            nonlocal checking_shown
            result = ('checking', '◐ Checking...', '#FFFF00')
            try:
                # Use timeout wrapper to prevent hanging forever
                result_queue = Queue()
                
                def _do_check():
                    try:
                        result_queue.put(check_network_share_status())
                    except Exception as e:
                        logging.warning(f"Share status check failed: {e}")
                        result_queue.put(('error', f'● Error: {str(e)[:30]}', '#FF4500'))
                
                # Run the check with a timeout
                check_thread = threading.Thread(target=_do_check, daemon=True)
                check_thread.start()
                check_thread.join(5.0)  # 5 second global timeout
                
                # If thread is still alive, it timed out
                if check_thread.is_alive():
                    logging.warning("[share-status] Check timed out after 5 seconds")
                    result = ('error', '● Timeout checking share', '#FF4500')
                elif not result_queue.empty():
                    result = result_queue.get_nowait()
                else:
                    logging.warning("[share-status] No result after thread completion")
                    result = ('error', '● Check failed', '#FF4500')
                
                # If check took longer than 500ms, show "Checking..." briefly
                # This prevents flash for fast checks but gives feedback for slow ones
                elapsed = time.time() - check_start_time
                if elapsed > 0.5 and not checking_shown:
                    checking_shown = True
                    try:
                        if hasattr(self, "share_status_label"):
                            self.after(0, lambda: self.share_status_label.config(text="◐ Checking...", fg="#FFFF00"))
                    except:
                        pass
                        
            except Exception as e:
                logging.warning(f"Share status check wrapper error: {e}")
                result = ('error', f'● Error: {str(e)[:30]}', '#FF4500')

            def _apply():
                try:
                    status_code, status_msg, status_color = result
                    
                    # Only update UI if status actually changed (prevents flashing)
                    current_status_key = f"{status_code}:{status_msg}"
                    if last_status != current_status_key:
                        # Update share status label
                        if hasattr(self, "share_status_label"):
                            self.share_status_label.config(text=status_msg, fg=status_color)
                        
                        # Update compact host status line (map status to simple bool for backwards compat)
                        if hasattr(self, "host_status_label"):
                            is_ok = status_code in ('connected', 'local')
                            self.host_status_label.config(text=self._format_host_status(is_ok if status_code != 'checking' else None))
                        
                        # Remember this status
                        self._last_share_status = current_status_key
                        
                        # Log status changes for troubleshooting
                        if status_code == 'disconnected' and last_status and 'connected' in last_status.lower():
                            logging.warning(f"[share-status] Share became disconnected - drive may have been unplugged")
                        elif status_code in ('connected', 'local') and last_status and 'disconnect' in last_status.lower():
                            logging.info(f"[share-status] Share reconnected")
                        
                finally:
                    self._share_check_busy = False
                    # Schedule next update in 3 seconds (faster detection of drive disconnection)
                    self.after(3000, self._update_share_status)

            # Apply result on UI thread
            try:
                self.after(0, _apply)
            except Exception:
                # If widget is destroyed, just drop it
                self._share_check_busy = False

        run_in_thread(_work)

    def _force_share_status_update(self):
        """Force an immediate share status check, bypassing the busy flag.
        
        Shows "Checking..." immediately for manual refresh to provide visual feedback.
        """
        # Reset the busy flag to allow immediate check
        self._share_check_busy = False
        # Clear last status so UI updates even if status is the same
        self._last_share_status = None
        # Show immediate "Checking..." feedback for manual refresh
        try:
            if hasattr(self, "share_status_label"):
                self.share_status_label.config(text="◐ Checking...", fg="#FFFF00")
        except:
            pass
        # Trigger the update
        self.after(50, self._update_share_status)  # Small delay to ensure UI updates

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

        save_config()

        new_share = o["share_name"]
        if new_share and new_share.lower() != old_share.lower():
            propagate_share_rename_in_config(old_share, new_share)
        working = tk.Toplevel(self)
        working.title("Working…")
        tk.Label(working, text="Working…", padx=20, pady=20).pack()

        def _work():
            try:
                apply_offline_settings()  # sync Wizard, fusers, and ensure share
                # Try to establish the UNC session now (no prompts)
                connect_working_share_interactive(parent=None, silent=True)

                if self.shared_auto_map.get():
                    unc_root = build_unc_from_cfg(o)
                    if unc_root and map_drive(unc_root, sd["drive_letter"]):
                        def _apply_map():
                            self.shared_mode.set("DRIVE")
                            sd["preferred_mode"] = "DRIVE"
                            save_config()

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
        """Test access to the shared working folder with enhanced diagnostics."""
        path = resolve_shared_access_path()
        if not path:
            messagebox.showinfo(
                "Test Access",
                "Host IP is not configured. Set it above to test the shared folder.",
            )
            return
        
        working = tk.Toplevel(self)
        working.title("Testing Connection…")
        tk.Label(working, text="Testing connection to shared folder…", padx=20, pady=20).pack()

        def _work():
            # Extract host and share for diagnostics
            try:
                parts = path.strip("\\").split("\\")
                host = parts[0] if parts else "unknown"
                share = parts[1] if len(parts) > 1 else "unknown"
                
                # Use the new SMB session cache function
                logging.info(f"[test_access] Testing connection to {path}")
                
                # Try to establish session using cached connection
                unc_root = f"\\\\{host}\\{share}"
                session_ok = ensure_smb_session_cached(unc_root, timeout=8)
                
                if session_ok:
                    # Verify the specific path is accessible
                    ok = quick_unc_check(path, timeout=3)
                else:
                    ok = False
                    
                # Get detailed error info
                error_detail = ""
                if not ok:
                    # Try to determine why it failed
                    if not session_ok:
                        error_detail = (
                            "Session establishment failed. This could mean:\n\n"
                            "• Network connectivity issue\n"
                            "• ERROR 1219 (multiple connection conflict)\n"
                            "• Incorrect credentials\n"
                            "• Firewall blocking SMB (port 445)\n\n"
                            "Check the log file for details."
                        )
                    else:
                        error_detail = (
                            f"Session established but path not accessible:\n{path}\n\n"
                            "• Path may not exist on the host\n"
                            "• Insufficient permissions\n"
                            "• Share name or folder mismatch"
                        )
                
            except Exception as e:
                ok = False
                error_detail = f"Exception during test: {str(e)}"
                logging.error(f"[test_access] Exception: {e}", exc_info=True)

            def _done():
                working.destroy()
                if ok:
                    messagebox.showinfo(
                        "Connection Test", 
                        f"✓ Access successful!\n\n{path}\n\nOpening in Explorer…"
                    )
                    self.open_folder_foreground(path)
                else:
                    msg = f"✗ Cannot access:\n{path}\n\n"
                    if error_detail:
                        msg += error_detail
                    else:
                        msg += (
                            "If this is a local, offline LAN:\n\n"
                            "• Ensure all PCs are on the same switch\n"
                            "• Use static IPs (e.g., 192.168.50.10/24)\n"
                            "• Verify share exists with read/write permissions\n"
                            "• Confirm Host IP matches the actual host PC\n"
                            "• Check Windows Firewall allows File & Printer Sharing"
                        )
                    messagebox.showerror("Connection Test", msg)

            post_ui(_done)

        run_in_thread(_work)

    def _manual_connect_dialog(self):
        """Open a manual connection dialog when auto-connect fails."""
        dialog = tk.Toplevel(self)
        dialog.title("Manual Connection Setup")
        dialog.configure(bg="black")
        dialog.geometry("600x400")
        
        # Make modal
        dialog.transient(self)
        dialog.grab_set()
        
        # Title
        tk.Label(
            dialog,
            text="Manual Network Connection",
            font=("Helvetica", 14, "bold"),
            bg="black",
            fg="white"
        ).pack(pady=10)
        
        tk.Label(
            dialog,
            text="Use this when automatic connection fails.\nManually configure and test the connection.",
            bg="black",
            fg="gray",
            justify="left"
        ).pack(pady=5)
        
        # Input frame
        input_frame = tk.Frame(dialog, bg="black")
        input_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Host IP/Name
        tk.Label(input_frame, text="Host IP or Name:", bg="black", fg="white").grid(row=0, column=0, sticky="w", pady=5)
        host_var = tk.StringVar(value=self.host_ip_var.get() or "192.168.10.201")
        tk.Entry(input_frame, textvariable=host_var, width=30, bg="#333", fg="white", insertbackground="white").grid(row=0, column=1, sticky="ew", pady=5, padx=5)
        
        # Share name
        tk.Label(input_frame, text="Share Name:", bg="black", fg="white").grid(row=1, column=0, sticky="w", pady=5)
        share_var = tk.StringVar(value=self.off_share_name.get() or "SharedMeshDrive")
        tk.Entry(input_frame, textvariable=share_var, width=30, bg="#333", fg="white", insertbackground="white").grid(row=1, column=1, sticky="ew", pady=5, padx=5)
        
        # Username (optional)
        tk.Label(input_frame, text="Username (optional):", bg="black", fg="white").grid(row=2, column=0, sticky="w", pady=5)
        user_var = tk.StringVar()
        tk.Entry(input_frame, textvariable=user_var, width=30, bg="#333", fg="white", insertbackground="white").grid(row=2, column=1, sticky="ew", pady=5, padx=5)
        
        # Password (optional)
        tk.Label(input_frame, text="Password (optional):", bg="black", fg="white").grid(row=3, column=0, sticky="w", pady=5)
        pass_var = tk.StringVar()
        tk.Entry(input_frame, textvariable=pass_var, width=30, bg="#333", fg="white", insertbackground="white", show="*").grid(row=3, column=1, sticky="ew", pady=5, padx=5)
        
        # Map drive option
        map_drive_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            input_frame,
            text="Map as M: drive (non-persistent)",
            variable=map_drive_var,
            bg="black",
            fg="white",
            selectcolor="black"
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=10)
        
        input_frame.columnconfigure(1, weight=1)
        
        # Status label
        status_label = tk.Label(dialog, text="", bg="black", fg="yellow", wraplength=550, justify="left")
        status_label.pack(pady=10)
        
        # Button frame
        btn_frame = tk.Frame(dialog, bg="black")
        btn_frame.pack(pady=10)
        
        def test_connection():
            """Test the connection without saving."""
            host = host_var.get().strip()
            share = share_var.get().strip()
            
            if not host or not share:
                status_label.config(text="❌ Please enter both Host IP and Share Name", fg="red")
                return
            
            status_label.config(text="Testing connection...", fg="yellow")
            dialog.update()
            
            def _test():
                try:
                    unc_path = f"\\\\{host}\\{share}"
                    username = user_var.get().strip() or None
                    password = pass_var.get().strip() or None
                    
                    # Use the cached session function
                    success = ensure_smb_session_cached(unc_path, username=username, password=password, timeout=8)
                    
                    def _result():
                        if success:
                            status_label.config(
                                text=f"✓ Connection successful to {unc_path}",
                                fg="green"
                            )
                        else:
                            status_label.config(
                                text=f"❌ Connection failed to {unc_path}\nCheck log for details (ERROR 1219, credentials, firewall, etc.)",
                                fg="red"
                            )
                    post_ui(_result)
                except Exception as e:
                    def _error():
                        status_label.config(text=f"❌ Error: {str(e)}", fg="red")
                    post_ui(_error)
            
            run_in_thread(_test)
        
        def save_and_connect():
            """Save settings and establish connection."""
            host = host_var.get().strip()
            share = share_var.get().strip()
            username = user_var.get().strip() or None
            password = pass_var.get().strip() or None
            
            if not host or not share:
                status_label.config(text="❌ Please enter both Host IP and Share Name", fg="red")
                return
            
            status_label.config(text="Connecting and saving...", fg="yellow")
            dialog.update()
            
            def _connect():
                try:
                    unc_path = f"\\\\{host}\\{share}"
                    
                    # Establish connection
                    success = ensure_smb_session_cached(unc_path, username=username, password=password, timeout=10)
                    
                    if success:
                        # Save credentials if provided
                        if username and password:
                            try:
                                _store_creds_in_cmdkey(host, username, password)
                            except Exception as e:
                                logging.warning(f"[manual_connect] Could not store credentials: {e}")
                        
                        # Map drive if requested
                        if map_drive_var.get():
                            try:
                                subprocess.run(
                                    ['net', 'use', 'M:', unc_path, '/persistent:no'],
                                    capture_output=True,
                                    timeout=5,
                                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                                )
                            except Exception as e:
                                logging.warning(f"[manual_connect] Could not map M: drive: {e}")
                        
                        # Update config
                        def _save():
                            try:
                                self.host_ip_var.set(host)
                                self.off_share_name.set(share)
                                
                                # Save to config
                                config["Offline"]["host_ip"] = host
                                config["Offline"]["host_name"] = host
                                config["Offline"]["share_name"] = share
                                config["Fusers"]["working_folder_host"] = host
                                config["Fusers"]["shared_working_unc"] = f"\\\\{host}\\{share}\\WorkingFuser"
                                
                                save_config()
                                
                                status_label.config(
                                    text=f"✓ Connected and saved! Connection to {unc_path} established.",
                                    fg="green"
                                )
                                
                                # Close dialog after brief delay
                                dialog.after(2000, dialog.destroy)
                            except Exception as e:
                                status_label.config(text=f"❌ Save failed: {str(e)}", fg="red")
                        
                        post_ui(_save)
                    else:
                        def _fail():
                            status_label.config(
                                text=f"❌ Connection failed to {unc_path}\nCheck the log for ERROR 1219, credential issues, etc.",
                                fg="red"
                            )
                        post_ui(_fail)
                except Exception as e:
                    def _error():
                        status_label.config(text=f"❌ Error: {str(e)}", fg="red")
                    post_ui(_error)
            
            run_in_thread(_connect)
        
        tk.Button(btn_frame, text="Test Connection", bg="#444", fg="white", command=test_connection, padx=15, pady=5).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Connect & Save", bg="#446644", fg="white", command=save_and_connect, padx=15, pady=5).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancel", bg="#664444", fg="white", command=dialog.destroy, padx=15, pady=5).pack(side="left", padx=5)

    def _clear_offline_settings(self):
        """Clear all offline IP and network configuration settings."""
        result = messagebox.askyesno(
            "Clear Settings", 
            "This will clear all saved network IP addresses and connection settings.\n\n" +
            "This will prevent automatic reconnection attempts to problematic hosts.\n\n" +
            "Are you sure you want to continue?"
        )
        
        if result:
            # Clear the offline configuration
            success = clear_offline_ip_configuration()
            
            # Also clear the UI fields
            self.host_ip_var.set("")
            self.off_share_name.set("")
            self.off_work_subdir.set("")
            
            if success:
                messagebox.showinfo(
                    "Settings Cleared", 
                    "Network settings have been cleared successfully.\n\n" +
                    "The application will no longer attempt automatic connections to the previous host."
                )
            else:
                messagebox.showerror(
                    "Clear Failed", 
                    "Failed to clear some settings. Check the log for details."
                )

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
        try:
            pc = os.environ.get('COMPUTERNAME') or platform.node()
            logging.info(f"[ui-diag] SettingsPanel: fuser counter refresh -> {pc}: running={running}, desired={desired}, is_fuser={is_fuser}")
        except Exception:
            pass

    def _schedule_fuser_count_refresh(self):
        """Periodically refresh the fuser counter label to keep it in sync."""
        try:
            self._refresh_fuser_counter_row()
        except Exception:
            pass
        try:
            # Refresh every 2 seconds; lightweight call using process count
            self.after(2000, self._schedule_fuser_count_refresh)
        except Exception:
            pass

    def _refresh_connected_pcs(self):
        """Periodically refresh the connected fuser PCs count and list asynchronously."""
        if not hasattr(self, "connected_pcs_label"):
            return

        # Prevent overlapping scans
        if getattr(self, "_pcs_refresh_busy", False):
            # Try again shortly; avoid piling up
            self.after(2000, self._refresh_connected_pcs)
            return

        self._pcs_refresh_busy = True

        def _scan_and_update():
            try:
                cnt = 0
                names: list[str] | None = None
                try:
                    # Get list of connected PCs from heartbeats
                    names = list_connected_fuser_pc_names()
                    names_set = set(names) if names else set()
                    
                    # NEW: Add host baseline if we're the host (never shows 0 on host)
                    if is_host_machine():
                        try:
                            host_name = socket.gethostname()
                            names_set.add(host_name)
                        except Exception:
                            pass
                    
                    names = sorted(names_set)
                    cnt = len(names)
                except Exception:
                    # If any scanning error occurs, keep defaults
                    names = []

                def _apply():
                    try:
                        self.connected_pcs_label.config(text=f"Connected fuser PCs: {cnt}")
                        if names:
                            # Show each PC name on its own line for readability
                            # Limit total lines to avoid unbounded growth; append ellipsis if truncated
                            max_lines = 25
                            display_names = names[:max_lines]
                            suffix = "\n…" if len(names) > max_lines else ""
                            list_text = "\n".join(display_names) + suffix
                            self.connected_pcs_names_label.config(text=list_text)
                        else:
                            self.connected_pcs_names_label.config(text="(none)")
                    except Exception:
                        pass
                    finally:
                        # Allow future scans and schedule next refresh
                        self._pcs_refresh_busy = False
                        self.after(10000, self._refresh_connected_pcs)

                # Update UI on main thread
                self.after(0, _apply)
            except Exception:
                # Ensure busy flag clears and reschedule even on unexpected errors
                def _clear_and_resched():
                    self._pcs_refresh_busy = False
                    self.after(10000, self._refresh_connected_pcs)
                self.after(0, _clear_and_resched)

        # Run scan off the UI thread
        run_in_thread(_scan_and_update)

    def _open_working_folder(self):
        """
        One‑click: connect if needed, then open the working folder in Explorer.
        Opens the WorkingFuser subfolder (not just the share root).
        """
        # Get the WorkingFuser UNC path (includes the WorkingFuser subfolder)
        try:
            path = working_fuser_unc()
        except Exception:
            path = ""
        
        # Convert to local if we're on Host PC
        if path:
            path = unc_to_local_if_host(path)
        
        logging.info(f"[open_working_folder] Resolved WorkingFuser path: '{path}'")
        
        # Check if path is empty
        if not path:
            messagebox.showerror("Open Working Folder",
                                 "Working folder path is not configured.\n\n"
                                 "Please configure Host IP and Share Name in Offline Settings.")
            return
        
        # If it's a local path (Host PC), just open it directly
        if not path.startswith("\\\\"):
            logging.info(f"[open_working_folder] Opening local path: {path}")
            if os.path.exists(path):
                self.controller.open_folder_foreground(path)
            else:
                messagebox.showerror("Open Working Folder",
                                   f"Cannot access local path:\n{path}\n\n"
                                   "The folder may not exist yet. Try enabling fusers first.")
            return
        
        # For UNC paths (User PCs), ensure connection to the share root first
        share_root = resolve_shared_access_path()  # Just the share root for connection
        logging.info(f"[open_working_folder] Connecting to share root: {share_root}")
        
        if not connect_working_share_interactive(parent=self, silent=True):
            messagebox.showerror("Open Working Folder",
                                 f"Cannot access:\n{path}\n\n"
                                 "Use 'Test Access' button to diagnose the connection issue.")
            return

        # Once share is connected, open the WorkingFuser subfolder
        logging.info(f"[open_working_folder] Connection successful, opening WorkingFuser: {path}")
        
        # Verify the subfolder exists
        if not os.path.exists(path):
            messagebox.showerror("Open Working Folder",
                                 f"WorkingFuser folder doesn't exist:\n{path}\n\n"
                                 "Try enabling fusers first to create the folder.")
            return
        
        self.controller.open_folder_foreground(path)

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
        save_config()
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
            save_config()
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
        save_config()
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
            save_config()
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
        save_config()
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
            save_config()
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
        super().__init__(parent)
        set_background(controller, self)

        # Grid container for 4 cards (2 x 2)
        grid = tk.Frame(self, bg=self.cget("bg"), bd=0, highlightthickness=0)
        grid.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        for c in range(2):
            grid.grid_columnconfigure(c, weight=1, uniform="cards")
        for r in range(2):
            grid.grid_rowconfigure(r, weight=1, uniform="cards")

        # Helper to create a card and place it
        def create_card(row, col, title, items):
            card = TutorialCard(grid, title, items)
            card.grid(row=row, column=col, sticky="nsew", padx=10, pady=10)
            return card

        # Build 4 cards
        create_card(0, 0, "VBS4 Help", vbs4_help_items)
        create_card(0, 1, "BVI Help", bvi_help_items)
        create_card(1, 0, "One-Click Terrain Help", oct_help_items)
        create_card(1, 1, "Blue IG Help", blueig_help_items)

        # Back button (centered)
        footer = tk.Frame(self, bg=self.cget("bg"), bd=0, highlightthickness=0)
        footer.pack(pady=12)
        pb = globals().get("pill_button")
        if pb:
            pb(footer, "Back", lambda: controller.show('Main')).pack()
        else:
            DarkButtons.link(footer, "Back", lambda: controller.show('Main')).pack()


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

        tk.Label(card, text="Version: 2.0", font=("Helvetica", 18, "bold"),
                 bg="#222222", fg="white", anchor="w").pack(fill="x", pady=(0, 20))

        tk.Label(card, text="Special thanks to:", font=("Helvetica", 18, "bold"),
                 bg="#222222", fg="white", anchor="w").pack(fill="x")
        tk.Label(card, text="- The STE CFT team\n- All contributors and testers",
                 font=("Helvetica", 14), bg="#222222", fg="white", anchor="w",
                 justify="left").pack(fill="x", pady=(0, 20))

        tk.Button(card, text="Back", font=("Helvetica", 24), bg="#444444", fg="white",
                  width=25, height=2, command=lambda: controller.show('Main'),
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
                  bg="#444444", fg="white", width=25, height=2,
                  command=self.contact_support, bd=0, highlightthickness=0)\
            .pack(pady=(30, 10))
        tk.Button(card, text="Back", font=("Helvetica", 24), bg="#444444",
                  fg="white", width=25, height=2,
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
        pass

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

# =============================================================================
# Launcher with splash
# =============================================================================
def run_with_splash():
    # Prevent double instances in distro builds
    if not acquire_singleton():
        try:
            messagebox.showinfo("STE Toolkit", "Another instance is already running.")
        finally:
            return
    
    # Close PyInstaller's native splash immediately once Python has started
    if pyi_splash:
        try:
            pyi_splash.update_text("Initializing…")
            pyi_splash.close()
        except Exception:
            pass
    
    start_command_server()
    
    # Setup default config if needed
    if not config.has_section('General'):
        config.add_section('General')
        
    # update version number
    config['General']['app_version'] = '2.0'
    
    should_prompt_settings = not config['General'].getboolean('first_run_done', fallback=False)
    
    try:
        update_fuser_shared_path()
    except Exception as exc:
        pass
    
    # Create the main app but keep it hidden during the entire splash sequence
    app = MainApp()
    try:
        attach_tk_exception_hook(app)
    except Exception:
        pass
    # MainApp.__init__ already calls withdraw()
    
    # Clean up any orphaned fusers from previous sessions BEFORE starting new ones
    try:
        initial_count = count_local_fusers()
        logging.info(f"[startup-cleanup] Initial fuser count: {initial_count}")
        if initial_count > 0:
            logging.info(f"[startup-cleanup] Killing {initial_count} orphaned fuser(s)")
            kill_fusers()
            time.sleep(2.5)  # Wait for processes to terminate
            final_count = count_local_fusers()
            if final_count > 0:
                logging.warning(f"[startup-cleanup] {final_count} fuser(s) still running after cleanup, retrying...")
                kill_fusers()
                time.sleep(1.0)
            logging.info("[startup-cleanup] Cleanup complete")
        else:
            logging.info("[startup-cleanup] No orphaned fusers detected - clean start")
    except Exception as e:
        logging.error(f"[startup-cleanup] Failed to clean orphaned fusers: {e}")
    
    # Create and attach a splash that never steals focus
    splash_img = _resource_path(SPLASH_NAME)
    ver = "Version: 2.0"  # Explicitly set version to 2.0
    # Set min_display_time to 3.0 seconds to ensure splash shows long enough
    splash = SplashScreen(app, image_path=splash_img, version_text=ver, min_display_time=3.0)
    app.attach_splash(splash)
    
    # Process any pending UI updates while splash is showing
    app.update_idletasks()
    
    # We keep the main app withdrawn until the splash screen is done
    # We'll deiconify it in _finish_warmup method when the splash is closed
    
    # Ensure splash stays on top by forcing topmost again
    splash.lift()

    # Apply critical UI initialization immediately (don't delay buttons)
    # This ensures the navigation buttons are immediately visible
    
    # Make sure panels are fully initialized before continuing
    app.update_idletasks()
    
    # Apply immediate UI tasks if panels are ready
    if hasattr(app, 'panels') and 'OneClick' in app.panels:
        # Apply these synchronously without delay for better UI responsiveness
        try:
            apply_minimal_wizard_defaults()
            enforce_wizard_obj_only_defaults(log=app.panels['OneClick'].log_message)
        except Exception as exc:
            pass
    
    # Start non-blocking warmup work in parallel; splash will auto-close when done
    app.after(1, app.start_warmup_async)
    
    # Schedule the remaining non-UI initialization tasks 
    # with minimal delays to prevent UI freezing
    def setup_delayed_tasks():
        # Now app.panels should be initialized and we can safely access it

        if hasattr(app, 'panels') and 'OneClick' in app.panels:
            # Use a single short delay for background tasks
            app.after(5, update_fuser_shared_path)
            app.after(10, app.panels['OneClick'].update_fuser_state)
            
            # Improved fuser startup sequence: connect UNC first, then enable enforcement
            def _restore_then_enforce():
                global _allow_fuser_enforcement
                
                try:
                    # 1) Auto-connect to the host's WorkingFuser share FIRST
                    logging.info("[fuser-startup] Establishing UNC connection before fuser operations")
                    try:
                        run_in_thread(auto_connect_shared_working_folder)
                        # Give the connection a moment to establish
                        time.sleep(0.5)
                    except Exception as e:
                        logging.warning(f"[fuser-startup] UNC auto-connect failed: {e}")
                    
                    # 2) Ensure LocalFuser directories exist on UNC
                    try:
                        from photomesh_launcher import ensure_localfuser_dirs_on_unc, migrate_local_localfuser_to_unc_if_needed, get_fuser_counts, config as pm_config
                        desired_count = get_fuser_counts()[1]
                        ensure_localfuser_dirs_on_unc(pm_config, desired_count)
                        migrate_local_localfuser_to_unc_if_needed(pm_config)
                    except Exception as e:
                        logging.error(f"[fuser-startup] Failed to ensure LocalFuser folders on UNC: {e}")
                    
                    # 3) Now enable enforcement (this gates the policy to prevent premature kills)
                    logging.info("[fuser-startup] Enabling fuser enforcement now that UNC is ready")
                    _allow_fuser_enforcement = True
                    
                    # 4) Restore fusers - DISABLED, now using _autostart_fusers() instead
                    # restore_fusers_on_startup() uses old code that doesn't use per-instance workdirs
                    # Our new _autostart_fusers() at 3-second mark handles this properly
                    logging.info("[fuser-startup] Skipping restore_fusers_on_startup (using _autostart_fusers instead)")
                    # try:
                    #     restore_fusers_on_startup()
                    # except Exception as e:
                    #     logging.warning(f"[fuser-startup] Restore failed: {e}")
                    
                    # 5) Apply policy enforcement (won't kill if UNC check fails)
                    logging.info("[fuser-startup] Running first policy enforcement")
                    enforce_local_fuser_policy()
                    
                    # 6) Start presence heartbeat service
                    start_presence_service()
                    
                except Exception as e:
                    logging.error(f"[fuser-startup] Startup sequence failed: {e}")
            
            app.after(15, _restore_then_enforce)

            if should_prompt_settings:
                def _show_first_run_toast():
                    try:
                        app.show('Settings')
                    except Exception as exc:
                        pass
                    show_info_toast(app, "Review settings (host name, drive letter, RM install path)")
                    config['General']['first_run_done'] = 'True'
                    _save_config()

                app.after(100, _show_first_run_toast)

    # Schedule this sooner after the app's initialization is complete
    app.after(20, setup_delayed_tasks)
    
    # Auto-start fusers after UI is fully loaded (readiness-gated)
    def _autostart_fusers():
        global _skip_fuser_enforcement_at_startup
        
        print("\n" + "="*80)
        print("🚀 AUTO-START TRIGGERED after UI ready (6-second delay elapsed)")
        print("="*80 + "\n")
        logging.info("[startup] 🚀 Auto-starting fusers...")
        try:
            show_info_toast(app, "Starting fusers now…", duration_ms=3000)
        except Exception:
            pass
        try:
            post_ui(log_to_console, "> Starting fusers now…")
        except Exception:
            pass
        
        # Determine target count based on machine role
        is_fuser = config["Fusers"].getboolean("fuser_computer", fallback=False)
        print(f"📋 fuser_computer setting: {is_fuser}")
        
        if not is_fuser:
            print("⚠️ Not a fuser computer - SKIPPING auto-start")
            logging.info("[startup] Not a fuser computer, skipping auto-start")
            _skip_fuser_enforcement_at_startup = False
            return
        
        # Get target count from config
        host_ct, desired_ct = get_fuser_counts()
        is_host = is_host_machine()
        
        print(f"📊 Host count: {host_ct}, User count: {desired_ct}")
        print(f"🖥️ Is host machine: {is_host}")
        
        if is_host:
            target = host_ct
            print(f"✓ HOST mode: Will launch {target} fuser(s)")
            logging.info(f"[startup] Host machine: auto-starting {target} fuser(s)")
        else:
            target = desired_ct
            print(f"✓ USER mode: Will launch {target} fuser(s)")
            logging.info(f"[startup] User machine: auto-starting {target} fuser(s)")
        
        # Readiness-gated auto-start loop
        def _auto_start_tick():
            try:
                try:
                    machine_ip = get_primary_ipv4()
                except Exception:
                    machine_ip = ""
                frozen = is_frozen_build()
                configured_host = get_host_ip() or get_host()
                logging.info(f"[startup] auto-start tick: frozen={frozen} host={is_host} ip={machine_ip} configured_host={configured_host}")

                ready, diag = ready_for_fusers()
                # Structured readiness logs
                logging.info(f"[ready] exe_ok={diag.get('exe_ok')} path=\"{diag.get('exe_path','')}\"")
                logging.info(f"[ready] share_ok={diag.get('share_ok')} root=\"{diag.get('working_root','')}\" write_test={diag.get('write_test')}")
                logging.info(f"[ready] seed_ok={diag.get('seed_ok')} seed_pids={diag.get('seed_pids')}")
                logging.info(f"[ready] loopback_ok={diag.get('loopback_ok')}")
                logging.info(f"[ready] -> ready={diag.get('ready')}")

                if not ready:
                    # Try again in 500ms
                    try:
                        app.after(500, _auto_start_tick)
                    except Exception:
                        pass
                    return

                # Clear the skip flag FIRST so enforcement can run
                print("🔓 Clearing enforcement skip flag")
                global _skip_fuser_enforcement_at_startup
                _skip_fuser_enforcement_at_startup = False

                # Launch fusers in a background thread to avoid blocking UI
                def _launch_in_background():
                    try:
                        print("🧵 Background launch thread STARTED")
                        logging.info("[startup] Background fuser launch thread started")

                        existing_count = count_local_fusers()
                        print(f"📊 Existing fuser count: {existing_count}")
                        logging.info(f"[startup] Existing fuser count: {existing_count}")

                        print(f"▶️ Calling ensure_fuser_instances({target})...")
                        logging.info(f"[startup] About to call ensure_fuser_instances({target})")
                        ensure_fuser_instances(target)

                        final_running = count_local_fusers()
                        print(f"✅ AUTO-START COMPLETE: {final_running}/{target} fusers running")
                        logging.info(f"[startup] Fuser auto-start complete. Running: {final_running}/{target}")

                        # Persist a first-run completion marker
                        try:
                            flag = _first_run_flag_path()
                            with open(flag, 'w', encoding='utf-8') as f:
                                f.write('ok')
                        except Exception:
                            pass

                        try:
                            show_info_toast(app, f"Fusers {final_running}/{target} started", duration_ms=3500)
                        except Exception:
                            pass
                        try:
                            post_ui(log_to_console, f"> Fusers {final_running}/{target} started")
                        except Exception:
                            pass

                        try:
                            refresh_settings_panel_from_config()
                        except Exception:
                            pass
                    except Exception as e:
                        import traceback
                        error_msg = traceback.format_exc()
                        print(f"❌ AUTO-START FAILED: {e}")
                        print(error_msg)
                        logging.error(f"[startup] Fuser auto-start failed: {e}")
                        logging.error(f"[startup] Traceback: {error_msg}")

                import threading
                print("🧵 Starting background launch thread...")
                threading.Thread(target=_launch_in_background, daemon=True).start()
                logging.info("[startup] Background fuser launch thread dispatched")
            except Exception as e:
                logging.error(f"[startup] auto-start tick failed: {e}")

        # Start the readiness loop immediately
        _auto_start_tick()
    
    # Register a post-UI scheduler so the message appears AFTER the splash and window show
    def _schedule_post_ui_autostart():
        try:
            print("(fusers starting ~6 seconds)")
            logging.info("[startup] Scheduled fuser auto-start ~6 seconds after UI ready")
            # Visible UI hint for users (toast + log panel)
            try:
                show_info_toast(app, "Fusers will start in ~6 seconds", duration_ms=3500)
            except Exception:
                pass
            try:
                post_ui(log_to_console, "> Fusers will start in ~6 seconds")
            except Exception:
                pass
        except Exception:
            pass
        # Start the gating-based auto-start after a short grace period
        app.after(1000, _autostart_fusers)

    setattr(app, "_schedule_post_ui_autostart", _schedule_post_ui_autostart)
    logging.info("[startup] Registered post-UI fuser auto-start callback")

    print("\n" + "="*80)
    print("✅ MAINLOOP STARTING - App window should open now")
    print("="*80 + "\n")
    logging.info("[startup] About to start mainloop()")
    app.mainloop()
    print("\n" + "="*80)
    print("🛑 MAINLOOP EXITED - App was closed by user")
    print("="*80 + "\n")
    logging.info("[startup] mainloop() exited (app closed)")

if __name__ == "__main__":
    run_with_splash()
