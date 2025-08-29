"""Helpers for launching PhotoMesh Wizard with presets."""

from __future__ import annotations

import os
import subprocess

from .bootstrap import stage_install_preset


def _detect_wizard_dir() -> str:
    """Return the directory containing ``PhotoMeshWizard.exe``."""

    cands = [
        r"C:\\Program Files\\Skyline\\PhotoMeshWizard",
        r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard",
    ]
    for d in cands:
        if os.path.isdir(d):
            return d
    for dp, _, fs in os.walk(r"C:\\Program Files\\Skyline"):
        if "PhotoMeshWizard.exe" in fs or "WizardGUI.exe" in fs:
            return dp
    raise FileNotFoundError("Wizard not found")


def _find_wizard_exe(d: str) -> str:
    """Return the best wizard executable path in *d*."""

    for name in ("PhotoMeshWizard.exe", "WizardGUI.exe"):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    raise FileNotFoundError("Wizard executable not found")


try:  # pragma: no cover - environment specific
    WIZARD_DIR = _detect_wizard_dir()
except FileNotFoundError:  # pragma: no cover - missing install
    WIZARD_DIR = r"C:\\Program Files\\Skyline\\PhotoMeshWizard"

try:  # pragma: no cover - environment specific
    WIZARD_EXE = _find_wizard_exe(WIZARD_DIR)
except FileNotFoundError:  # pragma: no cover - missing install
    WIZARD_EXE = os.path.join(WIZARD_DIR, "PhotoMeshWizard.exe")


def launch_wizard_with_preset(
    project_name: str,
    project_path: str,
    imagery_folders: list[str] | None,
    preset: str | None = None,
    extra_args: list[str] | None = None,
) -> subprocess.Popen:
    """Launch PhotoMesh Wizard and autostart the build with our preset."""

    args = [
        WIZARD_EXE,
        "--projectName",
        project_name,
        "--projectPath",
        project_path,
        "--overrideSettings",
        "--autostart",
    ]
    if preset:
        args += ["--preset", preset]

    for f in imagery_folders or []:
        args += ["--folder", f]

    if extra_args:
        args += extra_args

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


__all__ = ["launch_wizard_with_preset", "launch_photomesh_with_install_preset"]

