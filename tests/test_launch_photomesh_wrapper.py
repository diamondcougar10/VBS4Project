import sys
from pathlib import Path


# Ensure the photomesh module is importable
sys.path.append(str(Path(__file__).resolve().parents[1] / "PythonPorjects"))

from photomesh_launcher import (
    stage_install_preset,
    launch_wizard_with_preset,
)


def test_launch_wizard_with_preset(monkeypatch):
    called = {}

    def fake_popen(args, cwd=None, creationflags=0):  # pragma: no cover - dummy
        called["args"] = args
        called["cwd"] = cwd
        called["creationflags"] = creationflags

    monkeypatch.setattr(
        "photomesh_launcher.subprocess.Popen", fake_popen
    )
    monkeypatch.setattr(
        "photomesh_launcher.WIZARD_EXE", "wiz.exe"
    )
    monkeypatch.setattr(
        "photomesh_launcher.WIZARD_DIR", "wizdir"
    )
    monkeypatch.setattr(
        "photomesh_launcher.enforce_wizard_install_config",
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
def test_stage_install_preset(monkeypatch):
    copies = []

    monkeypatch.setattr(
        "photomesh_launcher.os.path.isfile", lambda p: True
    )
    monkeypatch.setattr(
        "photomesh_launcher.os.makedirs", lambda p, exist_ok=True: None
    )
    monkeypatch.setattr(
        "photomesh_launcher.shutil.copy2",
        lambda src, dst: copies.append((src, dst)),
    )

    stage_install_preset("repo.PMPreset", "Preset")

    assert len(copies) == 3
    assert all(src == "repo.PMPreset" for src, _ in copies)

