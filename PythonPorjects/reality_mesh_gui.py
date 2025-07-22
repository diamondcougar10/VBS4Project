import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
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


class RealityMeshGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Reality Mesh Post-Process')
        self.geometry('600x400')

        self.build_dir = tk.StringVar()
        self.system_settings = tk.StringVar(value='RealityMeshSystemSettings.txt')
        self.ps_script = tk.StringVar(value='RealityMeshProcessor.ps1')

        self.create_widgets()

    def create_widgets(self):
        row = 0
        tk.Label(self, text='Build_1/out Directory:').grid(row=row, column=0, sticky='w')
        tk.Entry(self, textvariable=self.build_dir, width=50).grid(row=row, column=1, sticky='we')
        tk.Button(self, text='Browse', command=self.browse_build).grid(row=row, column=2)
        row += 1

        tk.Label(self, text='System Settings File:').grid(row=row, column=0, sticky='w')
        tk.Entry(self, textvariable=self.system_settings, width=50).grid(row=row, column=1, sticky='we')
        tk.Button(self, text='Browse', command=self.browse_settings).grid(row=row, column=2)
        row += 1

        tk.Label(self, text='PowerShell Script:').grid(row=row, column=0, sticky='w')
        tk.Entry(self, textvariable=self.ps_script, width=50).grid(row=row, column=1, sticky='we')
        tk.Button(self, text='Browse', command=self.browse_ps).grid(row=row, column=2)
        row += 1

        tk.Button(self, text='Start', command=self.start_process).grid(row=row, column=0, pady=10)
        tk.Button(self, text='Quit', command=self.destroy).grid(row=row, column=1)
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
