from __future__ import annotations
import os, json, shutil, subprocess, tempfile
from typing import Iterable, Optional

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

# -------------------- “modify only if key exists” patcher --------------------
def _patch_existing(d: dict, path: list[str], value) -> bool:
    """
    Follow 'path' without creating new keys; set the leaf only if it exists.
    Returns True if a change was applied.
    """
    cur = d
    for k in path[:-1]:
        if not isinstance(cur, dict) or k not in cur or not isinstance(cur[k], dict):
            return False
        cur = cur[k]
    leaf = path[-1]
    if isinstance(cur, dict) and leaf in cur and cur[leaf] != value:
        cur[leaf] = value
        return True
    return False

# -------------------- Write Wizard config (minimal, no new keys) --------------------
def enforce_wizard_install_config(
    *, model3d: bool = True, obj: bool = True, d3dml: bool = False, ortho_ui: bool = True,
    center_pivot: bool = True, ellipsoid: bool = True, fuser_unc: Optional[str] = None, log=print
) -> None:
    """
    Edit ONLY existing keys in <Wizard>\config.json:
      DefaultPhotoMeshWizardUI.OutputProducts.Model3D = True
      DefaultPhotoMeshWizardUI.OutputProducts.Ortho   = ortho_ui (UI-only)
      DefaultPhotoMeshWizardUI.Model3DFormats.OBJ     = obj
      DefaultPhotoMeshWizardUI.Model3DFormats.3DML    = d3dml
      DefaultPhotoMeshWizardUI.CenterPivotToProject   = center_pivot
      DefaultPhotoMeshWizardUI.ReprojectToEllipsoid   = ellipsoid
      NetworkWorkingFolder = fuser_unc (if provided)
    """
    cfg = _load_json(WIZARD_INSTALL_CFG)
    changed = False
    changed |= _patch_existing(cfg, ["DefaultPhotoMeshWizardUI","OutputProducts","Model3D"], bool(model3d))
    changed |= _patch_existing(cfg, ["DefaultPhotoMeshWizardUI","OutputProducts","Ortho"],   bool(ortho_ui))
    changed |= _patch_existing(cfg, ["DefaultPhotoMeshWizardUI","Model3DFormats","OBJ"],     bool(obj))
    changed |= _patch_existing(cfg, ["DefaultPhotoMeshWizardUI","Model3DFormats","3DML"],    bool(d3dml))
    changed |= _patch_existing(cfg, ["DefaultPhotoMeshWizardUI","CenterPivotToProject"],     bool(center_pivot))
    changed |= _patch_existing(cfg, ["DefaultPhotoMeshWizardUI","ReprojectToEllipsoid"],     bool(ellipsoid))

    if fuser_unc and isinstance(cfg, dict):
        # Allow write if the key exists at root (don’t inject new trees)
        if "NetworkWorkingFolder" in cfg and cfg["NetworkWorkingFolder"] != fuser_unc:
            cfg["NetworkWorkingFolder"] = fuser_unc
            changed = True

    if changed:
        _save_json(WIZARD_INSTALL_CFG, cfg)
        log(f"Wizard config updated: {WIZARD_INSTALL_CFG}")

# -------------------- Preset staging (Program Files + Wizard) --------------------
def stage_install_preset(repo_preset_path: str, preset_name: str, log=print) -> None:
    """
    Copy a .PMPreset to both Program Files preset folders and AppData fallback.
    No XML rewriting here; assume repo preset already encodes OBJ-only + pivot + ellipsoid.
    """
    if not os.path.isfile(repo_preset_path):
        raise FileNotFoundError(repo_preset_path)

    if not repo_preset_path.lower().endswith(".pmpreset"):
        raise ValueError("Preset must be a .PMPreset")

    targets = [
        os.path.join(r"C:\\Program Files\\Skyline\\PhotoMesh\\Presets", f"{preset_name}.PMPreset"),
        os.path.join(WIZARD_DIR, "Presets", f"{preset_name}.PMPreset"),  # Wizard Presets
        os.path.join(os.environ.get("APPDATA",""), "Skyline","PhotoMesh","Presets", f"{preset_name}.PMPreset"),
    ]
    for dst in targets:
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(repo_preset_path, dst)
            log(f"Staged preset -> {dst}")
        except Exception as e:
            log(f"Skipping preset copy to {dst}: {e}")

# -------------------- Launch Wizard with preset --------------------
def launch_wizard_with_preset(
    project_name: str,
    project_path: str,
    imagery_folders: Iterable[str],
    *,
    preset: Optional[str] = None,
    autostart: bool = True,
    fuser_unc: Optional[str] = None,
    log=print,
) -> subprocess.Popen:
    """
    Start PhotoMesh Wizard with --overrideSettings, optional --preset and --autostart.
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
    ]
    if preset:
        args += ["--preset", preset]
    if autostart:
        args += ["--autostart"]
    for f in imagery_folders or []:
        args += ["--folder", f]

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(args, cwd=WIZARD_DIR, creationflags=creationflags)
