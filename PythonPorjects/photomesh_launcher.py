from __future__ import annotations
import os, sys, json, shutil, subprocess, tempfile, configparser, ctypes, time, uuid, errno
import xml.etree.ElementTree as ET
from typing import Iterable, Optional

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

# === 1) Paste the exact JSON we were given ===
NEW_WIZARD_CFG = {
  "PhotomeshRestUrl": "http://localhost:8086",
  "NameEllipsoid": "WGS 84",
  "DatumEllipsoid": "GEOGCS[\"WGS 84\",DATUM[\"WGS_1984\",SPHEROID[\"WGS 84\",6378137,298.257223563,AUTHORITY[\"EPSG\",\"7030\"]],AUTHORITY[\"EPSG\",\"6326\"]],PRIMEM[\"Greenwich\",0,AUTHORITY[\"EPSG\",\"8901\"]],UNIT[\"degree\",0.0174532925199433,AUTHORITY[\"EPSG\",\"9122\"]],AUTHORITY[\"EPSG\",\"4326\"]]",
  "NameGeoid": "WGS 84 + EGM96 geoid height",
  "DatumGeoid": "COMPD_CS[\"WGS 84 + EGM96 geoid height\", GEOGCS[\"WGS 84\", DATUM[\"WGS_1984\", SPHEROID[\"WGS 84\", 6378137, 298.257223563, AUTHORITY[\"EPSG\", \"7030\"]], AUTHORITY[\"EPSG\", \"6326\"]], PRIMEM[\"Greenwich\", 0, AUTHORITY[\"EPSG\", \"8901\"]], UNIT[\"degree\", 0.0174532925199433, AUTHORITY[\"EPSG\", \"9122\"]], AUTHORITY[\"EPSG\", \"4326\"]], VERT_CS[\"EGM96 geoid height\", VERT_DATUM[\"EGM96 geoid\", 2005, AUTHORITY[\"EPSG\", \"5171\"], EXTENSION[\"PROJ4_GRIDS\", \"egm96_15.gtx\"]], UNIT[\"m\", 1.0], AXIS[\"Up\", UP], AUTHORITY[\"EPSG\", \"5773\"]]]",
  "SecondsPerFrame": 1.0,
  "StandardWaitTime": 1500,
  "UseMinimize": True,
  "UseLowPriorityPM": False,
  "UseRawRequests": False,
  "EnableTextureMeshMaxThreads": True,
  "OutputsWaitTimerSeconds": 0,
  "ClosePMWhenDone": True,
  "DefaultPhotoMeshWizardUI": {
    "VerticalDatum": "Ellipsoid",
    "GPSAccuracy": "Standard",
    "CollectionType": "3DMapping",
    "OptimizeShadow": True,
    "OutputProducts": {
      "Model3D": True,
      "Ortho": False,
      "DSM": False,
      "DTM": False,
      "LAS": False
    },
    "Model3DFormats": {
      "3DML": True,
      "OBJ": True,
      "SLPK": True
    },
    "ProcessingLevel": "Standard",
    "StopOnError": False,
    "MaxProcessing": False
  },
  "GBPerFuser": 24,
  "UseDepthAnything": False,
  "PMWServiceTimeoutInMinutes": 1440,
  "NetworkWorkingFolder": ""
}

def _wizard_config_targets():
    r"""
    All typical Wizard config.json locations:
      - Legacy:   C:\Program Files\Skyline\PhotoMeshWizard\config.json
      - Tools:    C:\Program Files\Skyline\PhotoMesh\Tools\PhotomeshWizard\config.json
      - Per-user: %LOCALAPPDATA%\Skyline\PhotoMesh\PhotomeshWizard\config.json
    """
    targets = []
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            targets.append(os.path.join(base, "Skyline", "PhotoMeshWizard", "config.json"))
            targets.append(os.path.join(base, "Skyline", "PhotoMesh", "Tools", "PhotomeshWizard", "config.json"))
    la = os.environ.get("LOCALAPPDATA")
    if la:
        targets.append(os.path.join(la, "Skyline", "PhotoMesh", "PhotomeshWizard", "config.json"))
    # keep those whose parent dir exists (we will create per-user dir if missing)
    out = []
    for p in targets:
        parent = os.path.dirname(p)
        if parent.lower().startswith((os.environ.get("ProgramFiles","" ).lower(),
                                      (os.environ.get("ProgramFiles(x86)","") or "x").lower())):
            if os.path.isdir(parent):
                out.append(p)
        else:
            os.makedirs(parent, exist_ok=True)
            out.append(p)
    return out

def _backup(path: str):
    if os.path.isfile(path):
        ts = time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, f"{path}.bak.{ts}")

def _atomic_write_json(path: str, data: dict):
    tmp = f"{path}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)

def install_wizard_config(log=print):
    wrote = False
    for dst in _wizard_config_targets():
        try:
            _backup(dst)
            _atomic_write_json(dst, NEW_WIZARD_CFG)
            log(f"[Wizard] Installed config → {dst}")
            wrote = True
        except PermissionError as e:
            log(f"[Wizard] Permission denied writing {dst}. Run this script as Administrator. ({e})")
        except Exception as e:
            log(f"[Wizard] Skipped {dst}: {e}")
    if not wrote:
        raise RuntimeError("No config.json was written. Run elevated and ensure Wizard is closed.")

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

# Repo-level wizard template (same shape as Wizard config.json)
REPO_WIZARD_TEMPLATE = os.environ.get(
    "PM_WIZARD_TEMPLATE_JSON",
    os.path.join(BASE_DIR, "config.json")
)

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

# -------------------- Apply repo template --------------------
def _patch_intersection(dst: dict, src: dict) -> bool:
    """
    Recursively copy values from src -> dst for keys that already exist in dst.
    - Never creates new keys in dst.
    - For dict leaves, recurses.
    - For non-dict leaves, assigns when the key exists and values differ.
    Returns True if any change was applied.
    """
    changed = False
    if not isinstance(dst, dict) or not isinstance(src, dict):
        return False
    for k, v in src.items():
        if k not in dst:
            continue
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            if _patch_intersection(dst[k], v):
                changed = True
        else:
            if dst.get(k) != v:
                dst[k] = v
                changed = True
    return changed


def apply_wizard_template_from_repo(
    template_path: str = REPO_WIZARD_TEMPLATE,
    dynamic_overrides: Optional[dict] = None,
    log=print
) -> None:
    """
    Load repo template JSON and apply values to the installed Wizard config,
    but ONLY where keys already exist in the install file. Optionally apply
    dynamic_overrides the same way (e.g., computed NetworkWorkingFolder).
    """
    # Load installed Wizard config
    target = _load_json(WIZARD_INSTALL_CFG)
    if not target:
        log(f"⚠️ Unable to load Wizard install config: {WIZARD_INSTALL_CFG}")
        return

    # Load repo template (if present)
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            tmpl = json.load(f)
    except Exception as e:
        tmpl = {}
        log(f"⚠️ Skipping repo template ({template_path}): {e}")

    changed = False
    # Apply template intersection
    if tmpl:
        if _patch_intersection(target, tmpl):
            changed = True

    # Apply dynamic overrides (e.g., Offline UNC) the same way
    if isinstance(dynamic_overrides, dict) and dynamic_overrides:
        if _patch_intersection(target, dynamic_overrides):
            changed = True

    if changed:
        _save_json(WIZARD_INSTALL_CFG, target)
        log(f"Wizard config updated from template: {WIZARD_INSTALL_CFG}")


# -------------------- Write Wizard config (minimal, no new keys) --------------------
def enforce_wizard_install_config(
    *, model3d: bool = True, obj: bool = True, d3dml: bool = False, ortho_ui: bool = False,
    center_pivot: bool = True, ellipsoid: bool = True, fuser_unc: Optional[str] = None, log=print
) -> None:
    """
    Compose minimal overrides that MUST be true/false for your workflow,
    then apply the repo template + these overrides to the installed config.
    """
    overrides = {
        "DefaultPhotoMeshWizardUI": {
            "OutputProducts": {
                "Model3D": bool(model3d),
                "Ortho":   bool(ortho_ui),
            },
            "Model3DFormats": {
                "OBJ":  bool(obj),
                "3DML": bool(d3dml),
            },
            # Only applied if these keys already exist in install config
            "CenterPivotToProject":   bool(center_pivot),
            "ReprojectToEllipsoid":   bool(ellipsoid),
        }
    }
    # Add NetworkWorkingFolder override if provided
    if fuser_unc:
        overrides["NetworkWorkingFolder"] = fuser_unc

    apply_wizard_template_from_repo(
        template_path=REPO_WIZARD_TEMPLATE,
        dynamic_overrides=overrides,
        log=log
    )

# -------------------- User config helpers --------------------
def ensure_wizard_user_defaults(autostart: bool = True) -> None:
    cfg = {
        "AutoBuild": bool(autostart),
    }
    _save_json(WIZARD_USER_CFG, cfg)

def enforce_photomesh_settings(autostart: bool = True) -> None:
    o = get_offline_cfg()
    fuser_unc = resolve_network_working_folder_from_cfg(o)
    enforce_wizard_install_config(fuser_unc=fuser_unc)
    ensure_wizard_user_defaults(autostart=autostart)


def _ensure_valid_outputs(config_path: str, log=print) -> None:
    import json, os
    if not os.path.isfile(config_path):
        return
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        ui = cfg.setdefault("DefaultPhotoMeshWizardUI", {})
        outs = ui.setdefault("OutputProducts", {})
        m3d = ui.setdefault("Model3DFormats", {})
        if not outs.get("Ortho", False):
            if not outs.get("3DModel", False) or not m3d.get("3DML", False):
                outs["3DModel"] = True
                m3d["3DML"] = True
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2)
                log(f"🛠️ Patched outputs: {config_path}")
    except Exception as e:
        log(f"⚠️ Could not validate outputs in {config_path}: {e}")


def _wizard_install_config_paths() -> list[str]:
    """Return possible install-level Wizard config.json paths."""
    return [
        WIZARD_INSTALL_CFG,
        r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard\\config.json",
    ]

# -------------------- Launch Wizard --------------------
def launch_wizard(
    project_name: str,
    project_path: str,
    imagery_folders: Iterable[str],
    *,
    autostart: bool = True,
    fuser_unc: Optional[str] = None,
    want_ortho: bool = False,
    log=print,
) -> subprocess.Popen:
    """Start PhotoMesh Wizard using default configuration."""

    try:
        enforce_wizard_install_config(
            model3d=True,
            obj=True,
            d3dml=True if not want_ortho else True,
            ortho_ui=bool(want_ortho),
            center_pivot=True,
            ellipsoid=True,
            fuser_unc=fuser_unc,
            log=log,
        )
    except PermissionError:
        log("⚠️ Could not update install config (permission). Continuing.")

    args = [WIZARD_EXE, "--projectName", project_name, "--projectPath", project_path]
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

