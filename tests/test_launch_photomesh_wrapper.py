import sys
from pathlib import Path


# Ensure the photomesh package is importable
sys.path.append(str(Path(__file__).resolve().parents[1] / "PythonPorjects"))

from photomesh.launch_photomesh_preset import (
    launch_photomesh_with_install_preset,
    launch_wizard_with_preset,
)


def test_launch_wizard_with_preset(monkeypatch):
    called = {}

    def fake_popen(args, cwd=None, creationflags=0):  # pragma: no cover - dummy
        called["args"] = args
        called["cwd"] = cwd
        called["creationflags"] = creationflags

    monkeypatch.setattr(
        "photomesh.launch_photomesh_preset.subprocess.Popen", fake_popen
    )
    monkeypatch.setattr(
        "photomesh.launch_photomesh_preset.WIZARD_EXE", "wiz.exe"
    )
    monkeypatch.setattr(
        "photomesh.launch_photomesh_preset.WIZARD_DIR", "wizdir"
    )
    monkeypatch.setattr(
        "photomesh.launch_photomesh_preset.enforce_wizard_install_config",
        lambda **kwargs: None,
    )

    launch_wizard_with_preset("proj", "path", ["a", "b"], preset="Preset")

    assert called["cwd"] == "wizdir"
    assert called["args"] == [
        "wiz.exe",
        "--projectName",
        "proj",
        "--projectPath",
        "path",
        "--overrideSettings",
        "--preset",
        "Preset",
        "--autostart",
        "--folder",
        "a",
        "--folder",
        "b",
    ]


def test_launch_photomesh_with_install_preset(monkeypatch):
    calls = {}

    def fake_stage(repo_preset_path, preset_name):
        calls["stage"] = (repo_preset_path, preset_name)

    def fake_launch(project_name, project_path, folders, preset=None, *, autostart=True, fuser_unc=None, log=print):
        calls["launch"] = (project_name, project_path, tuple(folders), preset, autostart, fuser_unc)

    monkeypatch.setattr(
        "photomesh.launch_photomesh_preset.stage_install_preset", fake_stage
    )
    monkeypatch.setattr(
        "photomesh.launch_photomesh_preset.launch_wizard_with_preset",
        fake_launch,
    )

    launch_photomesh_with_install_preset(
        "proj", "path", ["a", "b"], "Preset", "repo.preset"
    )

    assert calls["stage"] == ("repo.preset", "Preset")
    assert calls["launch"] == ("proj", "path", ("a", "b"), "Preset", True, None)

