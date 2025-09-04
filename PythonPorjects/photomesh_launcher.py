from __future__ import annotations
import os, sys, json, subprocess, tempfile, time, glob
import configparser, ctypes
from typing import Iterable
from xml.etree import ElementTree as ET

try:  # pragma: no cover - optional dependency
    import requests  # type: ignore
except Exception:  # pragma: no cover - requests may be absent in minimal environments
    requests = None  # type: ignore

try:  # pragma: no cover - tkinter may not be available
    from tkinter import messagebox
except Exception:  # pragma: no cover - headless/test environments
    messagebox = None

# ---- Authoritative Wizard locations ----
WIZARD_DIR         = r"C:\\Program Files\\Skyline\\PhotoMeshWizard"
WIZARD_EXE         = rf"{WIZARD_DIR}\\PhotoMeshWizard.exe"
WIZARD_INSTALL_CFG = rf"{WIZARD_DIR}\\config.json"

# Keys that would re-apply a preset/overrides (must be removed)
_PRESET_KEYS = ("SelectedPreset","SelectedPresets","PresetStack","LastUsedPreset","PresetOverrides","Preset")

def _load_json_silent(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _atomic_write_json(path: str, data: dict) -> None:
    """Atomic write (no .bak files)."""
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".pmcfg.", dir=d, text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)

def set_wizard_defaults_exact(log=print) -> None:
    """
    Edit ONLY the installed Wizard config that the Wizard reads on launch.
    No AppData writes, no presets, no backups, do not touch NetworkWorkingFolder.
    """
    cfg = _load_json_silent(WIZARD_INSTALL_CFG)
    for k in _PRESET_KEYS:
        cfg.pop(k, None)

    ui   = cfg.setdefault("DefaultPhotoMeshWizardUI", {})
    outs = ui.setdefault("OutputProducts", {})
    fmts = ui.setdefault("Model3DFormats", {})

    # === Required defaults for every build ===
    # Outputs
    outs["Model3D"] = True
    outs["Ortho"]   = False
    outs["DSM"]     = False
    outs["DTM"]     = False
    outs["LAS"]     = True
    # Formats (OBJ alongside base 3DML per vendor guidance)
    fmts["OBJ"]  = True
    fmts["3DML"] = True
    # Centering / reprojection
    ui["CenterPivotToProject"]  = True
    ui["CenterModelsToProject"] = True
    ui["ReprojectToEllipsoid"]  = True

    _atomic_write_json(WIZARD_INSTALL_CFG, cfg)

    # Log the effective values we just wrote (helps acceptance/debug)
    log(f"[WizardCfg] {WIZARD_INSTALL_CFG}")
    log(f"  OutputProducts: Model3D={outs.get('Model3D')}, Ortho={outs.get('Ortho')}, "
        f"DSM={outs.get('DSM')}, DTM={outs.get('DTM')}, LAS={outs.get('LAS')}")
    log(f"  Model3DFormats: OBJ={fmts.get('OBJ')}, 3DML={fmts.get('3DML')}")
    log(f"  CenterPivotToProject={ui.get('CenterPivotToProject')}, "
        f"CenterModelsToProject={ui.get('CenterModelsToProject')}, "
        f"ReprojectToEllipsoid={ui.get('ReprojectToEllipsoid')}")


def _find_project_preset(project_name: str, project_path: str, since_ts: float) -> str:
    """Return path to the newest .PMPreset created since *since_ts*.

    Searches both the user's AppData presets directory and the project
    folder itself.  Prefers files whose name contains *project_name*.
    """
    candidates: list[str] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        preset_dir = os.path.join(appdata, "Skyline", "PhotoMesh", "Presets")
        candidates.extend(glob.glob(os.path.join(preset_dir, "*.PMPreset")))
    candidates.extend(glob.glob(os.path.join(project_path, "*.PMPreset")))
    candidates = [p for p in candidates if os.path.getmtime(p) >= since_ts]
    if not candidates:
        return ""
    named = [p for p in candidates if project_name.lower() in os.path.basename(p).lower()]
    if named:
        return max(named, key=os.path.getmtime)
    return max(candidates, key=os.path.getmtime)


def _ensure_xml_path(root: ET.Element, path: str) -> ET.Element:
    """Ensure *path* exists under *root* and return the final element."""
    cur = root
    for part in path.split("/"):
        nxt = cur.find(part)
        if nxt is None:
            nxt = ET.SubElement(cur, part)
        cur = nxt
    return cur


def _patch_pmpreset_xml(path: str, log=print) -> None:
    """Set required build flags to ``true`` in the project preset."""
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except Exception as e:  # pragma: no cover - parsing errors rare
        log(f"[Preset] Failed to parse {path}: {e}")
        return

    flags = [
        "BuildParameters/OutputProducts/Model3D",
        "BuildParameters/Model3DFormats/OBJ",
        "BuildParameters/Model3DFormats/3DML",
        "BuildParameters/CenterPivotToProject",
        "BuildParameters/CenterModelsToProject",
        "BuildParameters/ReprojectToEllipsoid",
    ]
    for xpath in flags:
        elem = _ensure_xml_path(root, xpath)
        elem.text = "true"

    tree.write(path, encoding="utf-8")
    log(f"[Preset] Patched {path}")

def launch_wizard_new_project(project_name: str, project_path: str, folders, log=print) -> subprocess.Popen:
    """
    Write install defaults, launch Wizard to create the project (no autostart),
    patch the emitted project preset, then start the build.

    Returns the ``Popen`` handle of the autostarted Wizard process.
    """
    set_wizard_defaults_exact(log=log)
    time.sleep(0.2)

    # Initial launch without autostart so the project preset is generated
    prep_args = [
        WIZARD_EXE,
        "--projectName",
        project_name,
        "--projectPath",
        project_path,
        "--overrideSettings",
    ]
    for f in folders or []:
        prep_args += ["--folder", f]
    log(f"[Wizard-prepare] {' '.join(prep_args)}")
    t0 = time.time()
    proc = subprocess.Popen(prep_args, close_fds=False)

    # Wait for the project preset to appear
    preset_path = ""
    deadline = time.time() + 60
    while time.time() < deadline:
        preset_path = _find_project_preset(project_name, project_path, t0)
        if preset_path:
            break
        time.sleep(0.5)
    if preset_path:
        _patch_pmpreset_xml(preset_path, log=log)
    else:
        log("[Wizard] No project preset found; build may use defaults.")

    # Close the preparation instance
    try:
        proc.terminate()
    except Exception:
        pass

    # Relaunch with autostart to begin build
    start_args = [
        WIZARD_EXE,
        "--projectName",
        project_name,
        "--projectPath",
        project_path,
        "--autostart",
        "--overrideSettings",
    ]
    log(f"[Wizard-start] {' '.join(start_args)}")
    return subprocess.Popen(start_args, close_fds=False)

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


def enforce_photomesh_settings(autostart: bool = True, log=print) -> None:
    del autostart  # compatibility placeholder
    set_wizard_defaults_exact(log=log)


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

