import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from PIL import Image, ImageTk
import threading
import os
import time
import json
import shutil
import subprocess
from datetime import datetime
import re
from collections import OrderedDict


def load_system_settings(path: str) -> dict:
    settings = {}
    if os.path.isfile(path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                settings[key.strip()] = value.strip()
    return settings


def wait_for_file(path: str, poll_interval: float = 5.0):
    while not os.path.exists(path):
        time.sleep(poll_interval)


def create_project_folder(build_dir: str, project_name: str, dataset_root: str | None = None) -> str:
    """Create the project directory structure.

    A folder named ``<project_name>_<timestamp>`` is created under
    ``dataset_root`` when provided or ``build_dir`` otherwise.  The folder
    always contains a ``data`` subdirectory.
    """

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    base = dataset_root if dataset_root else build_dir
    if base:
        os.makedirs(base, exist_ok=True)
    project_folder = os.path.join(base, f"{project_name}_{ts}")

    os.makedirs(project_folder, exist_ok=True)
    data_folder = os.path.join(project_folder, 'data')
    os.makedirs(data_folder, exist_ok=True)
    return project_folder, data_folder


def copy_tiles(build_dir: str, data_folder: str):
    """Copy raw tile data from *build_dir* into *data_folder*."""
    for name in ('Tiles', 'OBJ'):
        src = os.path.join(build_dir, name)
        if os.path.isdir(src):
            dst = os.path.join(data_folder, name)
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            break


def _parse_offset_coordsys(wkt: str) -> str:
    """Return formatted offset coordinate system string from *wkt*."""
    zone = ''
    hemi = ''
    m = re.search(r"UTM zone\s*(\d+),\s*(Northern|Southern)", wkt)
    if m:
        zone = m.group(1)
        hemi = 'N' if m.group(2).startswith('Northern') else 'S'
    return f"UTM zone:{zone} hemi:{hemi} horiz_units:Meters vert_units:Meters"


def write_project_settings(settings_path: str, data: dict, data_folder: str):
    """Write the Reality Mesh settings file.

    ``data_folder`` is ensured and used for ``source_Directory``.  The same
    location is stored under a ``[BiSimOneClickPath]`` section.
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

    project_name = data.get('project_name', 'project')
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


def extract_progress(line: str) -> int | None:
    """Return progress percent from a log line if present."""
    if "Progress:" in line:
        m = re.search(r"Progress:\s*(\d+)%", line)
        if m:
            return int(m.group(1))
    m = re.search(r"Tile\s+(\d+)\s+of\s+(\d+)", line)
    if m:
        done, total = map(int, m.groups())
        if total:
            return int(done / total * 100)
    return None


def run_processor(ps_script: str, settings_path: str, log_fn, progress_cb):
    cmd = [
        'powershell',
        '-ExecutionPolicy', 'Bypass',
        '-File', ps_script,
        settings_path,
        '1'
    ]
    log_fn('Running: ' + ' '.join(cmd))
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as proc:
        for line in proc.stdout:
            line = line.rstrip()
            log_fn(line)
            percent = extract_progress(line)
            if percent is not None:
                progress_cb(percent)
        proc.wait()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)


def kill_fusers():
    exe = 'Fuser.exe'
    if os.name == 'nt':
        subprocess.run(['taskkill', '/IM', exe, '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class ToolTip:
    """Simple tooltip for Tkinter widgets."""

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        if self.tip_window or not self.text:
            return
        x, y, _, _ = self.widget.bbox("insert") or (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID,
                         borderwidth=1, font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hide(self, _=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class RealityMeshGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Reality Mesh Post-Process')
        self.geometry('600x600')

        self.logo_photo = None

        self.build_dir = tk.StringVar()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        photomesh_dir = os.path.join(base_dir, 'photomesh')

        self.system_settings = tk.StringVar(
            value=os.path.join(photomesh_dir, 'RealityMeshSystemSettings.txt')
        )
        self.ps_script = tk.StringVar(
            value=os.path.join(photomesh_dir, 'RealityMeshProcess.ps1')
        )

        self.create_widgets()

    def create_widgets(self):
        row = 0
        instructions = (
            "1. Select the Build_1/out folder from PhotoMesh.\n"
            "2. Click Start to generate the terrain package."
        )
        tk.Label(self, text=instructions, justify='left').grid(row=row, column=0, columnspan=3, sticky='w', padx=5)
        row += 1

        lbl_build = tk.Label(self, text='Build_1/out Directory:')
        lbl_build.grid(row=row, column=0, sticky='w')
        ent_build = tk.Entry(self, textvariable=self.build_dir, width=50)
        ent_build.grid(row=row, column=1, sticky='we')
        btn_build = tk.Button(self, text='Browse', command=self.browse_build)
        btn_build.grid(row=row, column=2)
        ToolTip(lbl_build, 'Folder that contains the OBJ output from PhotoMesh (Build_1/out).')
        ToolTip(ent_build, 'Path to Build_1/out directory.')
        ToolTip(btn_build, 'Locate the Build_1/out folder.')
        row += 1

        lbl_settings = tk.Label(self, text='System Settings File:')
        lbl_settings.grid(row=row, column=0, sticky='w')
        ent_settings = tk.Entry(self, textvariable=self.system_settings, width=50, state='readonly')
        ent_settings.grid(row=row, column=1, sticky='we')
        ToolTip(lbl_settings, 'Text file containing system configuration values.')
        ToolTip(ent_settings, 'Path to RealityMeshSystemSettings.txt.')
        row += 1

        lbl_ps = tk.Label(self, text='PowerShell Script:')
        lbl_ps.grid(row=row, column=0, sticky='w')
        ent_ps = tk.Entry(self, textvariable=self.ps_script, width=50, state='readonly')
        ent_ps.grid(row=row, column=1, sticky='we')
        ToolTip(lbl_ps, 'RealityMeshProcess.ps1 script used for processing.')
        ToolTip(ent_ps, 'Path to the processing PowerShell script.')
        row += 1

        btn_start = tk.Button(self, text='Start', command=self.start_process)
        btn_start.grid(row=row, column=0, pady=10)
        ToolTip(btn_start, 'Begin processing the selected project.')
        btn_quit = tk.Button(self, text='Quit', command=self.destroy)
        btn_quit.grid(row=row, column=1)
        ToolTip(btn_quit, 'Close the application.')
        row += 1

        self.log = scrolledtext.ScrolledText(self, width=70, height=15)
        self.log.grid(row=row, column=0, columnspan=3, pady=5)
        row += 1

        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(self, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=row, column=0, columnspan=3, sticky='we', padx=5)
        row += 1
        self.progress_label = tk.Label(self, text='0%')
        self.progress_label.grid(row=row, column=0, columnspan=3, sticky='e', padx=5)

    def browse_build(self):
        path = filedialog.askdirectory()
        if path:
            self.build_dir.set(path)

    def browse_settings(self):
        path = filedialog.askopenfilename(filetypes=[('Text Files','*.txt'), ('All Files','*.*')])
        if path:
            self.system_settings.set(path)

    def browse_ps(self):
        path = filedialog.askopenfilename(filetypes=[('PowerShell','*.ps1'), ('All Files','*.*')])
        if path:
            self.ps_script.set(path)

    def log_msg(self, msg):
        self.log.insert(tk.END, msg + '\n')
        self.log.see(tk.END)

    def set_progress(self, value: int):
        self.progress_var.set(value)
        self.progress_label.config(text=f"{value}%")
        self.update_idletasks()

    def start_process(self):
        if not self.build_dir.get():
            messagebox.showerror('Error', 'Please select a Build_1/out directory')
            return
        self.set_progress(0)
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        try:
            build_dir = self.build_dir.get()
            json_path = os.path.join(build_dir, 'Output-CenterPivotOrigin.json')
            self.log_msg(f'Waiting for {json_path}')
            wait_for_file(json_path)
            self.log_msg('JSON found')

            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            project_name = data.get('project_name', 'project')

            settings = load_system_settings(self.system_settings.get())
            dataset_root = settings.get('dataset_root')
            proj_folder, data_folder = create_project_folder(build_dir, project_name, dataset_root)
            self.log_msg(f'Created project folder {proj_folder}')

            copy_tiles(build_dir, data_folder)
            self.log_msg('Copied raw tiles')

            settings_path = os.path.join(proj_folder, f'{project_name}.txt')
            write_project_settings(settings_path, data, data_folder)
            self.log_msg(f'Wrote settings {settings_path}')

            run_processor(
                self.ps_script.get(),
                settings_path,
                self.log_msg,
                lambda p: self.after(0, self.set_progress, p)
            )
            self.log_msg('Processing complete')

            kill_fusers()
            self.log_msg('PhotoMesh fusers closed')
            messagebox.showinfo('Done', 'Processing finished successfully')
        except Exception as e:
            messagebox.showerror('Error', str(e))
            self.log_msg(f'Error: {e}')


def main():
    app = RealityMeshGUI()
    app.mainloop()


if __name__ == '__main__':
    main()
