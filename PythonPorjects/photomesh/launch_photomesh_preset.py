"""Helpers for launching PhotoMesh Wizard with presets."""

from __future__ import annotations

import os
import json
import subprocess

from .bootstrap import stage_install_preset


def _detect_wizard_dir() -> str:
    candidates = [
        r"C:\\Program Files\\Skyline\\PhotoMeshWizard",                 # NEW preferred
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


def _load_json_safe(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json_safe(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def enforce_wizard_install_config(
    *, obj: bool = True, ortho: bool = True, fuser_unc: str | None = None, log=print
):
    """
    Write C:\Program Files\Skyline\PhotoMeshWizard\config.json (or legacy) so:
      - OutputProducts: 3D Model ON, Ortho ON (Wizard-only requirement)
      - Model3DFormats: OBJ=True, 3DML=False
      - CenterPivot/ReprojectEllipsoid = True
      - NetworkWorkingFolder = fuser UNC (param or Offline cfg)
      - UseMinimize=True, ClosePMWhenDone=True
    """

    cfg = _load_json_safe(WIZARD_INSTALL_CFG)

    ui = cfg.setdefault("DefaultPhotoMeshWizardUI", {})
    outs = ui.setdefault("OutputProducts", {})
    # Support both key spellings (seen in the wild)
    outs["3DModel"] = True
    outs["Model3D"] = True
    outs["Ortho"] = bool(ortho)

    m3d = ui.setdefault("Model3DFormats", {})
    # turn all boolean formats off then explicitly enable OBJ only
    for k, v in list(m3d.items()):
        if isinstance(v, bool):
            m3d[k] = False
    m3d["OBJ"] = bool(obj)
    m3d["3DML"] = False

    # Pivot/Ellipsoid flags used by downstream step
    ui["CenterPivotToProject"] = True
    ui["CenterModelsToProject"] = True
    ui["ReprojectToEllipsoid"] = True

    # UX niceties
    cfg["UseMinimize"] = True
    cfg["ClosePMWhenDone"] = True

    # Fuser working UNC
    if fuser_unc is None:
        try:
            # If you already have these helpers in your project, they’ll resolve from Offline settings:
            from .bootstrap import get_offline_cfg, resolve_network_working_folder_from_cfg

            fuser_unc = resolve_network_working_folder_from_cfg(get_offline_cfg())
        except Exception:
            # Default if Offline cfg is not available
            fuser_unc = r"\\KIT1-1\SharedMeshDrive\WorkingFuser"
    cfg["NetworkWorkingFolder"] = fuser_unc

    _save_json_safe(WIZARD_INSTALL_CFG, cfg)
    log(
        f"✅ Wizard config updated: {WIZARD_INSTALL_CFG}\n"
        f"   - 3DModel=True, Ortho={outs['Ortho']}\n"
        f"   - OBJ={m3d.get('OBJ')}, 3DML={m3d.get('3DML')}\n"
        f"   - NetworkWorkingFolder={cfg['NetworkWorkingFolder']}"
    )


def launch_wizard_with_preset(
    project_name: str,
    project_path: str,
    imagery_folders: list[str] | None,
    preset: str | None = None,
    *,
    autostart: bool = True,
    fuser_unc: str | None = None,
    log=print,
) -> subprocess.Popen:
    """Launch PhotoMesh Wizard and optionally autostart the build with our preset."""

    # Write install-level config so the Wizard starts with correct UI flags & fuser UNC
    try:
        enforce_wizard_install_config(obj=True, ortho=True, fuser_unc=fuser_unc, log=log)
    except PermissionError:
        log(
            "⚠️ No permission to write install-level config.json (run as Admin or pre-stage). Continuing."
        )

    args = [
        WIZARD_EXE,
        "--projectName",
        project_name,
        "--projectPath",
        project_path,
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


def launch_photomesh_with_install_preset(
    project_name: str,
    project_path: str,
    imagery_folders: list[str],
    preset_name: str,
    repo_preset_path: str,
) -> subprocess.Popen:
    """Stage *repo_preset_path* under Program Files and start an autostart build."""

    stage_install_preset(repo_preset_path, preset_name)
    return launch_wizard_with_preset(
        project_name, project_path, imagery_folders, preset=preset_name
    )


__all__ = [
    "launch_wizard_with_preset",
    "launch_photomesh_with_install_preset",
    "enforce_wizard_install_config",
]

