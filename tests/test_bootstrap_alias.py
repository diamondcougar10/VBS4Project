import sys
from pathlib import Path
import subprocess

# Ensure the photomesh package is importable
sys.path.append(str(Path(__file__).resolve().parents[1] / "PythonPorjects"))

import photomesh.bootstrap as bootstrap


def test_prepare_photomesh_environment_preset_name(monkeypatch):
    called = {}
    monkeypatch.setattr(bootstrap, "ensure_oeccp_preset_in_appdata", lambda repo_hint: "preset_path")
    def mock_set_default(preset):
        called["preset"] = preset
    monkeypatch.setattr(bootstrap, "set_default_preset_in_presetsettings", mock_set_default)
    monkeypatch.setattr(bootstrap, "set_user_wizard_defaults", lambda preset, autostart: None)
    bootstrap.prepare_photomesh_environment_per_user("repo", preset_name="OECPP")
    assert called["preset"] == "OECPP"


def test_launch_wizard_with_preset_alias(monkeypatch):
    monkeypatch.setattr(bootstrap, "find_wizard_exe", lambda: "wizard.exe")
    popen_args = {}
    class DummyPopen:
        def __init__(self, args, cwd=None):
            popen_args["args"] = args
            popen_args["cwd"] = cwd
    monkeypatch.setattr(subprocess, "Popen", DummyPopen)
    bootstrap.launch_wizard_with_preset("proj", "path", ["f1"], preset_name="OECPP")
    args = popen_args["args"]
    idx = args.index("--preset") + 1
    assert args[idx] == "OECPP"
