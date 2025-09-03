import sys
from pathlib import Path


# Ensure the photomesh module is importable
sys.path.append(str(Path(__file__).resolve().parents[1] / "PythonPorjects"))

import photomesh_launcher
from photomesh_launcher import (
    install_embedded_preset,
    launch_wizard_with_preset,
    get_offline_cfg,
    resolve_network_working_folder_from_cfg,
    PRESET_NAME,
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

    launch_wizard_with_preset("proj", "path", ["a", "b"])

    assert called["cwd"] == "wizdir"
    assert called["args"] == [
        "wiz.exe",
        "--projectName",
        "proj",
        "--projectPath",
        "path",
        "--folder",
        "a",
        "--folder",
        "b",
        "--overrideSettings",
        "--preset",
        PRESET_NAME,
        "--autostart",
    ]
def test_install_embedded_preset(monkeypatch):
    calls = []

    def fake_write(path, text, log=print):
        calls.append((path, text))

    monkeypatch.setattr("photomesh_launcher._write_text_atomic", fake_write)
    monkeypatch.setattr("photomesh_launcher._ensure_dir", lambda p: None)
    monkeypatch.setattr("photomesh_launcher.os.path.isfile", lambda p: True)
    monkeypatch.setattr("photomesh_launcher.filecmp.cmp", lambda a, b, shallow=False: True)

    path = install_embedded_preset(log=lambda *_: None)

    assert path == photomesh_launcher.PRESET_PATH
    assert calls[0][0] == photomesh_launcher.PRESET_PATH
    assert calls[0][1].startswith("<?xml")


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

