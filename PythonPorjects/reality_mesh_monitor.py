import argparse
import os
import time
import json
import shutil
import subprocess
from datetime import datetime
from collections import OrderedDict


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
    """Create a data folder in *project_dir* and copy raw tiles."""
    data_folder = os.path.join(project_dir, 'data')
    os.makedirs(data_folder, exist_ok=True)

    for name in ('Tiles', 'OBJ'):
        src = os.path.join(project_dir, name)
        dst = os.path.join(data_folder, name)
        if os.path.isdir(src):
            print(f"Copying {src} -> {dst}")
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            break
    return data_folder


def _parse_offset_coordsys(wkt: str) -> str:
    zone = ''
    hemi = ''
    m = re.search(r"UTM zone\s*(\d+),\s*(Northern|Southern)", wkt)
    if m:
        zone = m.group(1)
        hemi = 'N' if m.group(2).startswith('Northern') else 'S'
    return f"UTM zone:{zone} hemi:{hemi} horiz_units:Meters vert_units:Meters"


def write_project_settings(settings_path: str, data: dict, data_folder: str) -> None:
    """Write settings for Reality Mesh processing.

    Ensures ``data_folder`` exists and sets it as ``source_Directory`` while
    also adding a ``[BiSimOneClickPath]`` section.
    """

    defaults = OrderedDict([
        ("orthocam_Resolution", "0.05"),
        ("orthocam_Render_Lowest", "1"),
        ("tin_to_dem_Resolution", "0.5"),
        ("sel_Area_Size", "0.5"),
        ("tile_scheme", "/Tile_%d_%d_L%d"),
        ("collision", "true"),
        ("visualLODs", "true"),
        ("project_vdatum", "WGS84_ellipsoid"),
        ("offset_models", "-0.2"),
        ("csf_options", "2 0.5 false 0.65 2 500"),
        ("faceThresh", "500"),
        ("lodThresh", "5"),
        ("tileSize", "100"),
        ("srfResolution", "0.5"),
    ])

    project_name = data.get('project_name', 'unknown')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    origin = data.get('Origin', [0, 0, 0])
    wkt = data.get('WKT', '')

    settings = OrderedDict()
    settings['project_name'] = f"{project_name} ({timestamp})"
    os.makedirs(data_folder, exist_ok=True)
    settings['source_Directory'] = data_folder
    settings['offset_coordsys'] = _parse_offset_coordsys(wkt) + '(centerpointoforigin)'
    settings['offset_hdatum'] = 'WGS84'
    settings['offset_vdatum'] = 'WGS84_ellipsoid'
    settings['offset_x'] = f"{origin[0]}(centerpointoforigin)"
    settings['offset_y'] = f"{origin[1]}(centerpointoforigin)"
    settings['offset_z'] = f"{origin[2]}(centerpointoforigin)"
    settings.update(defaults)

    with open(settings_path, 'w', encoding='utf-8') as f:
        for key, value in settings.items():
            f.write(f"{key}={value}\n")
        f.write("\n[BiSimOneClickPath]\n")
        f.write(f"path={data_folder}\n")
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
