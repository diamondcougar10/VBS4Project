# =============================================================================
# Project: VBS4Project
# File: update_photomesh_config.py
# Purpose: Enforce OBJ-only defaults and WorkingFuser UNC in Wizard config
# =============================================================================
# Table of Contents
#   1) Imports
#   2) Constants & Configuration
#   3) Paths & Environment
#   4) Data Models / Types (if any)
#   5) Utilities (pure helpers, no I/O)
#   6) File I/O & JSON helpers
#   7) Wizard Config (read/patch install config)
#   8) Network / UNC resolution
#   9) Launch / CLI argument builders
#  10) GUI / Tkinter handlers
#  11) Logging & Error handling
#  12) Main entry point
# =============================================================================

# region Imports
import os
import sys
import time
import subprocess
NO_WINDOW_FLAG = getattr(subprocess, "CREATE_NO_WINDOW", 0)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from STE_Toolkit import build_unc_from_cfg, get_offline_cfg
from photomesh_launcher import (
    resolve_network_working_folder_from_cfg,
    _load_json,
    _save_json,
)

CONFIGS = [
    r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard\\config.json",
    r"C:\\Program Files\\Skyline\\PhotoMeshWizard\\config.json",
    r"C:\\Program Files (x86)\\Skyline\\PhotoMesh\\Tools\\PhotomeshWizard\\config.json",
    r"C:\\Program Files (x86)\\Skyline\\PhotoMeshWizard\\config.json",
]
# endregion

# region Paths & Environment
# No additional environment paths required.
# endregion

# region Data Models / Types
# endregion

# region Utilities
def find_fuser_exe() -> str:
    """
    Try common install paths for PhotoMeshFuser.exe.
    Returns the path if found, empty string otherwise.
    """
    candidates = [
        r"C:\\Program Files\\Skyline\\PhotoMesh\\Fuser\\PhotoMeshFuser.exe",
        r"C:\\Program Files\\Skyline\\PhotoMesh\\Tools\\Fuser\\PhotoMeshFuser.exe",
        r"C:\\Program Files (x86)\\Skyline\\PhotoMesh\\Fuser\\PhotoMeshFuser.exe",
        r"C:\\Program Files (x86)\\Skyline\\PhotoMesh\\Tools\\Fuser\\PhotoMeshFuser.exe",
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    # Try walking PhotoMesh install folder
    for root_path in [r"C:\\Program Files\\Skyline\\PhotoMesh", r"C:\\Program Files (x86)\\Skyline\\PhotoMesh"]:
        if os.path.exists(root_path):
            for dp, dn, fn in os.walk(root_path):
                if "PhotoMeshFuser.exe" in fn:
                    return os.path.join(dp, "PhotoMeshFuser.exe")
    return ""

def seed_fuser_default(wf_unc: str) -> None:
    """
    Launch a fuser once with the correct UNC to let Skyline persist it as the default.
    This makes the fuser UI's 'Open Working Folder' open the right share thereafter.
    """
    if not wf_unc or not wf_unc.startswith("\\\\"):
        print(f"[seed_fuser] Invalid UNC path: {wf_unc}")
        return

    exe = find_fuser_exe()
    if not exe:
        print("[seed_fuser] PhotoMeshFuser.exe not found - fuser seeding skipped")
        return

    print(f"[seed_fuser] Seeding fuser default with: {wf_unc}")
    
    try:
        # Start 'first' fuser with the UNC so Skyline persists it.
        # Arguments: name, working_folder, auto_exit(0=no), show_ui(true)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        p = subprocess.Popen(
            [exe, "SeedFuser", wf_unc, "0", "true"], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            startupinfo=si,
            creationflags=NO_WINDOW_FLAG
        )
        
        # Give it time to initialize and save defaults (with hard timeout)
        max_wait_time = 10  # Hard limit: 10 seconds max
        wait_time = min(4, max_wait_time)  # Prefer 4 seconds but respect limit
        time.sleep(wait_time)
        
        # Best-effort shutdown with timeout; ignore errors if user already closed it
        try:
            # First try graceful termination
            subprocess.run(["taskkill", "/im", "PhotoMeshFuser.exe"], 
                         check=False, 
                         timeout=3,
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL,
                         creationflags=NO_WINDOW_FLAG)
            time.sleep(1)
            
            # If still running, force kill
            subprocess.run(["taskkill", "/im", "PhotoMeshFuser.exe", "/f"], 
                         check=False, 
                         timeout=2,
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL,
                         creationflags=NO_WINDOW_FLAG)
        except subprocess.TimeoutExpired:
            print("[seed_fuser] Warning: Timeout during fuser cleanup")
        except Exception:
            pass
            
        print("[seed_fuser] Fuser default seeded successfully")
        
    except Exception as e:
        print(f"[seed_fuser] Failed to seed fuser default: {e}")
# endregion

# region File I/O & JSON helpers
# Shared via photomesh_launcher._load_json/_save_json
# endregion

# region Wizard Config
def update_config(path: str) -> bool:
    """Force OBJ-only defaults and update NetworkWorkingFolder for Wizard 1.5.1."""
    if not os.path.isfile(path):
        return False

    cfg = _load_json(path) or {}

    ui = cfg.setdefault("DefaultPhotoMeshWizardUI", {})
    ui.setdefault("OutputProducts", {}).update({"Model3D": True})
    fmts = ui.setdefault("Model3DFormats", {})
    fmts["OBJ"] = True
    fmts["3DML"] = False
    fmts["SLPK"] = False
    ui.setdefault("VerticalDatum", "Ellipsoid")

    offline = get_offline_cfg()
    root_unc = build_unc_from_cfg(offline)
    wf_unc = ""
    if root_unc:
        subdir = (offline.get("working_fuser_subdir") or "WorkingFuser").strip() or "WorkingFuser"
        wf_unc = os.path.join(root_unc, subdir).replace("/", "\\")
    else:
        try:
            wf_unc = resolve_network_working_folder_from_cfg(offline)
        except Exception:
            wf_unc = ""

    if wf_unc:
        cfg["NetworkWorkingFolder"] = wf_unc

    if root_unc:
        projects_unc = os.path.join(root_unc, "Projects").replace("/", "\\")
        for key in ("ProjectsRoot", "ProjectsRootFolder", "ProjectsRootPath"):
            if key in cfg:
                cfg[key] = projects_unc
        paths = cfg.get("Paths")
        if isinstance(paths, dict):
            for key in ("ProjectsRoot", "ProjectRoot", "ProjectsFolder"):
                if key in paths:
                    paths[key] = projects_unc

    host_ip = (offline.get("host_ip") or "").strip()
    
    # Also ensure the host IP is set in the Network section for proper initialization
    if host_ip:
        try:
            import configparser
            # Use the same CONFIG_PATH resolution as STE_Toolkit
            from STE_Toolkit import CONFIG_PATH
            config_path = CONFIG_PATH
            
            if os.path.exists(config_path):
                config = configparser.ConfigParser()
                config.read(config_path)
                if "Network" not in config:
                    config["Network"] = {}
                config["Network"]["host"] = host_ip
                
                # Use atomic write for consistency
                tmp_path = config_path + ".tmp"
                with open(tmp_path, 'w') as f:
                    config.write(f)
                os.replace(tmp_path, config_path)
        except Exception:
            pass
    host_name = (offline.get("host_name") or "").strip()

    def _rewrite(value):
        if isinstance(value, dict):
            return {k: _rewrite(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_rewrite(v) for v in value]
        if isinstance(value, str) and host_ip:
            newv = value.replace("{host}", host_ip)
            if host_name:
                newv = newv.replace(f"\\\\{host_name}\\", f"\\\\{host_ip}\\")
                newv = newv.replace(f"//{host_name}/", f"//{host_ip}/")
            return newv
        return value

    cfg = _rewrite(cfg)

    try:
        _save_json(path, cfg)
    except PermissionError as exc:
        print(f"[Wizard 1.5.1] Permission denied writing {path}: {exc}")
        print("Run this updater as Administrator.")
        return False
    except Exception as exc:
        print(f"[Wizard 1.5.1] Failed updating {path}: {exc}")
        return False

    print(f"[Wizard 1.5.1] Updated -> {path}")
    return True
# endregion

# region Network / UNC resolution
# endregion

# region Launch / CLI argument builders
# endregion

# region GUI / Tkinter handlers
# endregion

# region Logging & Error handling
# endregion

# region Main entry point
def main() -> None:
    import argparse
    
    parser = argparse.ArgumentParser(description="Update PhotoMesh Wizard config and seed fuser defaults")
    parser.add_argument("--no-seed-fuser", action="store_true", default=False,
                       help="Skip seeding fuser default working folder")
    args = parser.parse_args()
    
    # Default to seeding enabled unless explicitly disabled
    should_seed_fuser = not args.no_seed_fuser
    
    any_ok = False
    wf_unc = ""
    
    # Update wizard configs
    for path in CONFIGS:
        if not os.path.isfile(path):
            continue
        if update_config(path):
            any_ok = True
    
    if not any_ok:
        print("No PhotoMesh Wizard config.json found in standard locations.")
    
    # Compute the working fuser UNC for seeding
    if should_seed_fuser:
        try:
            offline = get_offline_cfg()
            root_unc = build_unc_from_cfg(offline)
            if root_unc:
                subdir = (offline.get("working_fuser_subdir") or "WorkingFuser").strip() or "WorkingFuser"
                wf_unc = os.path.join(root_unc, subdir).replace("/", "\\")
            else:
                try:
                    wf_unc = resolve_network_working_folder_from_cfg(offline)
                except Exception:
                    wf_unc = ""
        except Exception as e:
            print(f"[main] Failed to compute working fuser UNC: {e}")
        
        # Only seed if we have a valid UNC and it's different from current Wizard setting
        if wf_unc:
            # Check if Wizard config already has the correct UNC (idempotency)
            needs_seeding = True
            for config_path in CONFIGS:
                if os.path.isfile(config_path):
                    try:
                        cfg = _load_json(config_path) or {}
                        if cfg.get("NetworkWorkingFolder") == wf_unc:
                            print(f"[main] Wizard config already has correct UNC: {wf_unc}")
                            needs_seeding = False
                            break
                    except Exception:
                        pass
            
            if needs_seeding:
                print(f"[main] Seeding fuser default with UNC: {wf_unc}")
                seed_fuser_default(wf_unc)
            else:
                print("[main] Fuser seeding skipped - already configured correctly")
        else:
            print("[main] No valid working fuser UNC found - skipping fuser seeding")
    else:
        print("[main] Fuser seeding disabled by command line argument")


if __name__ == "__main__":
    main()
# endregion

# =============================================================================
# Refactor Notes
# - Added atomic config read/write helpers.
# - Structured file with explicit sections and docstrings.
# =============================================================================

