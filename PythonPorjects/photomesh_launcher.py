from __future__ import annotations
import os, sys, json, shutil, subprocess, tempfile, configparser, ctypes, filecmp, time, uuid, errno
import xml.etree.ElementTree as ET
from typing import Iterable, Optional

try:  # pragma: no cover - tkinter may not be available
    from tkinter import messagebox
except Exception:  # pragma: no cover - headless/test environments
    messagebox = None

# Preset configuration
PRESET_NAME = "STEPRESET"
PRESET_PATH = os.path.join(
    os.environ.get("APPDATA", ""), "Skyline", "PhotoMesh", "Presets", f"{PRESET_NAME}.PMPreset"
)

# Known Wizard preset directories (both legacy and tools paths)
WIZARD_PRESET_DIRS = [
    r"C:\\Program Files\\Skyline\\PhotoMeshWizard\\Presets",                # legacy path
    r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard\\Presets"  # tools path
]

# Load shared configuration for network fuser settings
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")

# Embedded preset XML
PRESET_XML = """<?xml version="1.0" encoding="utf-8"?>
<BuildParametersPreset xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
  <SerializableVersion>8.0.4.50513</SerializableVersion>
  <Version xmlns:d2p1="http://schemas.datacontract.org/2004/07/System">
    <d2p1:_Build>4</d2p1:_Build>
    <d2p1:_Major>8</d2p1:_Major>
    <d2p1:_Minor>0</d2p1:_Minor>
    <d2p1:_Revision>50513</d2p1:_Revision>
  </Version>
  <BuildParameters>
    <SerializableVersion>8.0.4.50513</SerializableVersion>
    <Version xmlns:d3p1="http://schemas.datacontract.org/2004/07/System">
      <d3p1:_Build>4</d3p1:_Build>
      <d3p1:_Major>8</d3p1:_Major>
      <d3p1:_Minor>0</d3p1:_Minor>
      <d3p1:_Revision>50513</d3p1:_Revision>
    </Version>
    <AddWalls>false</AddWalls>
    <BuildATFlags>-m_tf 100 @Match2[DoSort=1] @Match2[max_matches_for_image=100] @Match2[num_cameras_per_group=10] @Match2[min_connected_to_camera=30] @Match2[num_features_per_collection=300] @Match2[total_num_features=900] @featuredetect2[GdalUseHistogram=1] @featuredetect2[GdalHistAllBands=0] @featuredetect2[GdalHistMin=0.0001] @featuredetect2[GdalHistMax=0.9999] @featuredetect2[ClaheClipLimit=2] @featuredetect2[ClaheGridPixelsX=256] @featuredetect2[ClaheGridPixelsY=256] @texturemesh[MaxThreads=4]</BuildATFlags>
    <BuildFlags></BuildFlags>
    <CenterModelsToProject>true</CenterModelsToProject>
    <CesiumReprojectZ>true</CesiumReprojectZ>
    <ColorTone>1.05</ColorTone>
    <DsmSettings>
      <SizeH>20000</SizeH>
      <SizeW>20000</SizeW>
    </DsmSettings>
    <FillInGround>true</FillInGround>
    <FocalLengthAccuracy>-1</FocalLengthAccuracy>
    <HorizontalAccuracyFactor>0.1</HorizontalAccuracyFactor>
    <IgnoreOrientation>false</IgnoreOrientation>
    <LasMethod>FromImageCorrelation</LasMethod>
    <OrthoSettings>
      <SizeH>32768</SizeH>
      <SizeW>32768</SizeW>
    </OrthoSettings>
    <OrthophotoCompressionRatio>98</OrthophotoCompressionRatio>
    <OutputCoordinateSystem xmlns:d3p1="http://www.skylineglobe.com/schema-3dml">
      <d3p1:OriginalWKT>PROJCS["UTM zone 15, Northern Hemisphere",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",-93],PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",EAST],AXIS["Northing",NORTH],AUTHORITY["EPSG","32615"]]</d3p1:OriginalWKT>
      <d3p1:WKT>PROJCS["UTM zone 15, Northern Hemisphere",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",-93],PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",EAST],AXIS["Northing",NORTH],AUTHORITY["EPSG","32615"]]</d3p1:WKT>
    </OutputCoordinateSystem>
    <OutputFormats xmlns:d3p1="http://schemas.microsoft.com/2003/10/Serialization/Arrays">
      <d3p1:string>OBJ</d3p1:string>
    </OutputFormats>
    <PointCloudFormat>LAS</PointCloudFormat>
    <PointCloudQuality>4</PointCloudQuality>
    <PrincipalPointAccuracy>-1</PrincipalPointAccuracy>
    <RadialAccuracy>false</RadialAccuracy>
    <TangentialAccuracy>false</TangentialAccuracy>
    <TileSplitMethod>Simple</TileSplitMethod>
    <VerticalAccuracyFactor>0.1</VerticalAccuracyFactor>
    <VerticalBias>false</VerticalBias>
  </BuildParameters>
  <Description>ste toolkit output preset </Description>
  <IsDefault>false</IsDefault>
  <IsLastUsed>false</IsLastUsed>
  <IsSystem>false</IsSystem>
  <IsSystemDefault>false</IsSystemDefault>
  <PresetFileName i:nil="true" />
  <PresetName>STEPRESET</PresetName>
</BuildParametersPreset>
"""

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

def _write_text_atomic(path: str, text: str, log=print) -> None:
    dstdir = os.path.dirname(path)
    _ensure_dir(dstdir)
    if _files_equal_text(path, text):
        log(f"Preset already up to date -> {path}")
        return
    tmp = os.path.join(dstdir, f".{os.path.basename(path)}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    with open(tmp, "wb") as f:
        f.write(text.encode("utf-8"))
    os.replace(tmp, path)
    log(f"Preset written -> {path}")

def install_embedded_preset(log=print) -> str:
    """
    Writes the embedded PRESET_XML to PRESET_PATH (AppData Presets).
    Additionally stages the preset to known Wizard preset directories.
    Returns the AppData PRESET_PATH that we control.
    """
    _write_text_atomic(PRESET_PATH, PRESET_XML, log=log)
    for d in WIZARD_PRESET_DIRS:
        dst = os.path.join(d, f"{PRESET_NAME}.PMPreset")
        try:
            _ensure_dir(d)
            if not (os.path.isfile(dst) and filecmp.cmp(PRESET_PATH, dst, shallow=False)):
                tmp = dst + f".{os.getpid()}.{uuid.uuid4().hex}.tmp"
                shutil.copy2(PRESET_PATH, tmp)
                try:
                    os.replace(tmp, dst)
                finally:
                    if os.path.exists(tmp):
                        try:
                            os.remove(tmp)
                        except Exception:
                            pass
                log(f"Staged preset -> {dst}")
            else:
                log(f"Preset already up to date -> {dst}")
        except PermissionError as e:
            log(f"Skipping staged copy (permission): {dst} ({e})")
        except OSError as e:
            log(f"Skipping staged copy (locked/in use): {dst} ({e})")

    return PRESET_PATH
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
if is_windows() and not is_admin():
    print("[INFO] Elevation required. Relaunching as Administrator…")
    relaunch_self_as_admin()
    sys.exit(0)

try:
    installed = install_embedded_preset()
    print(f"[CFG] Embedded preset installed to: {installed}")
except Exception as e:
    print(f"[WARN] Could not install embedded preset: {e}")

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
        "SelectedPreset": PRESET_NAME,
        "OverrideSettings": False,
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

def clear_wizard_preset_overrides(log=print):
    """
    Remove any saved 'Selected Presets (last override)' so Wizard won't apply them.
    Edits install-level and per-user Wizard config.json files if present.
    """
    import json, os

    CANDIDATE_KEYS = {
        "SelectedPresets", "Selected Presets",
        "PresetOverrides", "LastPresetOverrides",
        "LastOverrideSelection", "OverridePresetList",
        "PresetStack", "SelectedPresetNames",
    }

    def _scrub(d):
        if isinstance(d, dict):
            for k in list(d.keys()):
                if k in CANDIDATE_KEYS:
                    d[k] = [] if isinstance(d[k], list) else {}
                else:
                    _scrub(d[k])
        elif isinstance(d, list):
            for x in d:
                _scrub(x)

    def _try_path(p):
        if not os.path.isfile(p):
            return False
        try:
            with open(p, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            _scrub(cfg)
            # optional flags some builds honor
            cfg.setdefault("PresetManager", {}).update({
                "ApplyOverridesOnLaunch": False,
                "UseLastPresetOverride": False,
            })
            with open(p, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            log(f"Cleared Wizard preset overrides → {p}")
            return True
        except Exception as e:
            log(f"Skip clearing overrides at {p}: {e}")
            return False

    # Known locations
    paths = []
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base:
            paths.append(os.path.join(base, "Skyline", "PhotoMesh", "Tools", "PhotomeshWizard", "config.json"))
            paths.append(os.path.join(base, "Skyline", "PhotoMeshWizard", "config.json"))  # legacy
    local = os.environ.get("LOCALAPPDATA")
    if local:
        paths.append(os.path.join(local, "Skyline", "PhotoMesh", "PhotomeshWizard", "config.json"))

    touched = any(_try_path(p) for p in paths)
    if not touched:
        log("No Wizard config.json found to clear overrides.")

# Resolve preset locations for the Wizard
def _resolve_preset_for_wizard(preset_name: str) -> str | None:
    """Return absolute path to <preset_name>.PMPreset in a Wizard Presets dir if found; else None."""
    for d in WIZARD_PRESET_DIRS:
        p = os.path.join(d, f"{preset_name}.PMPreset")
        if os.path.isfile(p):
            return p
    p = os.path.join(os.environ.get("APPDATA", ""), "Skyline", "PhotoMesh", "Presets", f"{preset_name}.PMPreset")
    return p if os.path.isfile(p) else None

# -------------------- Launch Wizard with preset --------------------
def launch_wizard_with_preset(
    project_name: str,
    project_path: str,
    imagery_folders: Iterable[str],
    *,
    autostart: bool = True,
    fuser_unc: Optional[str] = None,
    want_ortho: bool = False,
    preset: str = PRESET_NAME,
    log=print,
) -> subprocess.Popen:
    """Start PhotoMesh Wizard with an explicit preset."""

    # Minimal install-config seeding: allow Wizard to start
    try:
        enforce_wizard_install_config(
            model3d=True,
            obj=True,
            d3dml=True if not want_ortho else True,   # keep 3DML on in UI so Wizard can start
            ortho_ui=bool(want_ortho),                # UI checkbox only
            center_pivot=True,
            ellipsoid=True,
            fuser_unc=fuser_unc,
            log=log,
        )
    except PermissionError:
        log("⚠️ Could not update install config (permission). Continuing.")

    # Clear any remembered preset/UI overrides so the .PMPreset is honored
    clear_wizard_preset_overrides(log=log)

    # Resolve absolute preset path inside a Wizard Presets folder
    preset_abs = _resolve_preset_for_wizard(preset or PRESET_NAME)
    if not preset_abs:
        raise FileNotFoundError(f"Preset not found in Wizard Presets: {preset or PRESET_NAME}")

    # Build CLI: NO --overrideSettings
    args = [WIZARD_EXE, "--projectName", project_name, "--projectPath", project_path, "--preset", preset_abs]
    if autostart:
        args.append("--autostart")
    for f in imagery_folders or []:
        args += ["--folder", f]

    log(f"[Wizard] WIZARD_DIR: {WIZARD_DIR}")
    log(f"[Wizard] WIZARD_EXE: {WIZARD_EXE}")
    log(f"[Wizard] Using preset file: {preset_abs}")
    log(f"[Wizard] Launch cmd: {args}")

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


# ---------- Locate Wizard Presets ----------
def _wizard_presets_dirs() -> list[str]:
    """Return existing Wizard preset directories."""
    return [d for d in WIZARD_PRESET_DIRS if os.path.isdir(d)]


def _atomic_write_text(path: str, text: str) -> None:
    """Atomically write text to path."""
    tmp = f"{path}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "wb") as f:
        f.write(text.encode("utf-8"))
    os.replace(tmp, path)


# ---------- Patch the 3D preset ----------
def patch_3d_preset_obj_only(log=print) -> None:
    """Force the Wizard's 3D preset to OBJ-only with center/ellipsoid options."""
    ns_arrays = {"arr": "http://schemas.microsoft.com/2003/10/Serialization/Arrays"}
    ET.register_namespace("arr", ns_arrays["arr"])

    patched_any = False
    for d in _wizard_presets_dirs():
        preset_path = os.path.join(d, "3D.PMPreset")
        if not os.path.isfile(preset_path):
            log(f"⚠️  Not found: {preset_path}")
            continue

        bak = f"{preset_path}.bak.{time.strftime('%Y%m%d-%H%M%S')}"
        try:
            shutil.copy2(preset_path, bak)
            log(f"Backup → {bak}")
        except Exception as e:  # pragma: no cover - best effort
            log(f"Backup skipped: {e}")

        tree = ET.parse(preset_path)
        root = tree.getroot()

        def ensure(tag: str) -> ET.Element:
            e = root.find(f".//{tag}")
            if e is None:
                bp = root.find(".//BuildParameters")
                e = ET.SubElement(bp if bp is not None else root, tag)
            return e

        of = root.find(".//OutputFormats")
        if of is None:
            of = ET.SubElement(ensure("BuildParameters"), "OutputFormats")
        for c in list(of):
            of.remove(c)
        of.append(ET.Element(f"{{{ns_arrays['arr']}}}string"))
        of[-1].text = "OBJ"

        ensure("CenterModelsToProject").text = "true"
        if root.find(".//CesiumReprojectZ") is None:
            ET.SubElement(ensure("BuildParameters"), "CesiumReprojectZ").text = "true"
        else:
            root.find(".//CesiumReprojectZ").text = "true"

        cp = root.find(".//CenterPivotToProject")
        if cp is not None:
            cp.text = "true"

        desc = ensure("Description")
        desc.text = (desc.text or "3D") + "  [OBJ-only via launcher]"
        pn = ensure("PresetName")
        if pn.text != "3D":
            pn.text = "3D"

        xml_str = ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")
        _atomic_write_text(preset_path, xml_str)
        log(f"✅ Patched: {preset_path}")
        patched_any = True

    if not patched_any:
        log("❌ No Wizard Presets folder found / 3D.PMPreset missing.")


# ---------- (Optional) disable WizardGenerated 3DML override ----------
def disable_wizard_generated_override(log=print) -> None:
    for d in _wizard_presets_dirs():
        for fname in ("WizardGenerated_Output_3DML_.PMPreset", "WizardGenerated_Output.PMPreset"):
            p = os.path.join(d, fname)
            if os.path.isfile(p):
                try:
                    os.replace(p, p + ".disabled")
                    log(f"🔒 Disabled override preset → {p}.disabled")
                except Exception as e:  # pragma: no cover - best effort
                    log(f"Skip disabling {p}: {e}")


if __name__ == "__main__":  # pragma: no cover - manual run utility
    print("Patching 3D.PMPreset to OBJ-only, with center/ellipsoid...")
    patch_3d_preset_obj_only()
    disable_wizard_generated_override()
    print("Done. Launch the Wizard and open Presets to confirm.")
