import ctypes
import json
import os
import sys
import tempfile

CONFIG_PATH = r"C:\Program Files\Skyline\PhotoMeshWizard\config.json"


def is_admin() -> bool:
    """Check for administrative privileges on Windows."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def elevate() -> bool:
    """Attempt to relaunch the script with admin rights."""
    params = " ".join(f'"{arg}"' for arg in sys.argv)
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        return int(ret) > 32
    except Exception:
        return False


def _atomic_write(path: str, data: str, encoding: str = "utf-8") -> None:
    directory = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=os.path.basename(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(data)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise


def patch_wizard_config_minimal(path: str) -> None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        print(f"❌ File not found: {path}")
        return
    except PermissionError as exc:
        print(f"❌ Permission denied reading file: {exc}")
        return
    except json.JSONDecodeError as exc:
        print(f"❌ Failed to parse JSON: {exc}")
        return

    changed = {}
    try:
        ui = cfg["DefaultPhotoMeshWizardUI"]
        outputs = ui["OutputProducts"]
        fmts = ui["Model3DFormats"]

        before = {
            "Model3D": outputs.get("Model3D"),
            "Ortho": outputs.get("Ortho"),
            "OBJ": fmts.get("OBJ"),
            "3DML": fmts.get("3DML"),
        }

        if "Model3D" in outputs:
            outputs["Model3D"] = True
        if "Ortho" in outputs:
            outputs["Ortho"] = True
        if "OBJ" in fmts:
            fmts["OBJ"] = True
        if "3DML" in fmts:
            fmts["3DML"] = False

        after = {
            "Model3D": outputs.get("Model3D"),
            "Ortho": outputs.get("Ortho"),
            "OBJ": fmts.get("OBJ"),
            "3DML": fmts.get("3DML"),
        }

        changed = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    except KeyError:
        print("[warn] config.json structure missing expected keys; no changes made.")
        return

    if changed:
        _atomic_write(path, json.dumps(cfg, indent=2))
        print("[ok] Patched Wizard config (minimal). Changes:")
        for key, (b, a) in changed.items():
            print(f"  - {key}: {b} -> {a}")
    else:
        print("[ok] No changes needed; values already correct.")


if __name__ == "__main__":
    if not is_admin():
        print("⚠️  This script needs to run with Administrator privileges.")
        if elevate():
            sys.exit(0)
        else:
            print("❌ Could not obtain elevated privileges. Please rerun this script as Administrator.")
            sys.exit(1)
    patch_wizard_config_minimal(CONFIG_PATH)
    input("Press Enter to exit...")
