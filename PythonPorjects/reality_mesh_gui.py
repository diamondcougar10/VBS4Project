import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from PIL import Image, ImageTk
import threading
import os
import time
import json
import shutil
import subprocess
from datetime import datetime


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


def create_project_folder(build_dir: str, project_name: str) -> str:
    dt = datetime.now().strftime('%Y%m%d_%H%M%S')
    project_folder = os.path.join(build_dir, f"{project_name}_{dt}")
    os.makedirs(project_folder, exist_ok=True)
    data_folder = os.path.join(project_folder, 'Data')
    os.makedirs(data_folder, exist_ok=True)
    return project_folder, data_folder


def copy_obj(build_dir: str, data_folder: str):
    src = os.path.join(build_dir, 'OBJ')
    dst = os.path.join(data_folder, 'OBJ')
    if os.path.isdir(src):
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)


def write_project_settings(settings_path: str, data: dict, data_folder: str):
    with open(settings_path, 'w', encoding='utf-8') as f:
        project_name = data.get('project_name', 'project')
        f.write(f"project_name={project_name}\n")
        f.write(f"source_Directory={data_folder}\n")
        for k, v in data.items():
            if k == 'project_name':
                continue
            f.write(f"{k}={v}\n")


def run_processor(ps_script: str, settings_path: str, log_fn):
    cmd = [
        'powershell',
        '-ExecutionPolicy', 'Bypass',
        '-File', ps_script,
        settings_path,
        '1'
    ]
    log_fn('Running: ' + ' '.join(cmd))
    subprocess.run(cmd, check=True)


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
        self.geometry('620x480')

        self.logo_photo = None

        self.build_dir = tk.StringVar()
        self.system_settings = tk.StringVar(value='RealityMeshSystemSettings.txt')
        self.ps_script = tk.StringVar(value='RealityMeshProcessor.ps1')

        self.create_widgets()

    def create_widgets(self):
        row = 0

        logo_path = os.path.join(os.path.dirname(__file__), 'logos', 'STE_CFT_Logo.png')
        try:
            img = Image.open(logo_path)
            self.logo_photo = ImageTk.PhotoImage(img)
            tk.Label(self, image=self.logo_photo).grid(row=row, column=0, columnspan=3, pady=(5, 10))
            row += 1
        except Exception:
            pass

        instructions = (
            "1. Select the Build_1/out folder from PhotoMesh.\n"
            "2. Confirm the settings and script paths.\n"
            "3. Click Start to generate the terrain package."
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
        ent_settings = tk.Entry(self, textvariable=self.system_settings, width=50)
        ent_settings.grid(row=row, column=1, sticky='we')
        btn_settings = tk.Button(self, text='Browse', command=self.browse_settings)
        btn_settings.grid(row=row, column=2)
        ToolTip(lbl_settings, 'Text file containing system configuration values.')
        ToolTip(ent_settings, 'Path to RealityMeshSystemSettings.txt.')
        ToolTip(btn_settings, 'Choose the settings file.')
        row += 1

        lbl_ps = tk.Label(self, text='PowerShell Script:')
        lbl_ps.grid(row=row, column=0, sticky='w')
        ent_ps = tk.Entry(self, textvariable=self.ps_script, width=50)
        ent_ps.grid(row=row, column=1, sticky='we')
        btn_ps = tk.Button(self, text='Browse', command=self.browse_ps)
        btn_ps.grid(row=row, column=2)
        ToolTip(lbl_ps, 'RealityMeshProcessor.ps1 script used for processing.')
        ToolTip(ent_ps, 'Path to the processing PowerShell script.')
        ToolTip(btn_ps, 'Select the PowerShell script.')
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

    def start_process(self):
        if not self.build_dir.get():
            messagebox.showerror('Error', 'Please select a Build_1/out directory')
            return
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
            proj_folder, data_folder = create_project_folder(build_dir, project_name)
            self.log_msg(f'Created project folder {proj_folder}')

            copy_obj(build_dir, data_folder)
            self.log_msg('Copied OBJ files')

            settings_path = os.path.join(proj_folder, f'{project_name}.txt')
            write_project_settings(settings_path, data, data_folder)
            self.log_msg(f'Wrote settings {settings_path}')

            run_processor(self.ps_script.get(), settings_path, self.log_msg)
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
