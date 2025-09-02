import sys
from pathlib import Path


# Ensure the photomesh module is importable
sys.path.append(str(Path(__file__).resolve().parents[1] / "PythonPorjects"))

from photomesh_launcher import (
    stage_install_preset,
    launch_wizard_with_preset,
    get_offline_cfg,
    resolve_network_working_folder_from_cfg,
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
    monkeypatch.setattr(
        "photomesh_launcher.stage_preset",
        lambda preset: preset,
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


def test_offline_cfg_resolution(monkeypatch):
    import configparser

    cfg = configparser.ConfigParser()
    cfg.read_dict(
        {
            "Offline": {
                "enabled": "true",
                "host_name": "HOST",
                "host_ip": "1.2.3.4",
                "share_name": "Share",
                "local_data_root": r"D:\\Share",
                "working_fuser_subdir": "WorkingFuser",
                "use_ip_unc": "true",
            }
        }
    )
    monkeypatch.setattr("photomesh_launcher.config", cfg)
    monkeypatch.setattr("photomesh_launcher.CONFIG_PATH", "nonexistent.ini")

    o = get_offline_cfg()
    assert o["host_ip"] == "1.2.3.4"
    path = resolve_network_working_folder_from_cfg(o)
    assert path == r"\\1.2.3.4\Share\WorkingFuser"

