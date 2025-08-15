import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, messagebox
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
from tkinter import simpledialog
import re
import socket
import threading
import shlex
from post_process_utils import clean_project_settings
from launch_photomesh_preset import launch_photomesh_with_preset
from collections import OrderedDict
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

try:  # Optional atomic write helper
    from steup.utils import write_config_atomic  # type: ignore
except Exception:  # pragma: no cover - helper may not exist
    write_config_atomic = None

# Win32 constants for tweaking window styles:
GWL_STYLE        = -16
WS_BORDER        = 0x00800000
WS_DLGFRAME      = 0x00400000
SWP_NOMOVE       = 0x0002
SWP_NOSIZE       = 0x0001
SWP_NOZORDER     = 0x0004
SWP_FRAMECHANGED = 0x0020

logging.basicConfig(
    level=logging.INFO,
    filename='ste_toolkit.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

_lock_file = None
#------------SINGLETON DEF------------------------------------------------------
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

def run_in_thread(target, *args, **kwargs):
    """Run *target* in a background daemon thread."""
    thread = threading.Thread(target=target, args=args,
                             kwargs=kwargs, daemon=True)
    thread.start()

# ---------------------------------------------------------------------------
# PhotoMesh progress helpers
# ---------------------------------------------------------------------------

def extract_progress(line: str) -> int | None:
    """Return progress percent from a log line if present."""
    if "Progress:" in line:
        m = re.search(r"Progress:\s*(\d+)%", line)
        if m:
            return int(m.group(1))
    m = re.search(r"Tile\s+(\d+)\s+of\s+(\d+)", line)
    if m:
        done, total = map(int, m.groups())
        if total:
            return int(done / total * 100)
    return None


#==============================================================================
# NETWORK HELPERS
#==============================================================================

def get_local_ip():
    """Return the primary IPv4 address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # connecting to an external host does not actually send data
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


#==============================================================================
# VBS4 INSTALL PATH FINDER
#==============================================================================

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

def get_vbs4_launcher_path():
    # First, check the config file
    path = config['General'].get('vbs4_setup_path', '').strip()
    if path and os.path.isfile(path):
        logging.info("VBS4 Launcher path found in config: %s", path)
        return path

    # If not in config, try to find it
    possible_paths = [
        r"C:\BISIM\VBS4",
        r"C:\Builds\VBS4",
        r"C:\Builds",
        r"C:\Bohemia Interactive Simulations"
    ]

    for base_path in possible_paths:
        if os.path.isdir(base_path):
            # Look for VBS4 directories. Some installations may place the
            # version number directly under the VBS4 folder.  Allow
            # numeric names as well as those prefixed with "VBS4".
            vbs4_dirs = [
                d for d in os.listdir(base_path)
                if d.startswith("VBS4") or re.match(r"^[0-9]", d)
            ]
            vbs4_dirs.sort(reverse=True)  # Sort in descending order to get the latest version first
            
            for vbs4_dir in vbs4_dirs:
                full_path = os.path.join(base_path, vbs4_dir, "VBSLauncher.exe")
                if os.path.isfile(full_path):
                    logging.info("VBS4 Launcher path found: %s", full_path)
                    # Save the found path to config
                    config['General']['vbs4_setup_path'] = full_path
                    with open(CONFIG_PATH, 'w') as f:
                        config.write(f)
                    return full_path

    # If not found in the usual locations, try to find it relative to VBS4.exe
    vbs4_exe = get_vbs4_install_path()
    if vbs4_exe:
        base = os.path.dirname(vbs4_exe)
        launcher_path = os.path.join(base, 'VBSLauncher.exe')
        if os.path.isfile(launcher_path):
            logging.info("VBS4 Launcher path found relative to VBS4.exe: %s", launcher_path)
            config['General']['vbs4_setup_path'] = launcher_path
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
            return launcher_path

    logging.warning("VBS4 Launcher path not found")
    return ''
#==============================================================================
# VERSION DISPLAY FUNCTIONS
#==============================================================================

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
    # handle paths like ".../VBS4/25.1/VBS4.exe" or "VBS4 25.1" etc.
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
    match = re.search(r'ARES-dev-release-v(\d+\.\d+\.\d+)', file_path)
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

# ---------------------------------------------------------------------------
# Reality Mesh post-processing helpers
# ---------------------------------------------------------------------------

def find_reality_mesh_to_vbs4_link() -> str:
    """Return the path to the Reality Mesh to VBS4 shortcut if found."""
    default = (r"C:\\Bohemia Interactive Simulations\\Reality Mesh to VBS4 25.1\\"
               r"Reality Mesh to VBS4.lnk")
    if os.path.isfile(default):
        return default
    search_root = r"C:\\Bohemia Interactive Simulations"
    for dirpath, _dirnames, filenames in os.walk(search_root):
        for name in filenames:
            if name.lower() == "reality mesh to vbs4.lnk":
                return os.path.join(dirpath, name)
    return ""

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


def wait_for_file(path: str, poll_interval: float = 5.0) -> None:
    while not os.path.exists(path):
        time.sleep(poll_interval)


def find_output_json(start_dir: str) -> str | None:
    """Return path to Output-CenterPivotOrigin.json under *start_dir* if found."""
    for root, _dirs, files in os.walk(start_dir):
        if 'Output-CenterPivotOrigin.json' in files:
            return os.path.join(root, 'Output-CenterPivotOrigin.json')
    return None


def wait_for_output_json(start_dir: str, poll_interval: float = 5.0) -> str:
    """Search *start_dir* repeatedly until the output JSON exists."""
    json_path = find_output_json(start_dir)
    while not json_path or not os.path.exists(json_path):
        time.sleep(poll_interval)
        json_path = find_output_json(start_dir)
    return json_path


def create_project_folder(build_dir: str, project_name: str, dataset_root: str | None = None) -> tuple[str, str]:
    """Create the project directory structure used by Reality Mesh.

    A folder named ``<project_name>_<timestamp>`` is created under
    ``dataset_root`` when provided or ``build_dir`` otherwise.  A ``data``
    subfolder is also ensured inside the project folder.
    """

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    base = dataset_root if dataset_root else build_dir
    if base:
        os.makedirs(base, exist_ok=True)
    proj_folder = os.path.join(base, f"{project_name}_{ts}")

    os.makedirs(proj_folder, exist_ok=True)
    data_folder = os.path.join(proj_folder, 'data')
    os.makedirs(data_folder, exist_ok=True)
    return proj_folder, data_folder


def set_active_wizard_preset(preset_name="CPP&OBJ"):
    import os
    import json

    config_path = os.path.join(
        os.environ.get("APPDATA", ""),
        "Skyline", "PhotoMesh", "Wizard", "config.json"
    )

    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    config = {
        "SelectedPreset": preset_name,
        "OverrideSettings": True,
        "AutoBuild": True  # Optional: auto-start build
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"✅ Set {preset_name} as active preset in Wizard config")


def enable_obj_in_photomesh_config():
 config_path = r"C:\Program Files\Skyline\PhotoMeshWizard\config.json"

 config_path = r"C:\Program Files\Skyline\PhotoMeshWizard\config.json"

 try:
    with open(config_path, 'r') as f:
        config = json.load(f)

    # Ensure the structure exists before editing
    if "DefaultPhotoMeshWizardUI" not in config:
        config["DefaultPhotoMeshWizardUI"] = {}
    if "Model3DFormats" not in config["DefaultPhotoMeshWizardUI"]:
        config["DefaultPhotoMeshWizardUI"]["Model3DFormats"] = {}

    # ✅ Enable OBJ
    config["DefaultPhotoMeshWizardUI"]["Model3DFormats"]["OBJ"] = True

    # ❌ Disable 3DML
    config["DefaultPhotoMeshWizardUI"]["Model3DFormats"]["3DML"] = False

    # Save changes
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)

    print("✅ OBJ enabled and 3DML disabled in config.json")

 except Exception as e:
        print(f"❌ Failed to update config.json: {e}")

def _copytree_progress(src: str, dst: str, progress_cb=None) -> None:
    """Recursively copy *src* to *dst* reporting progress."""
    files = []
    for root, _, filenames in os.walk(src):
        for f in filenames:
            files.append(os.path.join(root, f))

    total = len(files)
    copied = 0
    for root, _, filenames in os.walk(src):
        rel = os.path.relpath(root, src)
        dest_dir = os.path.join(dst, rel)
        os.makedirs(dest_dir, exist_ok=True)
        for f in filenames:
            shutil.copy2(os.path.join(root, f), os.path.join(dest_dir, f))
            copied += 1
            if progress_cb and total:
                progress_cb(int(copied / total * 100))


def copy_tiles(build_dir: str, data_folder: str, progress_cb=None) -> None:
    """Copy raw tile data from *build_dir* into *data_folder*."""
    for name in ('Tiles', 'OBJ'):
        src = os.path.join(build_dir, name)
        if os.path.isdir(src):
            dst = os.path.join(data_folder, name)
            if os.path.exists(dst):
                shutil.rmtree(dst)
            _copytree_progress(src, dst, progress_cb)
            break


def _parse_offset_coordsys(wkt: str) -> str:
    zone = ''
    hemi = ''
    m = re.search(r"UTM zone\s*(\d+),\s*(Northern|Southern)", wkt)
    if m:
        zone = m.group(1)
        hemi = 'N' if m.group(2).startswith('Northern') else 'S'
    return f"UTM zone:{zone} hemi:{hemi} horiz_units:Meters vert_units:Meters"


def write_project_settings(settings_path: str, data: dict, data_folder: str) -> None:
    """Write the Reality Mesh settings file for *data*.

    ``data_folder`` is ensured to exist and used for the ``source_Directory``
    setting.  The same path is also written under a ``[BiSimOneClickPath]``
    section.
    """

    defaults = OrderedDict([
        ("export_format", "OBJ"),
        ("center_pivot_to_project", "true"),
        ("orthocam_Resolution", "0.05"),
        ("orthocam_Render_Lowest", "1"),
        ("tin_to_dem_Resolution", "0.5"),
        ("sel_Area_Size", "0.5"),
        ("tile_scheme", "/Tile_%d_%d_L%d"),
        ("collision", "true"),
        ("visualLODs", "true"),
        ("project_vdatum", "WGS84_ellipsoid"),
        ("offset_models", "-0.2"),
        ("csf_options", "2 0.5 false 0.65 2 500"),
        ("faceThresh", "500"),
        ("lodThresh", "5"),
        ("tileSize", "100"),
        ("srfResolution", "0.5"),
    ])

    project_name = data.get('project_name', 'project')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    origin = data.get('Origin', [0, 0, 0])
    wkt = data.get('WKT', '')

    settings = OrderedDict()
    settings['project_name'] = f"{project_name} ({timestamp})"
    os.makedirs(data_folder, exist_ok=True)
    settings['source_Directory'] = data_folder
    settings['offset_coordsys'] = _parse_offset_coordsys(wkt) + '(centerpointoforigin)'
    settings['offset_hdatum'] = 'WGS84'
    settings['offset_vdatum'] = 'WGS84_ellipsoid'
    settings['offset_x'] = f"{origin[0]}(centerpointoforigin)"
    settings['offset_y'] = f"{origin[1]}(centerpointoforigin)"
    settings['offset_z'] = f"{origin[2]}(centerpointoforigin)"
    settings.update(defaults)

    with open(settings_path, 'w', encoding='utf-8') as f:
        for key, value in settings.items():
            f.write(f"{key}={value}\n")
        f.write("\n[BiSimOneClickPath]\n")
        f.write(f"path={data_folder}\n")


def run_processor(ps_script: str, settings_path: str, log_func=lambda msg: None) -> None:
    """Run the Reality Mesh PowerShell script via a project-specific batch file."""
    batch_path = os.path.join(os.path.dirname(settings_path), 'RealityMeshProcess.bat')

    with open(batch_path, 'w', encoding='utf-8') as f:
        f.write(
            f'start "" powershell -executionpolicy bypass "{ps_script}" "{settings_path}" 1\n'
        )

    log_func(f'Created batch file {batch_path}')
    subprocess.run(batch_path, check=True)


def run_remote_processor(ps_script: str, target_ip: str, settings_path: str,
                         log_func=lambda msg: None,
                         progress_cb=lambda p: None) -> None:
    """Execute *ps_script* on *target_ip* passing it *settings_path*.

    Output from the PowerShell process is streamed back and parsed for
    progress updates using :func:`extract_progress`.
    """
    if not os.path.isfile(ps_script):
        raise FileNotFoundError(f'PowerShell script not found: {ps_script}')
    cmd = [
        'powershell',
        '-ExecutionPolicy', 'Bypass',
        '-File', ps_script,
        target_ip,
        settings_path,
    ]
    log_func('Running: ' + ' '.join(cmd))
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    ) as proc:
        for line in proc.stdout:
            line = line.rstrip("\r\n")
            log_func(line)
            percent = extract_progress(line)
            if percent is not None:
                progress_cb(percent)
        proc.wait()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)


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


def kill_fusers() -> None:
    if os.name == 'nt':
        subprocess.run(['taskkill', '/IM', 'Fuser.exe', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def create_realitymesh_dataset(project_name: str, source_obj_folder: str,
                               origin_json_path: str, datasets_base: str,
                               config_path: str) -> str:
    """Create a RealityMesh dataset folder and settings file.

    Parameters
    ----------
    project_name : str
        Name of the dataset/project.
    source_obj_folder : str
        Path to the OBJ folder output from PhotoMesh.
    origin_json_path : str
        Path to the ``Output-CenterPivotOrigin.json`` file used to obtain
        ``offset_x``, ``offset_y`` and ``offset_z`` values.
    datasets_base : str
        Root folder where RealityMesh datasets should be stored.
    config_path : str
        Path to the global ``config.ini`` that will receive/contain the
        ``[BiSimOneClickPath]`` section.

    Returns
    -------
    str
        The full path to the newly created dataset project folder.
    """

    dataset_folder = os.path.join(datasets_base, project_name)
    os.makedirs(dataset_folder, exist_ok=True)

    with open(origin_json_path, 'r', encoding='utf-8') as f:
        origin_data = json.load(f)

    origin = origin_data.get('Origin') or origin_data.get('origin')
    if isinstance(origin, (list, tuple)) and len(origin) >= 3:
        offset_x, offset_y, offset_z = origin[:3]
    else:
        offset_x = origin_data.get('offset_x', 0)
        offset_y = origin_data.get('offset_y', 0)
        offset_z = origin_data.get('offset_z', 0)

    settings_path = os.path.join(dataset_folder, f"{project_name}-settings.txt")
    lines = [
        f"project_name={project_name}",
        f"source_Directory={source_obj_folder}",
        "offset_coordsys=UTM zone:11 hemi:N horiz_units:Meters vert_units:Meters",
        "offset_hdatum=WGS84",
        "offset_vdatum=WGS84_ellipsoid",
        f"offset_x={offset_x}",
        f"offset_y={offset_y}",
        f"offset_z={offset_z}",
        "orthocam_Resolution=0.25",
        "orthocam_Render_Lowest=1",
        "tin_to_dem_Resolution=0.5",
        "sel_Area_Size=0.5",
        "tile_scheme=/Tile_%d_%d_L%d",
        "collision=true",
        "visualLODs=true",
        "project_vdatum=WGS84_ellipsoid",
        "offset_models=-0.2",
        "csf_options=2 0.5 false 0.65 2 500",
        "faceThresh=500",
        "lodThresh=5",
        "tileSize=100",
        "srfResolution=0.5",
        "",
        "[BiSimOneClickPath]",
        f"path={dataset_folder}"
    ]
    with open(settings_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    cfg = configparser.ConfigParser()
    cfg.read(config_path)
    if 'BiSimOneClickPath' not in cfg:
        cfg['BiSimOneClickPath'] = {}
    cfg['BiSimOneClickPath']['path'] = dataset_folder
    with open(config_path, 'w') as cfg_file:
        cfg.write(cfg_file)

    return dataset_folder

#==============================================================================
# CONFIGURATION - APP ICON APPLICATION
#==============================================================================

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.ini')
ICON_NAME   = 'icon.ico'

config      = configparser.ConfigParser()
config.read(CONFIG_PATH)

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
        # ``after_idle`` may not exist on some custom widgets; fallback
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
    config['General']['fullscreen'] = 'False'  # Set a default value
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
       

#==============================================================================
# AUTO-LAUNCH CONFIG
#==============================================================================

if 'Auto-Launch' not in config:
    config['Auto-Launch'] = {
        'enabled': 'False',
        'program_path': '',
        'arguments': ''
    }
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)

#------------------------------------------------------------------------------
# FUSER CONFIG
#------------------------------------------------------------------------------

if 'Fusers' not in config:
    config['Fusers'] = {
        'config_path': 'fuser_config.json',
        'local_fuser_exe': r'C:\\Program Files\\Skyline\\PhotoMesh\\Fuser\\Fuser.exe',
        'remote_fuser_exe': r'C:\\Program Files\\Skyline\\PhotoMesh Fuser\\PhotoMeshFuser.exe',
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

# Update the shared fuser path in the JSON config. If *project_path* is a UNC
# path, derive the host from it; otherwise fall back to the local machine name.
def update_fuser_shared_path(project_path: str | None = None) -> None:
    # If no project path is supplied only update when this machine is marked as
    # a fuser computer
    if project_path is None and not config['Fusers'].getboolean('fuser_computer', False):
        return

    config_file = config['Fusers'].get('config_path', 'fuser_config.json')
    cfg_path = os.path.join(BASE_DIR, config_file) if not os.path.isabs(config_file) else config_file

    stored_host = config['Fusers'].get('working_folder_host', '').strip()
    env_host = os.environ.get('COMPUTERNAME') or socket.gethostname().split('.')[0]

    host = stored_host

    # If project path is a UNC path, derive host from path
    if project_path and project_path.startswith('\\'):
        parts = project_path.strip('\\').split('\\')
        if parts:
            host = parts[0]

    # If this is a fuser computer and no host is set, use local hostname
    elif config['Fusers'].getboolean('fuser_computer', False) and not host:
        host = env_host

    # Do not overwrite manually set host otherwise

    try:
        with open(cfg_path, 'r') as f:
            data = json.load(f)
    except Exception:
        data = {}

    data.setdefault('fusers', {'localhost': [{'name': 'LocalFuser'}]})
    data['shared_path'] = f"\\\\{host}\\SharedMeshDrive\\WorkingFuser"

    try:
        with open(cfg_path, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error("Failed to update fuser config: %s", e)

    # Only write config if the host changed
    if stored_host != host:
        config['Fusers']['working_folder_host'] = host
        with open(CONFIG_PATH, 'w') as f:
            config.write(f)

def is_auto_launch_enabled() -> bool:
    return config.getboolean('Auto-Launch', 'enabled', fallback=False)

def get_auto_launch_cmd() -> tuple[str, list[str]]:
    path = config['Auto-Launch'].get('program_path', '').strip()
    raw_args = config['Auto-Launch'].get('arguments', '').strip()
    args = raw_args.split() if raw_args else []
    return path, args

#==============================================================================
# SETTINGS HELPERS
#==============================================================================

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

#==============================================================================
# COMMAND LAUNCH HELPERS
#==============================================================================
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

def create_app_button(parent, app_name, get_path_func, launch_func, set_path_func):
    frame = tk.Frame(parent, bg="#333333")
    frame.pack(pady=8)

    path = clean_path(get_path_func())
    
    if not path or not os.path.exists(path):
        state = "disabled"
        bg_color = "#888888"
    else:
        state = "normal"
        bg_color = "#444444"

    button = tk.Button(
        frame,
        text=f"Launch {app_name}",
        font=("Helvetica", 20),
        bg=bg_color,
        fg="white",
        state=state,
        command=launch_func
    )
    button.pack(side=tk.LEFT, ipadx=10, ipady=5)

    if state == "disabled":
        question_button = tk.Button(
            frame,
            text="?",
            font=("Helvetica", 16, "bold"),
            bg="orange",
            fg="black",
            command=set_path_func
        )
        question_button.pack(side=tk.LEFT, padx=(5, 0))

    # Version label
    version_label = tk.Label(
        frame,
        text="",
        font=("Helvetica", 16),
        bg="#333333",
        fg="white"
    )
    version_label.pack(side=tk.LEFT, padx=10)

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
        return True  # User chose to skip

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

def ensure_executable(config_key: str, exe_name: str, prompt_title: str) -> str:
    path = clean_path(config['General'].get(config_key, '').strip())
    # 1) Try what we already have in config
    if path and os.path.isfile(path):
        return path

    # 2) Try auto-find logic (registry, standard folders, etc.)
    if isinstance(exe_name, str):
        candidate = exe_name.lower()
        if candidate == 'vbs4.exe':
            path = get_vbs4_install_path()
        elif candidate == 'blueig.exe':
            path = get_blueig_install_path()
        elif candidate == 'vbslauncher.exe':
            path = get_vbs4_launcher_path()
        else:
            path = find_executable(exe_name)
    else:
        # exe_name might be a list of possible names
        for name in exe_name:
            path = find_executable(name)
            if path:
                break

    if path and os.path.isfile(path):
        # store it for next time unless it's the VBS4 path
        if config_key != 'vbs4_path':
            config['General'][config_key] = clean_path(path)
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
        return path

      # 3) Fallback: prompt the user (must pass BOTH arguments!)
    if not prompt_for_exe(prompt_title, config_key):  # Changed from exe_name to prompt_title
        raise FileNotFoundError(f"No executable selected for '{config_key}'.")

    # prompt_for_exe wrote the new path into config
    path = config['General'][config_key]
    return path

# BVI (ARES Manager)

def get_bvi_batch_file() -> str:
    """Return path to a temporary batch file for launching BVI."""
    ares_exe = ensure_executable(
        'bvi_manager_path',
        ['ares.manager.exe', 'ARES.Manager.exe'],
        "Select ARES Manager executable",
    )
    return create_bvi_batch_file(ares_exe)

def get_blueig_install_path() -> str:
    path = config['General'].get('blueig_path', '')
    if not path or not os.path.isfile(path):
        path = find_executable('BlueIG.exe')
        if path:
            config['General']['blueig_path'] = path
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
    return path or ''

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
    # 1) Get (or ask for) the full path to BlueIG.exe
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
            webbrowser.open(url, new=2)
        except Exception:
            messagebox.showinfo("BVI", "Note: BVI must be running")

    run_in_thread(_open)
       
# ─── BACKGROUND & LOGOS ──────────────────────────────────────────────────────

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
        img = Image.open(background_image_path)
        img = img.resize((screen_width, screen_height), Image.Resampling.LANCZOS)
        ph  = ImageTk.PhotoImage(img)
        lbl = tk.Label(widget or window, image=ph)
        lbl.image = ph
        lbl.place(x=0, y=0, relwidth=1, relheight=1)

    # logos
    if not isinstance(window, (tk.Tk, tk.Toplevel)) or getattr(window, "_logos_placed", False):
        return
    window._logos_placed = True

    def place_logos():
        coords = [
            (int(screen_width * 0.125),  int(screen_height * 0.02), logo_STE_path,   (70, 70)),
            (int(screen_width * 0.1875), int(screen_height * 0.02), logo_AFC_army,   (60, 70)),
            (int(screen_width * 0.2375), int(screen_height * 0.02), logo_first_army, (45, 75)),
            (int(screen_width * 0.83125), int(screen_height * 0.02), logo_us_army_path, (200, 76)),
        ]
        for x,y,path,(w,h) in coords:
            if os.path.exists(path):
                img   = Image.open(path).convert("RGBA").resize((w,h), Image.Resampling.LANCZOS)
                ph    = ImageTk.PhotoImage(img)
                lbl2  = tk.Label(window, image=ph, bg="black")
                lbl2.image = ph
                lbl2.place(x=x, y=y)

    # Use after() to ensure the window is fully initialized
    window.after(100, place_logos)

def set_wallpaper(window):
    if not os.path.exists(background_image_path):
        return

    # get actual window dimensions
    w = window.winfo_width()
    h = window.winfo_height()

    img = Image.open(background_image_path).resize((w, h), Image.Resampling.LANCZOS)
    ph  = ImageTk.PhotoImage(img)
    lbl = tk.Label(window, image=ph)
    lbl.image = ph
    lbl.place(relwidth=1, relheight=1)
    
# ─── TUTORIALS PANEL DATA ────────────────────────────────────────────────────

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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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
    # List of possible locations for the BVI documentation
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
oct_help_items = {
    "How to collect terrain scans w/ Drone":   lambda: messagebox.showinfo("Drone Scans","Coming soon…"),
    "How to import terrain scans from drone":  lambda: messagebox.showinfo("Import Scans","Coming soon…"),
    "How to: Simulated Terrain":               lambda: messagebox.showinfo("Simulated Terrain","Coming soon…"),
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

# ======================== SETUP & CONFIGURATION ========================= #

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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

def get_ares_manager_path() -> str:
    """Return saved ARES Manager path if it exists, else empty string."""
    path = config['General'].get('bvi_manager_path', '')
    if path and os.path.isfile(path):
        return path
    return ''

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
    # you can also set defaults if you want:
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
    # build URL with both loginName and vbsFullComputerName
    url = (
        f"http://{host}:{port}/#/external/login"
        f"?loginName={user}"
        f"&vbsFullComputerName={user}"
    )

    def _check_and_open():
        try:
            urllib.request.urlopen(f"http://{host}:{port}", timeout=1)
            webbrowser.open(url, new=2)
        except Exception:
            messagebox.showinfo(
                "External Map",
                "Note: VBS Map server must be running"
            )

    run_in_thread(_check_and_open)

def make_borderless(hwnd):
    """Strip only the thin border & titlebar out of a real toplevel."""
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
    # turn off WS_BORDER | WS_DLGFRAME
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

    # Add label for instructions
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
        apply_app_icon(self)
        self.title("STE Mission Planning Toolkit")
         # Prevent window resizing
        self.resizable(False, False)

        # List of buttons that can receive keyboard focus
        self.focusable_buttons = []

        self.fullscreen = config.getboolean('General', 'fullscreen', fallback=False)

        # screen dims
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        # monitor work area (excludes taskbar)
        mon  = win32api.MonitorFromPoint((0,0))
        wr   = win32api.GetMonitorInfo(mon)['Work']  # (l,t,r,b)
        wx1, wy1, wx2, wy2 = wr
        ww, wh = wx2-wx1, wy2-wy1

        # decide initial geometry & style
        if self.fullscreen:
            # size to work-area, strip only border/title
            self.geometry(f"{ww}x{wh}+{wx1}+{wy1}")
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            make_borderless(hwnd)

        else:
            # normal windowed
            w, h = 1660, 800
            x = (sw - w)//2
            y = (sh - h)//2
            self.geometry(f"{w}x{h}+{x}+{y}")

        set_background(self)

        close_btn = tk.Button(self, text="✕",
                              font=("Helvetica",12,"bold"),
                              bg="red", fg="white", bd=0,
                              command=self.destroy)
        close_btn.place(relx=1.0, x=-40, y=5, width=30, height=30)

        self.content = tk.Frame(self)
        self.content.pack(expand=True, fill="both")

        nav = tk.Frame(self.content, width=200, bg='#333333')
        nav.pack(side='left', fill='y')

        self.panels_container = tk.Frame(self.content)
        self.panels_container.pack(side='right', expand=True, fill='both')

        # Instantiate each panel, passing `self` as the controller
        self.panels = {
            'Main':      MainMenu(self.panels_container, self),
            'VBS4':      VBS4Panel(self.panels_container, self),
            'BVI':       BVIPanel(self.panels_container, self),
            'Settings':  SettingsPanel(self.panels_container, self),
            'Tutorials': TutorialsPanel(self.panels_container, self),
            'Credits':   CreditsPanel(self.panels_container, self),
            'Contact Us': ContactSupportPanel(self.panels_container, self),
        }

        # Stack all panels in the same location and raise the active one
        for panel in self.panels.values():
            panel.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Build the nav buttons
        nav_tip = Tooltip(nav)
        for key, label in [
            ('Main',     'Home'),
            ('VBS4',     'VBS4 / BlueIG'),
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

    def toggle_fullscreen(self):
        """Call this (e.g. on F11) to go borderless-workarea ↔ windowed."""
        self.fullscreen = not self.fullscreen
        # save back to config if you like...
        if self.fullscreen:
            # apply borderless workarea
            mon  = win32api.MonitorFromPoint((0,0))
            wr   = win32api.GetMonitorInfo(mon)['Work']
            x1,y1,x2,y2 = wr
            self.geometry(f"{x2-x1}x{y2-y1}+{x1}+{y1}")
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            make_borderless(hwnd)
        else:
            # restore windowed
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            w, h = 1660, 800
            x = (sw - w)//2
            y = (sh - h)//2
            # re-add standard frame by resetting style bits:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            style |= (WS_BORDER | WS_DLGFRAME)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            ctypes.windll.user32.SetWindowPos(
                hwnd, None, 0,0,0,0,
                SWP_NOMOVE|SWP_NOSIZE|SWP_NOZORDER|SWP_FRAMECHANGED
            )
            self.geometry(f"{w}x{h}+{x}+{y}")

    def update_button_state(self, button, path_key):
        """Update button state based on whether the executable exists."""
        path = config['General'].get(path_key, '')
        if path and os.path.exists(path):
            button.config(state="normal")
        else:
            button.config(state="disabled")

    def show(self, name):
        """Raise the given panel without unpacking others."""
        panel = self.panels[name]
        panel.tkraise()
        self.current = name
        if name == "VBS4":
            self.update_button_state(panel.vbs4_button, 'vbs4_path')
            self.update_button_state(panel.vbs4_launcher_button, 'vbs4_setup_path')
            self.update_button_state(panel.vbs_license_button, 'vbs_license_manager_path')
            self.update_button_state(panel.blueig_button, 'blueig_path')
        elif name == "BVI":
            self.update_button_state(panel.bvi_button, 'bvi_manager_path')

        # Refresh navigation list whenever a new panel is shown
        self.update_navigation()

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
   
# ─── ---------------- MAINMENU PANEL --------------------------------- ──────────

class MainMenu(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        set_wallpaper(self)
        set_background(controller, self)
        controller.create_tutorial_button(self)   # <— keeps the “?” button

        tk.Label(
            self,
            text="STE Mission Planning Toolkit",
            font=("Helvetica", 36, "bold"),
            bg="black", fg="white", pady=20
        ).pack(fill="x")

        # BlueIG Frame (dynamic)
        self.blueig_frame = tk.Frame(self, bg="#333333")
        self.blueig_frame.pack(pady=10)
        self.create_blueig_button()

        # Other buttons
        for txt, cmd in [
            ("Launch VBS4", launch_vbs4),
            ("Launch BVI", launch_bvi),
            ("Settings", lambda: controller.show("Settings")),
            ("Tutorials", lambda: controller.show("Tutorials")),
            ("Credits", lambda: controller.show("Credits")),
            ("Exit", controller.destroy),
        ]:
            if txt == "Launch VBS4":
                self.create_vbs4_button()
                continue

            state = "normal"
            bg    = "#444444"
            if txt == "Launch BVI":
                path = get_ares_manager_path()
                if not path or not os.path.isfile(path):
                    state = "disabled"
                    bg    = "#888888"

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

    def create_vbs4_button(self):
        path = get_vbs4_install_path()
        state = "normal" if path and os.path.isfile(path) else "disabled"
        bg = "#444444" if state == "normal" else "#888888"
        tk.Button(
            self,
            text="Launch VBS4",
            font=("Helvetica", 24),
            bg=bg, fg="white",
            width=30, height=1,
            command=launch_vbs4,
            state=state
        ).pack(pady=10, before=self.blueig_frame)

    def create_blueig_button(self):
        for widget in self.blueig_frame.winfo_children():
            widget.destroy()

        is_srv  = config["General"].getboolean("is_server", fallback=False)
        path_ok = bool(get_blueig_install_path())
        state   = "normal" if (not is_srv and path_ok) else "disabled"
        bg      = "#444444" if state == "normal" else "#888888"

        tk.Button(
            self.blueig_frame,
            text="Launch BlueIG",
            font=("Helvetica", 24),
            bg=bg, fg="white",
            width=30, height=1,
            state=state,
            command=self.show_scenario_buttons
        ).pack()

    def show_scenario_buttons(self):
        if config["General"].getboolean("is_server", fallback=False):
            return

        for widget in self.blueig_frame.winfo_children():
            widget.destroy()

        for i in range(1, 5):
            tk.Button(
                self.blueig_frame,
                text=f"Launch BlueIG HammerKit 1-{i}",
                font=("Helvetica", 20),
                bg="#444444", fg="white",
                width=30, height=1,
                command=lambda n=i: self.launch_blueig_scenario(n)
            ).pack(pady=5)

        tk.Button(
            self.blueig_frame,
            text="Back",
            font=("Helvetica", 18),
            bg="#666666", fg="white",
            width=10,
            command=self.create_blueig_button
        ).pack(pady=10)

    def launch_blueig_scenario(self, scenario_num):
        exe = config["General"].get("blueig_path", "").strip()
        if not exe or not os.path.isfile(exe):
            messagebox.showerror(
                "Error",
                "BlueIG executable not found. Please set it in the settings."
            )
            return

        blueig_dir = os.path.dirname(exe)
        scenario = f"Exercise-HAMMERKIT1-{scenario_num}"
        args = [
            exe,
            "-hmd=openxr_ctr:oculus",
            f"-vbsHostExerciseID={scenario}",
            "-splitCPU",
            "-DJobThreads=8",
            "-DJobPool=8",
        ]

        try:
            subprocess.Popen(args, cwd=blueig_dir)
            if is_close_on_launch_enabled():
                sys.exit(0)
        except Exception as e:
            messagebox.showerror("Launch Failed", f"Couldn't launch BlueIG:\n{e}")

        self.create_blueig_button()

    def update_blueig_state(self):
        self.create_blueig_button()
  
class VBS4Panel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        set_wallpaper(self)
        set_background(controller, self)
        self.controller = controller
        controller.create_tutorial_button(self)
        self.create_battlespaces_button()
        self.create_vbs4_folder_button()
        self.tooltip = Tooltip(self)
        enable_obj_in_photomesh_config()
        set_active_wizard_preset()
       

        tk.Label(
            self,
            text="VBS4 / BlueIG",
            font=("Helvetica", 36, "bold"),
            bg="black", fg="white", pady=20
        ).pack(fill="x")

         # VBS4 Launch frame
        vbs4_frame = tk.Frame(self, bg="#333333")
        vbs4_frame.pack(pady=8)

        vbs4_path = get_vbs4_install_path()
        logging.debug("VBS4 path for button creation: %s", vbs4_path)

        self.vbs4_button, self.vbs4_version_label = create_app_button(
            self, "VBS4", get_vbs4_install_path, launch_vbs4,
            lambda: self.set_file_location("VBS4", "vbs4_path", self.vbs4_button)
        )
        self.update_vbs4_version()
        self.update_vbs4_button_state()

        # VBS4 version label
        self.vbs4_version_label = tk.Label(
            vbs4_frame,
            text="",
            font=("Helvetica", 16),
            bg="#333333", fg="white"
        )
        self.vbs4_version_label.pack(side=tk.LEFT, padx=10)
        self.update_vbs4_version()

        self.vbs4_launcher_button, _ = create_app_button(
            self, "VBS4 Launcher", 
            lambda: config['General'].get('vbs4_setup_path', ''),
            launch_vbs4_setup,
            lambda: self.set_file_location("VBS4 Launcher", "vbs4_setup_path", self.vbs4_launcher_button)
        )
        self.update_vbs4_launcher_button_state()

        # BlueIG frame for dynamic buttons + version label handled below
        self.blueig_frame = tk.Frame(self, bg="#333333")
        self.blueig_frame.pack(pady=8)
        self.create_blueig_button()

        # VBS License Manager button
        self.vbs_license_button, _ = create_app_button(
            self, "VBS License Manager", 
            lambda: config['General'].get('vbs_license_manager_path', ''),
            self.launch_vbs_license_manager,
            lambda: self.set_file_location("VBS License Manager", "vbs_license_manager_path", self.vbs_license_button)
        )

        # Terrain Converter Section
        self.terrain_frame = tk.Frame(self, bg="#333333")
        self.terrain_frame.pack(pady=8)
        self.terrain_button = tk.Button(
            self.terrain_frame,
            text="One-Click Terrain Converter",
            font=("Helvetica", 20),
            bg="#444", fg="white",
            command=self.toggle_terrain_buttons
        )
        self.terrain_button.pack(pady=8, ipadx=10, ipady=5)
        # Tooltip for expanding the terrain tools
        self.terrain_button.bind(
            "<Enter>",
            lambda e: self.show_tooltip(e, "Show or hide terrain tools")
        )
        self.terrain_button.bind("<Leave>", self.hide_tooltip)
        self.create_hidden_terrain_buttons()
        self.update_fuser_state()

        # External Map button
        tk.Button(
            self,
            text="External Map",
            font=("Helvetica", 20),
            bg="#444", fg="white",
            command=open_external_map
        ).pack(pady=8, ipadx=10, ipady=5)

        # Back to main menu
        tk.Button(
            self,
            text="Back",
            font=("Helvetica", 18),
            bg="red", fg="white",
            command=lambda: controller.show("Main")
        ).pack(pady=20)

               # Log Window
            # Log Window
        self.log_frame = tk.Frame(self, bg="#222222")
        # Keep the activity log anchored to the bottom so control buttons
        # remain accessible even in fullscreen mode.
        self.log_frame.pack(side="bottom", fill="x", padx=10, pady=(5, 0))

        tk.Label(
            self.log_frame, text="Activity Log",
            font=("Helvetica", 16, "bold"),
            bg="#222222", fg="white"
        ).pack(anchor="w")

        self.log_text = tk.Text(self.log_frame, height=3, bg="black", fg="lime", wrap="word")
        self.log_text.pack(fill="both", expand=True)
        self.log_expanded = False
        self.log_text.config(state="disabled")

        # Render progress bar
        progress_frame = tk.Frame(self.log_frame, bg="#222222")
        progress_frame.pack(fill="x", pady=(5, 0))

        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            orient="horizontal",
            mode="determinate",
        )
        self.progress_bar.pack(side="left", fill="x", expand=True)

        self.progress_label = tk.Label(
            progress_frame,
            text="0%",
            font=("Helvetica", 12),
            bg="#222222",
            fg="white",
            width=5,
        )
        self.progress_label.pack(side="right", padx=(5, 0))

        self.progress_job = None
        self.project_log_folder = None
        self.work_folder = None
        self.last_build_dir = None

        button_frame = tk.Frame(self.log_frame, bg="#222222")
        button_frame.pack(fill="x", pady=5)

        self.toggle_log_button = tk.Button(
            button_frame, text="Expand Log",
            command=self.toggle_log,
            bg="#555", fg="white"
        )
        self.toggle_log_button.pack(side="left")

        tk.Button(
            button_frame, text="Clear Log",
            command=self.clear_log,
            bg="#555", fg="white"
        ).pack(side="right")

    def create_blueig_button(self):
        # Clear out any existing widgets
        for widget in self.blueig_frame.winfo_children():
            widget.destroy()

        is_srv = config['General'].getboolean('is_server', fallback=False)
        state = 'disabled' if is_srv else 'normal'

        # Launch BlueIG button
        self.blueig_button, self.blueig_version_label = create_app_button(
            self, "BlueIG", get_blueig_install_path, self.show_scenario_buttons,
            lambda: self.set_file_location("BlueIG", "blueig_path", self.blueig_button)
        )
        self.update_blueig_version()

        # BlueIG version label (now here, after the button)
        self.blueig_version_label = tk.Label(
            self.blueig_frame,
            text="",
            font=('Helvetica', 16),
            bg='#333333', fg='white'
        )
        self.blueig_version_label.pack(side=tk.LEFT, padx=10)
        self.update_blueig_version()

    def update_vbs4_version(self):
        path = get_vbs4_install_path()
        ver = get_vbs4_version(path)
        self.vbs4_version_label.config(text=f"Version: {ver}")

    def update_blueig_version(self):
        path = get_blueig_install_path()
        ver = get_blueig_version(path)
        self.blueig_version_label.config(text=f"BlueIG Version: {ver}")

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

    def show_scenario_buttons(self):
        # If “Is Server”, do nothing
        if config["General"].getboolean("is_server", fallback=False):
            return

        # Otherwise clear and show four “HammerKit 1–i” buttons
        for widget in self.blueig_frame.winfo_children():
            widget.destroy()

        for i in range(1, 5):
            tk.Button(
                self.blueig_frame,
                text=f"HammerKit 1-{i}",
                font=("Helvetica", 16),
                bg="#444444", fg="white",
                command=lambda n=i: self.launch_blueig_scenario(n)
            ).pack(side=tk.LEFT, padx=5, pady=5, ipadx=5, ipady=2)

    def launch_blueig_scenario(self, scenario_num):
        exe = config["General"].get("blueig_path", "").strip()
        if not exe or not os.path.isfile(exe):
            messagebox.showerror(
                "Error",
                "BlueIG executable not found. Please set it in the settings."
            )
            return

        blueig_dir = os.path.dirname(exe)
        scenario = f"Exercise-HAMMERKIT1-{scenario_num}"

        args = [
            exe,
            "-hmd=openxr_ctr:oculus",
            f"-vbsHostExerciseID={scenario}",
            "-splitCPU",
            "-DJobThreads=8",
            "-DJobPool=8",
        ]

        try:
            subprocess.Popen(args, cwd=blueig_dir)
            if is_close_on_launch_enabled():
                sys.exit(0)
        except Exception as e:
            messagebox.showerror("Launch Failed", f"Couldn't launch BlueIG:\n{e}")

        # Re‐draw the single “Launch BlueIG” button again
        self.create_blueig_button()

    def update_blueig_state(self):
        """Re‐draw the single BlueIG button if 'is_server' toggles."""
        self.create_blueig_button()

    def show_tooltip(self, event, text=None):
        # If text is not provided, use the default text
        if text is None:
            text = "Open local Battlespaces folder"

        # event.x_root, event.y_root are screen coordinates of the mouse.
        # Add a small offset so the tooltip does not cover the mouse pointer:
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

    def create_hidden_terrain_buttons(self):
        self.hidden_buttons = []

        buttons = [
            (
                "One-Click Conversion",
                self.one_click_conversion,
                "Run the full terrain workflow",
            ),
            (
                "Launch Reality Mesh to VBS4",
                self.post_process_last_build,
                "Run Reality Mesh to VBS4 on the last build",
            ),
            (
                "One-Click Terrain Tutorial",
                self.show_terrain_tutorial,
                "Open help for the terrain tools",
            ),
        ]

        for text, command, tip in buttons:
            button = tk.Button(
                self.terrain_frame,
                text=text,
                font=("Helvetica", 16),
                bg="#444", fg="white",
                command=command
            )
            button.bind("<Enter>", lambda e, t=tip: self.show_tooltip(e, t))
            button.bind("<Leave>", self.hide_tooltip)
            self.hidden_buttons.append(button)

    def toggle_terrain_buttons(self):
        if self.terrain_button.cget("text") == "One-Click Terrain Converter":
            self.terrain_button.config(text="Hide Terrain Options")
            for button in self.hidden_buttons:
                button.pack(pady=5, padx=10, fill="x")
        else:
            self.terrain_button.config(text="One-Click Terrain Converter")
            for button in self.hidden_buttons:
                button.pack_forget()

    def update_vbs4_button_state(self):
        path = get_vbs4_install_path()
        logging.debug("Updating VBS4 button state. Path: %s", path)
        if path and os.path.isfile(path):
            self.vbs4_button.config(state="normal", bg="#444444")
        else:
            self.vbs4_button.config(state="disabled", bg="#888888")

    def update_vbs4_launcher_button_state(self):
        path = get_vbs4_launcher_path()
        if path and os.path.exists(path):
            self.vbs4_launcher_button.config(state="normal", bg="#444444")
        else:
            self.vbs4_launcher_button.config(state="disabled", bg="#888888")

    def update_fuser_state(self):
        is_fuser = config['Fusers'].getboolean('fuser_computer', fallback=False)
        tip = "This pc is being used as a fuser" if is_fuser else "Show or hide terrain tools"
        state = "disabled" if is_fuser else "normal"
        bg = "#888888" if is_fuser else "#444"

        self.terrain_button.config(state=state, bg=bg, text="One-Click Terrain Converter")
        self.terrain_button.bind("<Enter>", lambda e: self.show_tooltip(e, tip))
        self.terrain_button.bind("<Leave>", self.hide_tooltip)

        for btn in self.hidden_buttons:
            btn.pack_forget()
            btn.config(state=state)

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

        # Set background or fallback to color
        if os.path.exists(prompt_box_image_path):
            img = Image.open(prompt_box_image_path).resize(
                (801, 506), Image.Resampling.LANCZOS
            )
            ph = ImageTk.PhotoImage(img)
            bg_label = tk.Label(folder_window, image=ph)
            bg_label.image = ph
            bg_label.place(relwidth=1, relheight=1)
        else:
            folder_window.configure(bg="#222222")

        # Header
        tk.Label(
            folder_window,
            text="Selected Imagery Folders:",
            font=("Helvetica", 14, "bold"),
            bg="#222222",
            fg="white",
        ).pack(pady=(20, 5))

        # Folder listbox
        folder_listbox = tk.Listbox(
            folder_window,
            width=80,
            height=10,
            bg="#1e1e1e",
            fg="white",
            selectbackground="#444",
        )
        folder_listbox.pack(pady=10)

        def add_folder():
            path = simpledialog.askstring(
                "Network Path",
                "Enter network folder path (leave blank to browse):",
                parent=folder_window,
            )
            if path and os.path.exists(path):
                found = get_image_folders_recursively(clean_path(path))
                folders.extend(found)
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
            messagebox.showinfo(
                "Imagery Selected",
                "Selected imagery folders:\n" + "\n".join(norm_folders),
                parent=folder_window,
            )
            self.log_message("Selected imagery folders:")
            for folder in norm_folders:
                self.log_message(f" - {folder}")
            folder_window.destroy()

        def cancel_selection():
            """Close the imagery selection window without saving."""
            folder_window.destroy()

        # --- Button Frame ---
        button_frame = tk.Frame(folder_window, bg="#222222")
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
                if not path and machine_name:
                    path = rf'\\{machine_name}\\SharedMeshDrive\\WorkingFuser'
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

        default_path = shared_path
        if default_path is None:
            default_path = load_fuser_config(config_file)

        fuser_path = default_path or r"\\localhost\SharedMeshDrive\WorkingFuser"

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
        enable_obj_in_photomesh_config()
        set_active_wizard_preset()
        if not hasattr(self, 'image_folder_paths') or not self.image_folder_paths:
            self.select_imagery()
            if not hasattr(self, 'image_folder_paths') or not self.image_folder_paths:
                return

        project_name = prompt_project_name(self)
        if not project_name:
            messagebox.showwarning("Missing Name", "Project name is required.", parent=self)
            return

        project_path = filedialog.askdirectory(title="Select Project Output Folder", parent=self)
        if not project_path:
            messagebox.showwarning("Missing Folder", "Project output folder is required.", parent=self)
            return
        # Normalize to UNC style backslashes for PhotoMesh
        project_path = clean_path(project_path)
        update_fuser_shared_path(project_path)

        self.log_message(f"Creating mesh for project: {project_name}")

        try:
            launch_photomesh_with_preset(project_name, project_path, self.image_folder_paths)
            self.log_message("PhotoMesh Wizard launched successfully.")
            messagebox.showinfo(
                "PhotoMesh Wizard Launched",
                f"Wizard started for project:\n{project_name}",
                parent=self,
            )
            self.start_progress_monitor(project_path)
        except Exception as e:
            error_message = f"Failed to start PhotoMesh Wizard.\nError: {str(e)}"
            self.log_message(error_message)
            messagebox.showerror("Launch Error", error_message, parent=self)

            if messagebox.askyesno("Open Folder", "Would you like to open the project folder?", parent=self):
                os.startfile(project_path)

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
                    start_explorer(found_path)
                else:
                    messagebox.showwarning(
                        "TerraExplorer Not Found",
                        "TerraExplorer is not installed or could not be found.", parent=self
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
            try:
                self.log_message("Waiting for mesh build to complete...")
                json_path = wait_for_output_json(self.last_build_dir)
                self.log_message(f"Mesh build finished: {json_path}")
            except Exception as exc:
                self.log_message(f"Failed while waiting for build: {exc}")
                self.after(0, lambda: messagebox.showerror(
                    "Build Error", str(exc), parent=self))
                return

            try:
                self.log_message("Launching Reality Mesh to VBS4...")
                self._launch_reality_mesh_app(self.last_build_dir)
            except Exception as exc:
                self.log_message(f"Launch failed: {exc}")
                self.after(0, lambda: messagebox.showerror(
                    "Launch Error", str(exc), parent=self))
                return

            self.log_message("Reality Mesh to VBS4 launched.")

        run_in_thread(_pipeline)

    def post_process_last_build(self, build_root: str | None = None) -> None:
        """Launch the external Reality Mesh to VBS4 application."""
        if self.terrain_button.cget("text") == "Hide Terrain Options":
            self.toggle_terrain_buttons()

        sys_settings_path = os.path.join(BASE_DIR, 'photomesh', 'RealityMeshSystemSettings.txt')
        if build_root:
            self.last_build_dir = build_root
        if not self.last_build_dir:
            self.log_message("No build directory available to launch Reality Mesh.")
            return

        try:
            self._launch_reality_mesh_app(self.last_build_dir)
        except Exception as exc:
            self.log_message(f"Launch failed: {exc}")
            messagebox.showerror("Error", str(exc), parent=self)
            return

    def _launch_reality_mesh_app(self, build_root: str | None = None) -> None:
        """Start the Reality Mesh to VBS4 application."""
        sys_settings_path = os.path.join(BASE_DIR, 'photomesh', 'RealityMeshSystemSettings.txt')
        settings = load_system_settings(sys_settings_path)
        link = settings.get('reality_mesh_to_vbs4_path') or find_reality_mesh_to_vbs4_link()
        link = os.path.normpath(link)
        if not link or not os.path.isfile(link):
            raise FileNotFoundError("Reality Mesh to VBS4 application not found")
        args = f'"{build_root}"' if build_root else ""
        self.log_message(f"Launching: {link} {args}".strip())
        try:
            if args:
                os.startfile(link, arguments=args)
            else:
                os.startfile(link)
        except OSError:
            cmd = [link]
            if build_root:
                cmd.append(build_root)
            subprocess.Popen(cmd)

    def show_terrain_tutorial(self):
        messagebox.showinfo("Terrain Tutorial", "One-Click Terrain Tutorial to be implemented.", parent=self)

    def log_message(self, message):
         self.log_text.config(state="normal")
         self.log_text.insert(tk.END, f"> {message}\n")
         self.log_text.see(tk.END)
         self.log_text.config(state="disabled")

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
        self.project_log_folder = os.path.join(project_path, "Build_1", "out", "Log")
        self.work_folder = os.path.join(project_path, "Build_1", "out", "Work")
        self.last_build_dir = os.path.join(project_path, "Build_1", "out")
        # Reset progress indicators
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

class BVIPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        set_wallpaper(self)
        set_background(controller, self)
        controller.create_tutorial_button(self)

        tk.Label(self, text="BVI",
                 font=("Helvetica",36,"bold"),
                 bg='black', fg='white', pady=20) \
          .pack(fill='x')

        bvi_frame = tk.Frame(self, bg="#333333")
        bvi_frame.pack(pady=8)

        self.bvi_button, self.bvi_version_label = create_app_button(
            self, "BVI", get_ares_manager_path, launch_bvi,
            lambda: self.set_file_location("BVI", "bvi_manager_path", self.bvi_button)
        )
        self.update_bvi_version()

        # BVI Version label
        self.bvi_version_label = tk.Label(
            bvi_frame,
            text="",
            font=("Helvetica", 16),
            bg="#333333", fg="white"
        )
        self.bvi_version_label.pack(side=tk.LEFT, padx=10)

        # Update BVI version label
        self.update_bvi_version()

        tk.Button(self, text="Open Terrain",
                  font=("Helvetica",20), bg="#444", fg="white",
                  command=open_bvi_terrain) \
          .pack(pady=8, ipadx=10, ipady=5)

        tk.Button(self, text="Back",
                  font=("Helvetica",18), bg="red", fg="white",
                  command=lambda: controller.show('Main')) \
          .pack(pady=20)

    def update_bvi_version(self):
        bvi_path = get_ares_manager_path()
        version = get_bvi_version(bvi_path)
        self.bvi_version_label.config(text=f"Version: {version}")

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
            elif app_name == "BlueIG":
                self.update_blueig_version()
        else:
            messagebox.showerror("Error", f"Invalid {app_name} path selected.")    

# ─── SETTINGS PANEL ──────────────────────────────────────────────────────────
class SettingsPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        set_wallpaper(self)
        set_background(controller, self)
        controller.create_tutorial_button(self)
        self.controller = controller

        tk.Label(self, text="Settings",
                 font=("Helvetica",36,"bold"),
                 bg='black', fg='white', pady=20) \
          .pack(fill='x')

        self.fullscreen_var = tk.BooleanVar(value=controller.fullscreen)
        tk.Checkbutton(self,
                       text="Fullscreen Mode",
                       variable=self.fullscreen_var,
                       command=self._on_fullscreen_toggle,
                       font=("Helvetica",20),
                       bg="#444444", fg="white",
                       selectcolor="#444444",
                       indicatoron=True,
                       width=30, pady=5) \
          .pack(pady=8)

        # Launch on Startup
        self.startup_var = tk.BooleanVar(value=is_startup_enabled())
        def _on_startup_toggle():
            toggle_startup()
            self.startup_var.set(is_startup_enabled())

        tk.Checkbutton(self,
                       text="Launch on Startup",
                       variable=self.startup_var,
                       command=_on_startup_toggle,
                       font=("Helvetica",20),
                       bg="#444444", fg="white",
                       selectcolor="#444444",
                       indicatoron=True,
                       width=30, pady=5) \
          .pack(pady=8)

        # Close on Launch
        self.close_var = tk.BooleanVar(value=is_close_on_launch_enabled())
        def _on_close_toggle():
            toggle_close_on_launch()
            self.close_var.set(is_close_on_launch_enabled())

        tk.Checkbutton(self,
                       text="Close on Software Launch?",
                       variable=self.close_var,
                       command=_on_close_toggle,
                       font=("Helvetica",20),
                       bg="#444444", fg="white",
                       selectcolor="#444444",
                       indicatoron=True,
                       width=30, pady=5) \
          .pack(pady=8)

        self.fuser_var = tk.BooleanVar(value=config['Fusers'].getboolean('fuser_computer', False))

        def _on_fuser_toggle():
            config['Fusers']['fuser_computer'] = str(self.fuser_var.get())
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
            if self.fuser_var.get():
                host = config['Fusers'].get('working_folder_host', '')
                host = prompt_hostname(self, host)
                if host:
                    config['Fusers']['working_folder_host'] = host.strip()
                    with open(CONFIG_PATH, 'w') as f:
                        config.write(f)
                update_fuser_shared_path()
                run_in_thread(self.controller.panels['VBS4'].launch_local_fuser)
            self.controller.panels['VBS4'].update_fuser_state()

        tk.Checkbutton(self,
                       text="Fuser Computer",
                       variable=self.fuser_var,
                       command=_on_fuser_toggle,
                       font=("Helvetica",20),
                       bg="#444444", fg="white",
                       selectcolor="#444444",
                       indicatoron=True,
                       width=30, pady=5) \
          .pack(pady=8)

        # VBS4 Install Location
        frame_vbs4 = tk.Frame(self, bg=self["bg"])
        frame_vbs4.pack(fill="x", pady=8, padx=20)
        tk.Button(frame_vbs4, text="Set VBS4 Install Location",
                  font=("Helvetica",20), bg="#444444", fg="white",
                  command=self._on_set_vbs4) \
          .pack(side="left", ipadx=10, ipady=5)
        self.lbl_vbs4 = tk.Label(frame_vbs4,
                                 text=get_vbs4_install_path() or "[not set]",
                                 font=("Helvetica",14),
                                 bg="#222222", fg="white",
                                 anchor="w", width=50)
        self.lbl_vbs4.pack(side="left", padx=10, fill="x", expand=True)

        frame_vbs4_setup = tk.Frame(self, bg=self["bg"])
        frame_vbs4_setup.pack(fill="x", pady=8, padx=20)
        tk.Button(frame_vbs4_setup, text="Set VBS4 Setup Launcher Location",
                  font=("Helvetica",20), bg="#444444", fg="white",
                  command=self._on_set_vbs4_setup) \
          .pack(side="left", ipadx=10, ipady=5)
        self.lbl_vbs4_setup = tk.Label(frame_vbs4_setup,
                                       text=config['General'].get('vbs4_setup_path', '') or "[not set]",
                                       font=("Helvetica",14),
                                       bg="#222222", fg="white",
                                       anchor="w", width=50)
        self.lbl_vbs4_setup.pack(side="left", padx=10, fill="x", expand=True)

        # BlueIG Install Location
        frame_blueig = tk.Frame(self, bg=self["bg"])
        frame_blueig.pack(fill="x", pady=8, padx=20)
        tk.Button(frame_blueig, text="Set BlueIG Install Location",
                  font=("Helvetica",20), bg="#444444", fg="white",
                  command=self._on_set_blueig) \
          .pack(side="left", ipadx=10, ipady=5)
        self.lbl_blueig = tk.Label(frame_blueig,
                                   text=get_blueig_install_path() or "[not set]",
                                   font=("Helvetica",14),
                                   bg="#222222", fg="white",
                                   anchor="w", width=50)
        self.lbl_blueig.pack(side="left", padx=10, fill="x", expand=True)

        # ARES Manager Install Location
        frame_ares = tk.Frame(self, bg=self["bg"])
        frame_ares.pack(fill="x", pady=8, padx=20)
        tk.Button(frame_ares, text="Set ARES Manager Location",
                  font=("Helvetica",20), bg="#444444", fg="white",
                  command=self._on_set_ares) \
          .pack(side="left", ipadx=10, ipady=5)
        self.lbl_ares = tk.Label(frame_ares,
                                 text=get_ares_manager_path() or "[not set]",
                                 font=("Helvetica",14),
                                 bg="#222222", fg="white",
                                 anchor="w", width=50)
        self.lbl_ares.pack(side="left", padx=10, fill="x", expand=True)

        # Default Browser
        frame_browser = tk.Frame(self, bg=self["bg"])
        frame_browser.pack(fill="x", pady=8, padx=20)
        tk.Button(frame_browser, text="Pick Default Browser",
                  font=("Helvetica",20), bg="#444444", fg="white",
                  command=self._on_set_browser) \
          .pack(side="left", ipadx=10, ipady=5)
        self.lbl_browser = tk.Label(frame_browser,
                                    text=get_default_browser() or "[not set]",
                                    font=("Helvetica",14),
                                    bg="#222222", fg="white",
                                    anchor="w", width=50)
        self.lbl_browser.pack(side="left", padx=10, fill="x", expand=True)

        # VBS License Manager Location
        frame_vbs_license = tk.Frame(self, bg=self["bg"])
        frame_vbs_license.pack(fill="x", pady=8, padx=20)
        tk.Button(frame_vbs_license, text="Set VBS License Manager Location",
                  font=("Helvetica",20), bg="#444444", fg="white",
                  command=self._on_set_vbs_license_manager) \
          .pack(side="left", ipadx=10, ipady=5)
        self.lbl_vbs_license = tk.Label(frame_vbs_license,
                                        text=config['General'].get('vbs_license_manager_path', '') or "[not set]",
                                        font=("Helvetica",14),
                                        bg="#222222", fg="white",
                                        anchor="w", width=50)
        self.lbl_vbs_license.pack(side="left", padx=10, fill="x", expand=True)

        # One-Click Dataset Location
        frame_ds = tk.Frame(self, bg=self["bg"])
        frame_ds.pack(fill="x", pady=8, padx=20)
        tk.Button(frame_ds, text="Set One-Click Output Folder",
                  font=("Helvetica",20), bg="#444444", fg="white",
                  command=self._on_set_oneclick) \
          .pack(side="left", ipadx=10, ipady=5)
        self.lbl_oneclick = tk.Label(frame_ds,
                                     text=get_oneclick_output_path() or "[not set]",
                                     font=("Helvetica",14),
                                     bg="#222222", fg="white",
                                     anchor="w", width=50)
        self.lbl_oneclick.pack(side="left", padx=10, fill="x", expand=True)

        # Back
        tk.Button(self, text="Back",
                  font=("Helvetica",18), bg="red", fg="white",
                  width=30, height=1,
                  command=lambda: controller.show('Main')) \
          .pack(pady=20)

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
        self.controller.panels['VBS4'].update_vbs4_button_state()

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

    def _on_fullscreen_toggle(self):
     self.controller.toggle_fullscreen()
     self.fullscreen_var.set(self.controller.fullscreen)

class TutorialsPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        set_wallpaper(self)
        set_background(controller, self)
        tk.Label(self, text="Tutorials ❓",
                 font=("Helvetica", 36, "bold"),
                 bg='black', fg='white', pady=20)\
          .pack(fill='x')

        # Create a frame to hold all button sections
        content_frame = tk.Frame(self, bg='black')
        content_frame.pack(expand=True, fill='both', padx=20, pady=20)

        # Configure grid
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=1)
        content_frame.rowconfigure(0, weight=1)
        content_frame.rowconfigure(1, weight=1)

        # VBS4 Help Section
        vbs4_frame = self._create_section(content_frame, "VBS4 Help", 0, 0)
        self._add_buttons(vbs4_frame, vbs4_help_items)

        # BVI Help Section
        bvi_frame = self._create_section(content_frame, "BVI Help", 0, 1)
        self._add_buttons(bvi_frame, bvi_help_items)

        # One-Click Terrain Help Section (Coming Soon)
        oct_frame = self._create_section(content_frame, "One-Click Terrain Help", 1, 0)
        tk.Label(oct_frame, text="Tool coming soon...",
                 font=("Helvetica", 16), bg="#333333", fg="white", pady=20)\
          .pack(expand=True)

        # Blue IG Help Section
        blueig_frame = self._create_section(content_frame, "Blue IG Help", 1, 1)
        self._add_buttons(blueig_frame, blueig_help_items)

        # Back button
        tk.Button(self, text="Back",
                  font=("Helvetica", 18), bg="red", fg="white",
                  command=lambda: controller.show('Main'))\
          .pack(pady=20)

    def _create_section(self, parent, title, row, column):
        frame = tk.Frame(parent, bg='#333333', bd=2, relief=tk.RAISED)
        frame.grid(row=row, column=column, sticky='nsew', padx=10, pady=10)
        
        tk.Label(frame, text=title,
                 font=("Helvetica", 24, "bold"),
                 bg='#333333', fg='white', pady=10)\
          .pack(fill='x')
        
        return frame

    def _add_buttons(self, parent, items):
        button_frame = tk.Frame(parent, bg='#333333')
        button_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        rows = 3
        cols = 2
        for i, (txt, cmd) in enumerate(items.items()):
            row = i // cols
            col = i % cols
            tk.Button(button_frame, text=txt,
                      font=("Helvetica", 12), bg="#444444", fg="white",
                      command=cmd, wraplength=150)\
              .grid(row=row, column=col, padx=5, pady=5, sticky='nsew')
        
        # Configure grid
        for i in range(cols):
            button_frame.columnconfigure(i, weight=1)
        for i in range(rows):
            button_frame.rowconfigure(i, weight=1)

    def open_blueig_docs(self):
        blueig_path = config['General'].get('blueig_path', '')
        if blueig_path:
            docs_path = os.path.join(os.path.dirname(blueig_path), "docs", "Blue_IG_EN.htm")
            if os.path.exists(docs_path):
                webbrowser.open(f"file://{docs_path}", new=2)
            else:
                messagebox.showerror("Error", "Blue IG documentation not found.")
        else:
            messagebox.showerror("Error", "Blue IG path not set. Please set it in the settings.")
            
class CreditsPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        set_wallpaper(self)
        set_background(controller, self)
        controller.create_tutorial_button(self)

        # Add header
        tk.Label(self, text="CREDITS",
                 font=("Helvetica", 36, "bold"),
                 bg='black', fg='white', pady=20)\
          .pack(fill='x')

        # Create a frame to center the content with gray background
        center_frame = tk.Frame(self, bg='#333333', padx=20, pady=20)
        center_frame.place(relx=0.5, rely=0.53, anchor='center')

        # Add STE logo
        if os.path.exists(logo_STE_path):
            img = Image.open(logo_STE_path).resize((90, 90), Image.Resampling.LANCZOS)
            ph = ImageTk.PhotoImage(img)
            logo_label = tk.Label(center_frame, image=ph, bg="#333333")
            logo_label.image = ph
            logo_label.pack(pady=(0, 20))

        # Credits text
        credits_text = """
        STE Mission Planning Toolkit

        Designed and developed by:

        Ryan Curphey - Developer

        Yovany Tietze-torres - Designer

   
        Version: 1.0

        Special thanks to:
        - The STE CFT team
        - All contributors and testers
        """

        tk.Label(center_frame, text=credits_text,
                 font=("Helvetica", 14),
                 bg='#333333', fg='white', justify='center')\
          .pack(pady=20)

        # Back button
        tk.Button(self, text="Back",
                  font=("Helvetica", 18), bg="red", fg="white",
                  command=lambda: controller.show('Main'))\
          .pack(side='bottom', pady=20)

class ContactSupportPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        set_wallpaper(self)
        set_background(controller, self)
        controller.create_tutorial_button(self)

        # Add header
        tk.Label(self, text="Contact Support",
                 font=("Helvetica", 36, "bold"),
                 bg='black', fg='white', pady=20)\
          .pack(fill='x')

        # Create a frame to center the content with gray background
        center_frame = tk.Frame(self, bg='#333333', padx=20, pady=20)
        center_frame.place(relx=0.5, rely=0.53, anchor='center')

        # Support information
        support_text = """
        For technical support or assistance, please contact:


        Michael Enloe
        Cheif Technology Officer
        Email: michael.r.enloe.civ@army.mil
        
        
        Yovany Tietze-torres
        Senior Syetems Architect
        Email: yovany.e.tietze-torres.ctr@army.mil
       

        US Army Futures Command, Synthetic Training Environment (STE)   Cross Functional Team (CFT)

        12809 Science Dr, Orlando, FL 32836

        Hours of Operation:
        Monday - Friday: 9:00 AM - 5:00 PM EST
        """

        tk.Label(center_frame, text=support_text,
                 font=("Helvetica", 14),
                 bg='#333333', fg='white', justify='left')\
          .pack(pady=20)

        # Contact Support button (at the bottom)
        tk.Button(self, text="Contact Support via Email",
                  font=("Helvetica", 18), bg="green", fg="white",
                  command=self.contact_support)\
          .pack(side='bottom', pady=20)

        # Back button
        tk.Button(self, text="Back",
                  font=("Helvetica", 18), bg="red", fg="white",
                  command=lambda: controller.show('Main'))\
          .pack(side='bottom', pady=20)

    def contact_support(self):
        # This function will open the default email client with the new email address
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

        # Create a new Toplevel, no decorations:
        self.tw = tk.Toplevel(self.parent)
        self.tw.wm_overrideredirect(True)  # no title bar, borders, etc.
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

        # Position the tooltip window at (x, y) in screen coordinates:
        self.tw.geometry(f"+{x}+{y}")

    def hide(self):
        if self.tw:
            self.tw.destroy()
            self.tw = None

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
                subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW)
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
    app = MainApp()
    if config['Fusers'].getboolean('fuser_computer', False):
        update_fuser_shared_path()
        run_in_thread(app.panels['VBS4'].launch_local_fuser)
        app.panels['VBS4'].update_fuser_state()
    app.mainloop()
