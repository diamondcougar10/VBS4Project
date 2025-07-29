import os
import shutil
import subprocess
import json
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def create_project_structure(project_name: str, base_folder: str) -> tuple[str, str]:
    """Create a timestamped project directory under *base_folder*.

    Returns the project folder path and its data subfolder. If the project
    folder already exists, it is reused.
    """
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    project_folder = os.path.join(base_folder, f"{project_name}_{ts}")
    data_folder = os.path.join(project_folder, 'data')
    os.makedirs(data_folder, exist_ok=True)
    return project_folder, data_folder


def copy_obj_folder(src_obj: str, data_folder: str) -> str:
    """Copy *src_obj* directory into *data_folder* as 'OBJ'."""
    dest = os.path.join(data_folder, 'OBJ')
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(src_obj, dest)
    return dest


def parse_centerpivot_json(json_path: str, project_name: str) -> dict:
    """Parse Output-CenterPivotOrigin.json and return offset info."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    origin = data.get('Origin', [0, 0, 0])
    wkt = data.get('WKT') or data.get('UTM', '')
    return {
        'project_name': project_name,
        'offset_x': origin[0],
        'offset_y': origin[1],
        'offset_z': origin[2],
        'offset_coordsys': wkt,
    }


def create_settings_file(info: dict, project_folder: str) -> str:
    r"""Write the Reality Mesh settings file using *info*.

    A matching folder is created under ``C:\BiSim OneClick\Datasets`` and used
    for both the ``source_Directory`` value and a ``[BiSimOneClickPath]``
    section.
    """
    # Name the settings file using the conventional "<project>-settings.txt"
    settings_path = os.path.join(project_folder, f"{info['project_name']}-settings.txt")
    dataset_root = os.path.join('C:\\BiSim OneClick\\Datasets', info['project_name'])
    dataset_data = os.path.join(dataset_root, 'data')
    os.makedirs(dataset_data, exist_ok=True)

    lines = [
        f"project_name={info['project_name']}",
        f"source_Directory={dataset_data}",
        f"offset_coordsys={info.get('offset_coordsys', '')}",
        "offset_hdatum=WGS84",
        "offset_vdatum=WGS84_ellipsoid",
        f"offset_x={info['offset_x']}",
        f"offset_y={info['offset_y']}",
        f"offset_z={info['offset_z']}",
        "orthocam_Resolution=0.05",
        "orthocam_Render_Lowest=1",
        "",
        "[BiSimOneClickPath]",
        f"path={dataset_data}",
    ]

    with open(settings_path, 'w', encoding='utf-8') as f:
        for line in lines:
            f.write(line + '\n')
    return settings_path


def run_powershell(ps_script: str, settings_file: str) -> None:
    cmd = [
        'powershell',
        '-ExecutionPolicy', 'Bypass',
        '-File', ps_script,
        settings_file,
        '1',
    ]
    print('Running:', ' '.join(cmd))
    subprocess.run(cmd, check=True)
    subprocess.run(['taskkill', '/IM', 'Fuser.exe', '/F'])


def distribute_to_installs(result_folder: str) -> None:
    """Copy *result_folder* to VBS4 installs listed in distribution_paths.json."""
    dist_file = os.path.join(BASE_DIR, 'distribution_paths.json')
    if not os.path.isfile(dist_file):
        return
    with open(dist_file, 'r', encoding='utf-8') as f:
        paths = json.load(f).get('paths', [])

    for path in paths:
        dest = os.path.join(path, os.path.basename(result_folder))
        try:
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.copytree(result_folder, dest)
            print('Copied result to', dest)
        except Exception as e:
            print('Failed to copy to', dest, ':', e)
