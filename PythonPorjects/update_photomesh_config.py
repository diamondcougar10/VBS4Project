import json
import sys
import ctypes
import os

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


def update_config(path: str) -> None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"❌ File not found: {path}")
        return
    except PermissionError as exc:
        print(f"❌ Permission denied reading file: {exc}")
        return
    except json.JSONDecodeError as exc:
        print(f"❌ Failed to parse JSON: {exc}")
        return

    # Update the desired field
    config.setdefault("DefaultPhotoMeshWizardUI", {}).setdefault("Model3DFormats", {})["OBJ"] = True

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        print("✅ config.json updated successfully.")
    except PermissionError as exc:
        print(f"❌ Permission denied writing file: {exc}")
        print("Please run this script as Administrator.")
    except Exception as exc:
        print(f"❌ Failed to update config: {exc}")


if __name__ == "__main__":
    if not is_admin():
        print("⚠️  This script needs to run with Administrator privileges.")
        if elevate():
            sys.exit(0)
        else:
            print("❌ Could not obtain elevated privileges. Please rerun this script as Administrator.")
            sys.exit(1)
    update_config(CONFIG_PATH)
    input("Press Enter to exit...")
