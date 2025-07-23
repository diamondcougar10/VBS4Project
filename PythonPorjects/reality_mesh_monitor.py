import argparse
import os
import time
import json
import shutil
import subprocess
from datetime import datetime


def load_system_settings(path: str) -> dict:
    """Load key=value pairs from the system settings file."""
    settings = {}
    if not os.path.isfile(path):
        return settings
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                settings[key.strip()] = value.strip()
    return settings


def wait_for_file(path: str, poll_interval: float = 5.0) -> None:
    """Wait until *path* exists."""
    print(f"Waiting for {path} ...")
    while not os.path.exists(path):
        time.sleep(poll_interval)
    print(f"Found {path}")


def create_data_folder(project_dir: str) -> str:
    """Create a Data folder in *project_dir* and copy OBJ folder."""
    data_folder = os.path.join(project_dir, 'Data')
    os.makedirs(data_folder, exist_ok=True)

    src_obj = os.path.join(project_dir, 'OBJ')
    dst_obj = os.path.join(data_folder, 'OBJ')
    if os.path.isdir(src_obj):
        print(f"Copying {src_obj} -> {dst_obj}")
        if os.path.exists(dst_obj):
            shutil.rmtree(dst_obj)
        shutil.copytree(src_obj, dst_obj)
    return data_folder


def write_project_settings(settings_path: str, data: dict, data_folder: str) -> None:
    """Write key=value pairs to *settings_path* from *data* and extras."""
    with open(settings_path, 'w', encoding='utf-8') as f:
        project_name = data.get('project_name', 'unknown')
        f.write(f"project_name={project_name}\n")
        f.write(f"source_Directory={data_folder}\n")
        for key, value in data.items():
            if key == 'project_name':
                continue
            f.write(f"{key}={value}\n")
    print(f"Wrote settings file {settings_path}")


def run_processor(ps_script: str, settings_path: str) -> None:
    """Run the Reality Mesh PowerShell script via a project-specific batch file."""
    batch_path = os.path.join(os.path.dirname(settings_path), 'RealityMeshProcess.bat')

    with open(batch_path, 'w', encoding='utf-8') as f:
        f.write(
            f'start "" powershell -executionpolicy bypass "{ps_script}" "{settings_path}" 1\n'
        )

    print(f'Created batch file {batch_path}')
    subprocess.run(batch_path, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description='Automate PhotoMesh Reality Mesh processing.')
    parser.add_argument('build_dir', help='Path to Build_1 directory to monitor')
    parser.add_argument('--system-settings', default='RealityMeshSystemSettings.txt', help='Path to system settings file')
    parser.add_argument('--ps-script', default='RealityMeshProcessor.ps1', help='Path to RealityMeshProcessor PowerShell script')
    args = parser.parse_args()

    system_settings = load_system_settings(args.system_settings)
    if system_settings:
        print('Loaded system settings:')
        for k, v in system_settings.items():
            print(f'  {k}={v}')

    json_path = os.path.join(args.build_dir, 'Output-CenterPivotOrigin.json')
    wait_for_file(json_path)

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    project_dir = os.path.dirname(json_path)
    data_folder = create_data_folder(project_dir)

    dt_str = datetime.now().strftime('%Y-%m-%d')
    project_name = data.get('project_name', 'project')
    settings_filename = f"{project_name}_build1_{dt_str}.txt"
    settings_path = os.path.join(project_dir, settings_filename)
    write_project_settings(settings_path, data, data_folder)

    run_processor(args.ps_script, settings_path)


if __name__ == '__main__':
    main()
