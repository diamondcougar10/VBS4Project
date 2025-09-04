import json
import os

CONFIG_PATH = r"C:\Program Files\Skyline\PhotoMeshWizard\config.json"


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

    ui = config.setdefault("DefaultPhotoMeshWizardUI", {})
    ui.setdefault("OutputProducts", {}).update({"Model3D": True})
    fmts = ui.setdefault("Model3DFormats", {})
    fmts["3DML"] = True
    fmts["OBJ"] = True
    # Optional:
    # fmts["LAS"] = True

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
    update_config(CONFIG_PATH)
