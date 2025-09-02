import sys
from pathlib import Path


# Ensure the photomesh package is importable
sys.path.append(str(Path(__file__).resolve().parents[1] / "PythonPorjects"))

from photomesh.launch_photomesh_preset import launch_wizard_with_preset


def test_launch_wizard_with_preset(monkeypatch):
    called = {}

    def fake_prepare(host):  # pragma: no cover - dummy
        called["host"] = host

    def fake_popen(args, cwd=None):  # pragma: no cover - dummy
        called["args"] = args
        called["cwd"] = cwd

    monkeypatch.setattr(
        "photomesh.launch_photomesh_preset.prepare_presets_and_wizard_defaults",
        fake_prepare,
    )
    monkeypatch.setattr(
        "photomesh.launch_photomesh_preset.subprocess.Popen", fake_popen
    )
    monkeypatch.setattr(
        "photomesh.launch_photomesh_preset.WIZARD_EXE", "wiz.exe"
    )
    monkeypatch.setattr(
        "photomesh.launch_photomesh_preset.WIZARD_DIR", "wizdir"
    )

    launch_wizard_with_preset("proj", "path", ["a", "b"], host="kit1-1")

    assert called["host"] == "kit1-1"
    assert called["cwd"] == "wizdir"
    assert called["args"] == [
        "wiz.exe",
        "--projectName",
        "proj",
        "--projectPath",
        "path",
        "--preset",
        "OECPP",
        "--overrideSettings",
        "--autostart",
        "--folder",
        "a",
        "--folder",
        "b",
    ]

