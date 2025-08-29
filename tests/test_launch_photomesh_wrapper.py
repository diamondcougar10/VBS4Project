import sys
from pathlib import Path


# Ensure the photomesh package is importable
sys.path.append(str(Path(__file__).resolve().parents[1] / "PythonPorjects"))

from photomesh.launch_photomesh_preset import (
    launch_photomesh_with_install_preset,
)


def test_launch_photomesh_with_install_preset(monkeypatch):
    calls = {}

    def fake_stage(repo_preset_path, preset_name):
        calls["stage"] = (repo_preset_path, preset_name)

    def fake_launch(project_name, project_path, folders, preset_name):
        calls["launch"] = (project_name, project_path, tuple(folders), preset_name)

    monkeypatch.setattr(
        "photomesh.launch_photomesh_preset.stage_install_preset", fake_stage
    )
    monkeypatch.setattr(
        "photomesh.launch_photomesh_preset.launch_autostart_build", fake_launch
    )

    launch_photomesh_with_install_preset(
        "proj", "path", ["a", "b"], "Preset", "repo.preset"
    )

    assert calls["stage"] == ("repo.preset", "Preset")
    assert calls["launch"] == ("proj", "path", ("a", "b"), "Preset")

