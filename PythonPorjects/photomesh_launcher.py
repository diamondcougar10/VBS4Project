from __future__ import annotations
import os, sys, json, shutil, subprocess, tempfile, configparser, ctypes, filecmp
from typing import Iterable, Optional

try:  # pragma: no cover - tkinter may not be available
    from tkinter import messagebox
except Exception:  # pragma: no cover - headless/test environments
    messagebox = None

# === PRESET (hard-coded) ===
PRESET_NAME = "STEPRESET"
# Prefer shipping a known path rather than %APPDATA%
PRESET_SRC = r"C:\BiSim OneClick\Presets\STEPRESET.PMPreset"

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


# -------------------- Preset staging --------------------
def stage_preset(src_path: str, preset_name: str) -> Optional[str]:
    """Copy *src_path* into the first writable PhotoMesh Presets folder."""
    if not os.path.isfile(src_path):
        return None

    dst_roots = [
        os.path.join(os.environ.get("APPDATA", ""), "Skyline", "PhotoMesh", "Presets"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Skyline", "PhotoMesh", "Presets"),
        os.path.join(os.environ.get("PROGRAMDATA", ""), "Skyline", "PhotoMesh", "Presets"),
        os.path.join(os.path.expanduser("~/Documents"), "PhotoMesh", "Presets"),
    ]
    for root in dst_roots:
        if not root:
            continue
        try:
            os.makedirs(root, exist_ok=True)
            dst = os.path.join(root, f"{preset_name}.PMPreset")
            if not os.path.isfile(dst) or not filecmp.cmp(src_path, dst, shallow=False):
                shutil.copy2(src_path, dst)
            return dst
        except Exception:
            continue
    return None


# Elevate GUI if needed and stage preset on import
if is_windows() and not is_admin():
    print("[INFO] Elevation required. Relaunching as Administrator…")
    relaunch_self_as_admin()
    sys.exit(0)

staged = stage_preset(PRESET_SRC, PRESET_NAME)
print(f"[INFO] Preset staged to: {staged or 'N/A'}")

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

# Folders where PhotoMesh/Wizard auto-discovers presets by name
PRESET_DIRS = [
    os.path.join(os.environ.get("APPDATA", ""), r"Skyline\PhotoMesh\Presets"),
    r"C:\\Program Files\\Skyline\\PhotoMesh\Presets",
]

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


def _is_known_preset_dir(path: str) -> bool:
    try:
        if not path:
            return False
        p = os.path.normcase(os.path.normpath(path))
        for d in PRESET_DIRS:
            if os.path.normcase(os.path.normpath(d)) == p:
                return True
        return False
    except Exception:
        return False


def _preset_arg_from_user_value(preset) -> str:
    """
    Normalize a user-supplied preset into what PhotoMesh expects on CLI:
      - 'STEPRESET'                   -> 'STEPRESET'
      - 'STEPRESET.PMPreset'          -> 'STEPRESET'
      - r'C:\\...\\STEPRESET.PMPreset'  -> 'STEPRESET' if parent is a known Presets dir,
                                     else r'C:\\...\\STEPRESET' (no extension)
      - ['Base','OBJ_Only']       -> 'Base,OBJ_Only'
      - mix-and-match lists of names/paths are supported
    """
    if isinstance(preset, (list, tuple)):
        return ",".join(_preset_arg_from_user_value(p).strip() for p in preset if str(p).strip())

    val = str(preset or "").strip().strip('"').strip("'")
    if not val:
        return ""

    # If a path was supplied, strip quotes and normalize
    name_wo_ext, ext = os.path.splitext(val)
    if ext.lower() == ".pmpreset":
        val = name_wo_ext  # drop the extension

    # If it still looks like a path, decide whether to pass name or full path
    if os.path.isabs(val) or any(sep in val for sep in ("/", "\\")):
        parent = os.path.dirname(val)
        base_no_ext = os.path.splitext(os.path.basename(val))[0]
        # If the preset lives in a known Presets dir, pass just the name
        if _is_known_preset_dir(parent):
            return base_no_ext
        # Otherwise pass the full path (without extension)
        return os.path.join(parent, base_no_ext)

    # Plain name already
    return val

# -------------------- Offline / network configuration --------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")
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

# -------------------- Preset staging (Program Files + Wizard) --------------------
def _resolve_preset_src(repo_preset_path: str, preset_name: str) -> str:
    """Accept folder or file; prefer <preset_name>.PMPreset"""
    p = os.path.normpath(os.path.expandvars(repo_preset_path.strip('"')))
    candidates: list[str] = []
    if os.path.isdir(p):
        candidates.append(os.path.join(p, f"{preset_name}.PMPreset"))
        try:
            for f in os.listdir(p):
                if f.lower().endswith(".pmpreset"):
                    candidates.append(os.path.join(p, f))
        except Exception:
            pass
    else:
        candidates.append(p)
    candidates += [
        os.path.join(os.getcwd(), "Presets", f"{preset_name}.PMPreset"),
        os.path.join(os.environ.get("APPDATA", ""), "Skyline", "PhotoMesh", "Presets", f"{preset_name}.PMPreset"),
        r"C:\\Program Files\\Skyline\\PhotoMesh\\Presets\%s.PMPreset" % preset_name,
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    raise FileNotFoundError(f"Could not locate {preset_name}.PMPreset")


def stage_install_preset(repo_preset_path: str, preset_name: str, log=print) -> None:
    """
    Copy a .PMPreset to both Program Files preset folders and AppData fallback.
    """
    src = _resolve_preset_src(repo_preset_path, preset_name)
    if not src.lower().endswith(".pmpreset"):
        raise ValueError("Preset must be a .PMPreset")
    targets = [
        os.path.join(r"C:\\Program Files\\Skyline\\PhotoMesh\\Presets", f"{preset_name}.PMPreset"),
        os.path.join(WIZARD_DIR, "Presets", f"{preset_name}.PMPreset") if WIZARD_DIR else "",
        os.path.join(os.environ.get("APPDATA", ""), "Skyline", "PhotoMesh", "Presets", f"{preset_name}.PMPreset"),
    ]
    for dst in targets:
        if not dst:
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        log(f"Staged preset -> {dst}")

# -------------------- User config helpers --------------------
def ensure_wizard_user_defaults(preset: str = "", autostart: bool = True) -> None:
    cfg = {
        "SelectedPreset": preset,
        "OverrideSettings": True,
        "AutoBuild": bool(autostart),
    }
    _save_json(WIZARD_USER_CFG, cfg)

def enforce_photomesh_settings(preset: str = "", autostart: bool = True) -> None:
    o = get_offline_cfg()
    fuser_unc = resolve_network_working_folder_from_cfg(o)
    enforce_wizard_install_config(fuser_unc=fuser_unc)
    ensure_wizard_user_defaults(preset=preset, autostart=autostart)

# -------------------- Launch Wizard with preset --------------------
def launch_wizard_with_preset(
    project_name: str,
    project_path: str,
    imagery_folders: Iterable[str],
    *,
    preset: Optional[str] = PRESET_NAME,
    autostart: bool = True,
    fuser_unc: Optional[str] = None,
    log=print,
) -> subprocess.Popen:
    """
    Start PhotoMesh Wizard with --overrideSettings, hard-coded preset and optional autostart.
    Before launch, ensure UI seeds won’t block startup (Ortho ON in UI; 3DML OFF; OBJ ON).
    """
    try:
        enforce_wizard_install_config(
            model3d=True, obj=True, d3dml=False, ortho_ui=True,
            center_pivot=True, ellipsoid=True, fuser_unc=fuser_unc, log=log
        )
    except PermissionError:
        log("⚠️ Could not update install config (permission). Continuing.")

    args = [
        WIZARD_EXE,
        "--projectName", project_name,
        "--projectPath", project_path,
        "--overrideSettings",
        "--preset", _preset_arg_from_user_value(preset or PRESET_NAME),
    ]
    if autostart:
        args.append("--autostart")
    for f in imagery_folders or []:
        args += ["--folder", f]

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(args, cwd=WIZARD_DIR, creationflags=creationflags)


def launch_wizard_autostart_admin(
    project_name: str, project_path: str, folders: list[str]
) -> None:
    """Launch PhotoMesh Wizard as admin with autostart and hard-coded preset."""
    wizard_exe = r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard\\PhotoMeshWizard.exe"
    args = [
        "--projectName", project_name,
        "--projectPath", project_path,
        "--autostart",
        "--preset", PRESET_NAME,
    ]
    for folder in folders:
        args += ["--folder", folder]
    run_exe_as_admin(wizard_exe, args)


def launch_photomesh_admin() -> None:
    """Launch PhotoMesh.exe elevated without arguments."""
    pm_exe = r"C:\\Program Files\\Skyline\\PhotoMesh\\PhotoMesh.exe"
    run_exe_as_admin(pm_exe, [])
