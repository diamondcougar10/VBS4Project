"""Thin wrapper to install a preset and launch PhotoMesh with it."""

from __future__ import annotations

from .bootstrap import stage_install_preset, launch_autostart_build


def launch_photomesh_with_install_preset(
    project_name: str,
    project_path: str,
    imagery_folders: list[str],
    preset_name: str,
    repo_preset_path: str,
):
    """Stage *repo_preset_path* under Program Files and start an autostart build."""

    stage_install_preset(repo_preset_path, preset_name)
    return launch_autostart_build(
        project_name, project_path, imagery_folders, preset_name
    )


__all__ = ["launch_photomesh_with_install_preset"]

