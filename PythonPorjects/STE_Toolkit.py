import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os
import subprocess
import webbrowser
import urllib.request
import configparser
import winreg
import sys
import functools
import json
from tkinter import simpledialog

def get_vbs4_install_path() -> str:
    path = config['General'].get('vbs4_path', '')
    if not path or not os.path.isfile(path):
        path = find_executable('VBS4.exe')
        if path:
            config['General']['vbs4_path'] = path
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
    return path or ''

def find_executable(name, additional_paths=[]):
    """
    Try to find either name (e.g. 'BlueIG.exe') or its .bat sibling
    (e.g. 'BlueIG.bat') under standard paths or any additional_paths.
    """
    base, ext = os.path.splitext(name)
    # build list of candidate filenames
    candidates = [name]
    if ext.lower() == '.exe':
        candidates.append(base + '.bat')
    elif ext.lower() == '.bat':
        candidates.append(base + '.exe')

    possible_paths = [
        r"C:\BISIM\VBS4",
        r"C:\Builds\VBS4",
        r"C:\Builds"
    ] + additional_paths

    for path in possible_paths:
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for cand in candidates:
                    if cand in files:
                        return os.path.join(root, cand)
    return None

# ─── CONFIGURATION ───────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.ini')
config      = configparser.ConfigParser()
config.read(CONFIG_PATH)
if 'General' not in config:
    config['General'] = {}
if 'close_on_launch' not in config['General']:
    config['General']['close_on_launch'] = 'False'
with open(CONFIG_PATH, 'w') as f:
    config.write(f)
def load_image(path, size=None):
    img = Image.open(path)
    if size:
        img = img.resize(size, Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(img)

# ─── AUTO-LAUNCH CONFIG ──────────────────────────────────────────────────────
if 'Auto-Launch' not in config:
    config['Auto-Launch'] = {
        'enabled': 'False',
        'program_path': '',
        'arguments': ''
    }
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)

def is_auto_launch_enabled() -> bool:
    return config.getboolean('Auto-Launch', 'enabled', fallback=False)

def get_auto_launch_cmd() -> tuple[str, list[str]]:
    path = config['Auto-Launch'].get('program_path', '').strip()
    raw_args = config['Auto-Launch'].get('arguments', '').strip()
    args = raw_args.split() if raw_args else []
    return path, args



# ─── SETTINGS HELPERS ────────────────────────────────────────────────────────
def is_startup_enabled() -> bool:
    """Return True if the app is registered to launch on Windows startup."""
    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "STE_Mission_Planning_Toolkit"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False

def is_close_on_launch_enabled() -> bool:
    """Return True if the config says to close on launch."""
    return config.getboolean('General', 'close_on_launch', fallback=False)

def toggle_startup():
    """Toggle Windows startup registration for this app."""
    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "STE_Mission_Planning_Toolkit"
    if is_startup_enabled():
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        messagebox.showinfo("Settings", "Launch on startup ▶ Disabled")
    else:
        exe_path = sys.executable
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
        messagebox.showinfo("Settings", "Launch on startup ▶ Enabled")

def toggle_close_on_launch():
    """Toggle whether the main window closes when you launch a tool."""
    enabled = not is_close_on_launch_enabled()
    config['General']['close_on_launch'] = str(enabled)
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
    status = "Enabled" if enabled else "Disabled"
    messagebox.showinfo("Settings", f"Close on Software Launch? ▶ {status}")


# ─── BATCH‐FILE LAUNCH LOGIC ──────────────────────────────────────────────────
BATCH_FOLDER = os.path.join(BASE_DIR, "Autolaunch_Batchfiles")
os.makedirs(BATCH_FOLDER, exist_ok=True)
VBS4_BAT     = os.path.join(BATCH_FOLDER, "VBS4_Launch.bat")
BLUEIG_BAT   = os.path.join(BATCH_FOLDER, "BlueIg.bat")
BVI_BAT      = os.path.join(BATCH_FOLDER, "BVI_Manager.bat")

def prompt_for_exe(title: str) -> str:
    root = tk.Tk(); root.withdraw()
    path = filedialog.askopenfilename(title=title, filetypes=[("Executable","*.exe")])
    root.destroy()
    return path

def ensure_executable(config_key: str, exe_name: str, prompt_title: str) -> str:
    path = config['General'].get(config_key, '').strip()
    if not path or not os.path.isfile(path):
        if exe_name and isinstance(exe_name, str):
            if exe_name.lower() == 'vbs4.exe':
                path = get_vbs4_install_path()
            elif exe_name.lower() == 'blueig.exe':
                path = get_blueig_install_path()
            else:
                path = find_executable(exe_name)
        elif isinstance(exe_name, list):
            for name in exe_name:
                path = find_executable(name)
                if path:
                    break
    
    if not path:
        path = prompt_for_exe(prompt_title)
        if not path or not os.path.isfile(path):
            raise FileNotFoundError(f"No executable found for '{config_key}'.")
        config['General'][config_key] = path
        with open(CONFIG_PATH, 'w') as f:
            config.write(f)
    
    return path

def get_blueig_install_path() -> str:
    path = config['General'].get('blueig_path', '')
    if not path or not os.path.isfile(path):
        path = find_executable('BlueIG.exe')
        if path:
            config['General']['blueig_path'] = path
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
    return path or ''

def _write_vbs4_bat(vbs4_exe: str):
    script = f"""@echo off
"{vbs4_exe}" -admin "-autoassign=admin" -forceSimul -window
exit /b 0
"""
    with open(VBS4_BAT, "w", newline="\r\n") as f:
        f.write(script)

def _write_blueig_bat(blueig_exe: str):
    script = f"""@echo off
"{blueig_exe}" -hmd=openxr_ctr:oculus -vbsHostExerciseID=Exercise-HAMMERKIT1-1 -splitCPU -DJobThreads=8 -DJobPool=8
exit /b 0
"""
    with open(BLUEIG_BAT, "w", newline="\r\n") as f:
        f.write(script)

def create_bvi_batch_file(ares_path: str) -> str:
    """
    Write a batch file that launches Ares Manager, waits, then Ares XR.
    """
    xr_path = ares_path.replace(
        "ares.manager\\ares.manager.exe",
        "ares.xr\\Windows\\AresXR.exe"
    )
    with open(BVI_BAT, "w") as f:
        f.write(f'''@echo off
start "" "{ares_path}"
timeout /t 40 /nobreak
start "" "{xr_path}"
exit /b 0
''')
    return BVI_BAT
# ─── BATCH‐FILE WRITING ──────────────────────────────────────────────────

vbs4_exe = ensure_executable('vbs4_path', 'VBS4.exe', "Select VBS4.exe")
_write_vbs4_bat(vbs4_exe)

# BlueIG
blueig_exe = ensure_executable('blueig_path', 'BlueIG.exe', "Select BlueIG.exe")
_write_blueig_bat(blueig_exe)

# BVI (ARES Manager)
ares_exe = ensure_executable('bvi_manager_path', ['ares.manager.exe', 'ARES.Manager.exe'], "Select ARES Manager executable")
bvi_batch_file = create_bvi_batch_file(ares_exe)

def launch_vbs4():
    try:
        subprocess.Popen(["cmd.exe","/c", VBS4_BAT], cwd=BATCH_FOLDER)
        messagebox.showinfo("Launch Successful", "VBS4 has started.")
        if is_close_on_launch_enabled():
            sys.exit(0)
    except Exception as e:
        messagebox.showerror("Launch Failed", f"Couldn’t launch VBS4:\n{e}")

def launch_vbs4_setup():
    try:
        vbs4_setup_exe = ensure_executable('vbs4_setup_path', 'VBSLauncher.exe', "Select VBSLauncher.exe")
        subprocess.Popen([vbs4_setup_exe])
        messagebox.showinfo("Launch Successful", "VBS4 Setup Launcher has started.")
        if is_close_on_launch_enabled():
            sys.exit(0)
    except Exception as e:
        messagebox.showerror("Launch Failed", f"Couldn't launch VBS4 Setup Launcher:\n{e}")

def launch_blueig():
    # 1) get the saved BlueIG.exe (or ask once)
    exe = config['General'].get('blueig_path', '').strip()
    if not exe or not os.path.isfile(exe):
        messagebox.showwarning("BlueIG Not Found",
                               "Couldn't find BlueIG.exe — please locate it now.")
        exe = filedialog.askopenfilename(
            title="Select BlueIG Executable",
            filetypes=[("Executable Files", "*.exe")]
        )
        if not exe or not os.path.isfile(exe):
            messagebox.showerror("Error", "Invalid BlueIG path selected.")
            return
        config['General']['blueig_path'] = exe
        with open(CONFIG_PATH, 'w') as cfg:
            config.write(cfg)

    # 2) ask which HammerKit exercise
    n = simpledialog.askinteger(
        "Select HammerKit Scenario",
        "Choose VBS4 Hammerkit Server (1–4):",
        minvalue=1, maxvalue=4
    )
    if n is None:
        return  # user hit Cancel

    scenario = f"Exercise-HAMMERKIT1-{n}"

    # 3) rewrite the batch file
    bat_contents = f"""@echo off
"{exe}" -hmd=openxr_ctr:oculus ^
    -vbsHostExerciseID={scenario} ^
    -splitCPU ^
    -DJobThreads=8 ^
    -DJobPool=8
exit /b 0
"""
    with open(BLUEIG_BAT, "w", newline="\r\n") as bat:
        bat.write(bat_contents)

    # 4) launch it
    try:
        subprocess.Popen(["cmd.exe", "/c", BLUEIG_BAT], cwd=BATCH_FOLDER)
        messagebox.showinfo("Launch Successful",
                            f"BlueIG HammerKit 1-{n} started.")
        if is_close_on_launch_enabled():
            sys.exit(0)
    except Exception as e:
        messagebox.showerror("Launch Failed",
                             f"Couldn't launch BlueIG:\n{e}")

def launch_bvi():
    try:
        subprocess.Popen([bvi_batch_file], shell=True)
        messagebox.showinfo("Launch Successful", "BVI has started.")
        if is_close_on_launch_enabled():
            sys.exit(0)
    except Exception as e:
        messagebox.showerror("Launch Failed", f"Couldn’t launch BVI:\n{e}")

def open_bvi_terrain():
    url = "http://localhost:9080/terrain"
    try:
        urllib.request.urlopen(url, timeout=1)
        webbrowser.open(url, new=2)
    except:
        messagebox.showinfo("BVI", "Note: BVI must be running")


# ─── BACKGROUND & LOGOS ──────────────────────────────────────────────────────
background_image_path = os.path.join(BASE_DIR, "20240206_101613_026.jpg")
logo_STE_path         = os.path.join(BASE_DIR, "logos", "STE_CFT_Logo.png")
logo_AFC_army         = os.path.join(BASE_DIR, "logos", "US_Army_AFC_Logo.png")
logo_first_army       = os.path.join(BASE_DIR, "logos", "First_Army_Logo.png")
logo_us_army_path     = os.path.join(BASE_DIR, "logos", "New_US_Army_Logo.png")

def set_background(window):
    # wallpaper
    if os.path.exists(background_image_path):
        img = Image.open(background_image_path).resize((1600,800), Image.Resampling.LANCZOS)
        ph  = ImageTk.PhotoImage(img)
        lbl = tk.Label(window, image=ph)
        lbl.image = ph
        lbl.place(relwidth=1, relheight=1)

    # logos
    if not isinstance(window, (tk.Tk, tk.Toplevel)) or getattr(window, "_logos_placed", False):
        return
    window._logos_placed = True

    def place_logos():
        coords = [
            (200,  5, logo_STE_path,   (90, 90)),
            (300,  5, logo_AFC_army,   (73, 90)),
            (380,  5, logo_first_army, (60, 90)),
            (window.winfo_width()-280, 3, logo_us_army_path, (230, 86)),
        ]
        for x,y,path,(w,h) in coords:
            if os.path.exists(path):
                img   = Image.open(path).convert("RGBA").resize((w,h), Image.Resampling.LANCZOS)
                ph    = ImageTk.PhotoImage(img)
                lbl2  = tk.Label(window, image=ph, bg="black")
                lbl2.image = ph
                lbl2.place(x=x, y=y)

    window.after(100, place_logos)

def set_wallpaper(window):
    if os.path.exists(background_image_path):
        img = Image.open(background_image_path).resize((1600,800), Image.Resampling.LANCZOS)
        ph  = ImageTk.PhotoImage(img)
        lbl = tk.Label(window, image=ph)
        lbl.image = ph
        lbl.place(relwidth=1, relheight=1)

# ─── TUTORIALS PANEL DATA ────────────────────────────────────────────────────
tutorials_items = {
    "VBS4 Documentation": lambda: webbrowser.open(
        "file:///C:/BISIM/VBS4/docs/HTML_EN/Content/Core/VBS4_Manuals_Home.htm", new=2),
    "Script Wiki":         lambda: webbrowser.open(
        "file:///C:/BISIM/VBS4/docs/Wiki/SQF_Resources/VBS_Scripting_Reference.html", new=2),
    "BVI PDF Docs":        lambda: messagebox.showinfo("BVI Docs","Open BVI PDF docs"),
}
blueig_help_items = {
    "Blue IG Official Documentation": lambda: messagebox.showinfo("Coming Soon", "Not implemented yet"),
    "Video Tutorials":                lambda: messagebox.showinfo("Coming Soon", "Not implemented yet"),
    "Support Website":                lambda: webbrowser.open("https://example.com/blueig-support", new=2),
}
# ─── help MENUS ────────────────────────────
# Update the VBS4_HTML constant
VBS4_HTML = r"C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\Help_Tutorials\VBS4_Manuals_EN.htm"
SCRIPT_WIKI  = r"C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\Help_Tutorials\Wiki\SQF_Reference.html"
SUPPORT_SITE = "https://bisimulations.com/support/"
STE_SMTP_KIT_GUIDE = r"C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\STE_SMTP_KIT_GUIDE.pdf"
# ─── PDF & VIDEO SUB-MENU DATA ───────────────────────────────────────────────
pdf_docs = {
    "SQF Wiki": lambda: webbrowser.open(
        r"file:///C:/Users/tifte/Documents/GitHub/VBS4Project/PythonPorjects/Help_Tutorials/Wiki/SQF_Reference.html",
        new=2),
    "VBS4 Manuals": lambda: webbrowser.open(
        r"file:///C:/Users/tifte/Documents/GitHub/VBS4Project/PythonPorjects/Help_Tutorials/VBS4_Manuals_EN.htm",
        new=2),
}
# ─── VBS4 PDF Docs Helper ────────────────────────────────────────────────────
VBS4_PDF_DIR = r"C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\PDF_EN"

def open_vbs4_pdfs():
    """Scan the VBS4 PDF_EN folder and pop up a submenu of all the PDFs."""
    try:
        pdfs = sorted(f for f in os.listdir(VBS4_PDF_DIR) if f.lower().endswith(".pdf"))
    except FileNotFoundError:
        messagebox.showerror("Error", f"VBS4 PDF folder not found:\n{VBS4_PDF_DIR}")
        return

    items = {}
    for fname in pdfs:
        display = os.path.splitext(fname)[0].replace("_", " ")
        path    = os.path.join(VBS4_PDF_DIR, fname)
        items[display] = lambda p=path: subprocess.Popen([p], shell=True)

video_items = {
    "VBS4 Video Tutorials":   lambda: messagebox.showinfo("VBS4 Videos", "Play VBS4 tutorial videos"),
    "BlueIG Video Tutorials": lambda: messagebox.showinfo("BlueIG Videos", "Play BlueIG tutorial videos"),
    "BVI Video Tutorials":    lambda: messagebox.showinfo("BVI Videos", "Play BVI tutorial videos"),
}
vbs4_help_items = {
    "VBS4 Official Documentation": lambda: subprocess.Popen([VBS4_HTML], shell=True),
       "VBS4 PDF Manuals":   open_vbs4_pdfs,
       "STE SMTP Kit Guide":          lambda: subprocess.Popen([STE_SMTP_KIT_GUIDE], shell=True),
    "Script Wiki":                  lambda: subprocess.Popen([SCRIPT_WIKI], shell=True),
    "Video Tutorials":              lambda: messagebox.showinfo("Video Tutorials","Coming soon…"),
    "Support Website":              lambda: webbrowser.open(SUPPORT_SITE, new=2),
}
def open_bvi_quickstart():
    path = r"C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\BVI_Documentation\BVI_TECHNICAL_DOC.pdf"
    if os.path.exists(path):
        try:
            subprocess.Popen([path], shell=True)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open Quick-Start Guide:\n{e}")
    else:
        messagebox.showerror("Error", f"Quick-Start Guide not found:\n{path}")

# BVI Help submenu
bvi_help_items = {
    "BVI Official Documentation": lambda: messagebox.showinfo("BVI Docs", "Open BVI PDF docs (not hooked up)"),
    "BVI Quick-Start Guide":      open_bvi_quickstart,
    "Video Tutorials":            lambda: messagebox.showinfo("Video Tutorials","Coming soon…"),
    "Support Website":            lambda: webbrowser.open("https://www.dignitastechnologies.com/bvi", new=2),
}

# One-Click Terrain Help submenu
oct_help_items = {
    "How to collect terrain scans w/ Drone":   lambda: messagebox.showinfo("Drone Scans","Coming soon…"),
    "How to import terrain scans from drone":  lambda: messagebox.showinfo("Import Scans","Coming soon…"),
    "How to: Simulated Terrain":               lambda: messagebox.showinfo("Simulated Terrain","Coming soon…"),
}

# ─── Helper DATA ────────────────────────────────────────────────────
def get_blueig_install_path() -> str:
    """Return the currently saved BlueIG path (or empty string if none)."""
    return config['General'].get('blueig_path', '')

def set_blueig_install_path():
    """Open a file dialog to choose your BlueIG executable and save it."""
    path = filedialog.askopenfilename(
        title="Select BlueIG Executable",
        filetypes=[("Executable Files", "*.exe")]
    )
    if path and os.path.exists(path):
        config['General']['blueig_path'] = path
        with open(CONFIG_PATH, 'w') as f:
            config.write(f)
        messagebox.showinfo("Settings", f"BlueIG path set to:\n{path}")
    else:
        messagebox.showerror("Settings", "Invalid BlueIG path selected.")

# ─── Default Browser Helpers ────────────────────────────────────────────────

def get_default_browser() -> str:
    """Return the currently saved default browser executable path."""
    return config['General'].get('default_browser', '')

def set_default_browser():
    """Open file dialog to set the default browser executable path."""
    path = filedialog.askopenfilename(
        title="Select Default Browser Executable",
        filetypes=[("Executable Files", "*.exe")]
    )
    if path and os.path.exists(path):
        config['General']['default_browser'] = path
        with open(CONFIG_PATH, 'w') as f:
            config.write(f)
        messagebox.showinfo("Settings", f"Default browser set to:\n{path}")
    else:
        messagebox.showerror("Settings", "Invalid browser path selected.")

# ======================== SETUP & CONFIGURATION ========================= #

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def set_vbs4_install_path():
    """Open a file dialog to choose VBS4.exe, then save it in config.ini."""
    path = filedialog.askopenfilename(
        title="Select VBS4.exe",
        filetypes=[("Executable Files", "*.exe")]
    )
    if path and os.path.exists(path):
        config['General']['vbs4_path'] = path
        with open(CONFIG_PATH, 'w') as f:
            config.write(f)
        messagebox.showinfo("Settings", f"VBS4 path set to:\n{path}")
    else:
        messagebox.showerror("Settings", "Invalid VBS4 path selected.")

def get_ares_manager_path() -> str:
    return config['General'].get('bvi_manager_path', '')

def set_ares_manager_path():
    path = filedialog.askopenfilename(title="Select ARES Manager.exe", filetypes=[("Executable", "*.exe")])
    if path:
        config['General']['bvi_manager_path'] = path
        with open(CONFIG_PATH, 'w') as f: config.write(f)
        messagebox.showinfo("Settings", f"ARES Manager path set to:\n{path}")

# ─── One Click Terrain SETUP ──────────────────────────────────────────────────────
def one_click_terrain_converter():
    # TODO: hook this up to terrain conversion logic
    print("One-Click Terrain Converter launched…")

# ─── helper for "External Map" ────────────────────────────────────────────
def select_vbs_map_profile():
    """Prompt for a VBS Map loginName and save it to config."""
    profile = simpledialog.askstring(
        "Select User Profile",
        "Enter VBS Map loginName:"
    )
    if not profile:
        return
    cfg = config['General']
    cfg['vbs_map_user']   = profile.strip()
    # you can also set defaults if you want:
    cfg.setdefault('vbs_map_server', 'localhost')
    cfg.setdefault('vbs_map_port',   '4080')
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
    messagebox.showinfo("Settings", f"VBS Map loginName set to:\n{profile}")

def open_external_map():
    """Open the VBS Map web UI for the saved user, if server is live."""
    cfg  = config['General']
    user = cfg.get('vbs_map_user','').strip()
    if not user:
        messagebox.showwarning("External Map",
                               "No loginName set. Please select a user profile first.")
        select_vbs_map_profile()
        user = cfg.get('vbs_map_user','').strip()
        if not user:
            return

    host = cfg.get('vbs_map_server', 'localhost').strip()
    port = cfg.get('vbs_map_port',   '4080').strip()
    # build URL with both loginName and vbsFullComputerName
    url = (
        f"http://{host}:{port}/#/external/login"
        f"?loginName={user}"
        f"&vbsFullComputerName={user}"
    )

    # quick ping
    try:
        urllib.request.urlopen(f"http://{host}:{port}", timeout=1)
    except Exception:
        messagebox.showinfo("External Map",
                            "Note: VBS Map server must be running")
    else:
        webbrowser.open(url, new=2)

# ─── SINGLE‐MAIN-WINDOW SETUP ──────────────────────────────────────────────────────
class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("STE Mission Planning Toolkit")
        self.geometry("1600x800")
        self.resizable(False, False)

        set_background(self)

        nav = tk.Frame(self, width=200, bg='#333333')
        nav.pack(side='left', fill='y')
        self.content = tk.Frame(self)
        self.content.pack(side='right', expand=True, fill='both')

        self.panels = {
            'Main':      MainMenu(self.content, self),
            'VBS4':      VBS4Panel(self.content, self),
            'BVI':       BVIPanel(self.content, self),
            'Settings':  SettingsPanel(self.content, self),
            'Tutorials': TutorialsPanel(self.content, self),
        }

        for key, label in [
            ('Main',     'Home'),
            ('VBS4',     'VBS4 / BlueIG'),
            ('BVI',      'BVI'),
            ('Settings', 'Settings'),
            ('Tutorials','?'),
        ]:
            tk.Button(nav, text=label,
                      font=("Helvetica",18), bg="#555", fg="white",
                      width=12,
                      command=lambda k=key: self.show(k)
            ).pack(pady=5, padx=5)

        tk.Button(nav, text="Exit", font=("Helvetica",18),
                  bg="red", fg="white", command=self.destroy
        ).pack(fill='x', pady=20, padx=5)

        self.current = None
        self.show('Main')

    def show(self, name):
        if self.current:
            self.panels[self.current].pack_forget()
        panel = self.panels[name]
        panel.pack(expand=True, fill='both')
        self.current = name

class MainMenu(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        set_background(self)

        tk.Label(self, text="STE Mission Planning Toolkit",
                 font=("Helvetica",36,"bold"),
                 bg='black', fg='white', pady=20) \
          .pack(fill='x')

        # VBS4 Button
        self.vbs4_button = tk.Button(self, text="Launch VBS4",
                  font=("Helvetica",24), bg="#444444", fg="white",
                  width=30, height=1, command=launch_vbs4)
        self.vbs4_button.pack(pady=10)

        # BlueIG Frame for dynamic buttons
        self.blueig_frame = tk.Frame(self, bg='#333333')  # Set gray background
        self.blueig_frame.pack(pady=10)
        self.create_blueig_button()

        # Other buttons
        self.other_buttons = []
        for txt, cmd in [
            ("Launch BVI",     launch_bvi),
            ("Settings",       lambda: controller.show('Settings')),
            ("Tutorials",      lambda: controller.show('Tutorials')),
            ("Exit",           controller.destroy),
        ]:
            button = tk.Button(self, text=txt,
                      font=("Helvetica",24), bg="#444444", fg="white",
                      width=30, height=1, command=cmd)
            button.pack(pady=10)
            self.other_buttons.append(button)

    def create_blueig_button(self):
        # Clear the frame first
        for widget in self.blueig_frame.winfo_children():
            widget.destroy()

        tk.Button(self.blueig_frame, text="Launch BlueIG",
                  font=("Helvetica", 24), bg="#444444", fg="white",
                  width=30, height=1, command=self.show_scenario_buttons) \
          .pack()

    def show_scenario_buttons(self):
        # Clear the frame
        for widget in self.blueig_frame.winfo_children():
            widget.destroy()

        # Create four scenario buttons
        for i in range(1, 5):
            tk.Button(self.blueig_frame, 
                      text=f"Launch BlueIG HammerKit 1-{i}",
                      font=("Helvetica", 20), bg="#444444", fg="white",
                      width=30, height=1,
                      command=lambda n=i: self.launch_blueig_scenario(n)) \
              .pack(pady=5)

        # Add a back button
        tk.Button(self.blueig_frame, text="Back",
                  font=("Helvetica", 18), bg="#666666", fg="white",
                  width=10, command=self.create_blueig_button) \
          .pack(pady=10)

    def launch_blueig_scenario(self, scenario_num):
        # Launch BlueIG with the selected scenario
        exe = config['General'].get('blueig_path', '').strip()
        if not exe or not os.path.isfile(exe):
            messagebox.showerror("Error", "BlueIG executable not found. Please set it in the settings.")
            return

        scenario = f"Exercise-HAMMERKIT1-{scenario_num}"

        # Rewrite the batch file
        bat_contents = f"""@echo off
"{exe}" -hmd=openxr_ctr:oculus ^
    -vbsHostExerciseID={scenario} ^
    -splitCPU ^
    -DJobThreads=8 ^
    -DJobPool=8
exit /b 0
"""
        with open(BLUEIG_BAT, "w", newline="\r\n") as bat:
            bat.write(bat_contents)

        # Launch it
        try:
            subprocess.Popen(["cmd.exe", "/c", BLUEIG_BAT], cwd=BATCH_FOLDER)
            messagebox.showinfo("Launch Successful",
                                f"BlueIG HammerKit 1-{scenario_num} started.")
            if is_close_on_launch_enabled():
                sys.exit(0)
        except Exception as e:
            messagebox.showerror("Launch Failed",
                                 f"Couldn't launch BlueIG:\n{e}")

        # Revert back to the single button
        self.create_blueig_button()

class VBS4Panel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        set_wallpaper(self)

        tk.Label(self, text="VBS4 / BlueIG",
                 font=("Helvetica",36,"bold"),
                 bg='black', fg='white', pady=20)\
          .pack(fill='x')

        # existing buttons
        tk.Button(self, text="Launch VBS4",
                  font=("Helvetica",20), bg="#444", fg="white",
                  command=launch_vbs4)\
          .pack(pady=8, ipadx=10, ipady=5)

        tk.Button(self, text="VBS4 Launcher",
                  font=("Helvetica",20), bg="#444", fg="white",
                  command=launch_vbs4_setup)\
          .pack(pady=8, ipadx=10, ipady=5)

        # BlueIG frame for dynamic buttons
        self.blueig_frame = tk.Frame(self, bg='#333333')  # Set the background to gray
        self.blueig_frame.pack(pady=8)
        self.create_blueig_button()

        # ─── new One-Click Terrain Converter stub button ───────────────────────
        tk.Button(self, text="One-Click Terrain Converter",
                  font=("Helvetica",20), bg="#444", fg="white",
                  command=lambda: messagebox.showinfo(
                      "One-Click Terrain Converter",
                      "Tool coming soon…"
                  ))\
          .pack(pady=8, ipadx=10, ipady=5)

        # ─── new External Map button ───────────────────────────────────────────
        tk.Button(self, text="External Map",
                  font=("Helvetica",20), bg="#444", fg="white",
                  command=open_external_map)\
          .pack(pady=8, ipadx=10, ipady=5)

        # back to main menu
        tk.Button(self, text="Back",
                  font=("Helvetica",18), bg="red", fg="white",
                  command=lambda: controller.show('Main'))\
          .pack(pady=20)

    def create_blueig_button(self):
        tk.Button(self.blueig_frame, text="Launch BlueIG",
                  font=("Helvetica", 20), bg="#444", fg="white",
                  command=self.show_scenario_buttons)\
          .pack(ipadx=10, ipady=5)

    def show_scenario_buttons(self):
        # Clear the frame
        for widget in self.blueig_frame.winfo_children():
            widget.destroy()

        # Create four scenario buttons
        for i in range(1, 5):
            tk.Button(self.blueig_frame, 
                      text=f"HammerKit 1-{i}",
                      font=("Helvetica", 16), bg="#444", fg="white",
                      command=lambda n=i: self.launch_blueig_scenario(n))\
              .pack(side=tk.LEFT, padx=5, pady=5, ipadx=5, ipady=2)

    def launch_blueig_scenario(self, scenario_num):
        # Launch BlueIG with the selected scenario
        exe = config['General'].get('blueig_path', '').strip()
        if not exe or not os.path.isfile(exe):
            messagebox.showerror("Error", "BlueIG executable not found. Please set it in the settings.")
            return

        scenario = f"Exercise-HAMMERKIT1-{scenario_num}"

        # Rewrite the batch file
        bat_contents = f"""@echo off
"{exe}" -hmd=openxr_ctr:oculus ^
    -vbsHostExerciseID={scenario} ^
    -splitCPU ^
    -DJobThreads=8 ^
    -DJobPool=8
exit /b 0
"""
        with open(BLUEIG_BAT, "w", newline="\r\n") as bat:
            bat.write(bat_contents)

        # Launch it
        try:
            subprocess.Popen(["cmd.exe", "/c", BLUEIG_BAT], cwd=BATCH_FOLDER)
            messagebox.showinfo("Launch Successful",
                                f"BlueIG HammerKit 1-{scenario_num} started.")
            if is_close_on_launch_enabled():
                sys.exit(0)
        except Exception as e:
            messagebox.showerror("Launch Failed",
                                 f"Couldn't launch BlueIG:\n{e}")

        # Revert back to the single button
        self.create_blueig_button()

class BVIPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        set_wallpaper(self)

        tk.Label(self, text="BVI",
                 font=("Helvetica",36,"bold"),
                 bg='black', fg='white', pady=20) \
          .pack(fill='x')

        tk.Button(self, text="Launch BVI",
                  font=("Helvetica",20), bg="#444", fg="white",
                  command=launch_bvi) \
          .pack(pady=8, ipadx=10, ipady=5)

        tk.Button(self, text="Open Terrain",
                  font=("Helvetica",20), bg="#444", fg="white",
                  command=open_bvi_terrain) \
          .pack(pady=8, ipadx=10, ipady=5)

        tk.Button(self, text="Back",
                  font=("Helvetica",18), bg="red", fg="white",
                  command=lambda: controller.show('Main')) \
          .pack(pady=20)

# ─── SETTINGS PANEL ──────────────────────────────────────────────────────────
class SettingsPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        set_wallpaper(self)

        tk.Label(self, text="Settings",
                 font=("Helvetica",36,"bold"),
                 bg='black', fg='white', pady=20) \
          .pack(fill='x')

        # Launch on Startup
        self.startup_var = tk.BooleanVar(value=is_startup_enabled())
        def _on_startup_toggle():
            toggle_startup()
            self.startup_var.set(is_startup_enabled())

        tk.Checkbutton(self,
                       text="Launch on Startup",
                       variable=self.startup_var,
                       command=_on_startup_toggle,
                       font=("Helvetica",20),
                       bg="#444444", fg="white",
                       selectcolor="#444444",
                       indicatoron=True,
                       width=30, pady=5) \
          .pack(pady=8)

        # Close on Launch
        self.close_var = tk.BooleanVar(value=is_close_on_launch_enabled())
        def _on_close_toggle():
            toggle_close_on_launch()
            self.close_var.set(is_close_on_launch_enabled())

        tk.Checkbutton(self,
                       text="Close on Software Launch?",
                       variable=self.close_var,
                       command=_on_close_toggle,
                       font=("Helvetica",20),
                       bg="#444444", fg="white",
                       selectcolor="#444444",
                       indicatoron=True,
                       width=30, pady=5) \
          .pack(pady=8)

        # VBS4 Install Location
        frame_vbs4 = tk.Frame(self, bg=self["bg"])
        frame_vbs4.pack(fill="x", pady=8, padx=20)
        tk.Button(frame_vbs4, text="Set VBS4 Install Location",
                  font=("Helvetica",20), bg="#444444", fg="white",
                  command=self._on_set_vbs4) \
          .pack(side="left", ipadx=10, ipady=5)
        self.lbl_vbs4 = tk.Label(frame_vbs4,
                                 text=get_vbs4_install_path() or "[not set]",
                                 font=("Helvetica",14),
                                 bg="#222222", fg="white",
                                 anchor="w", width=50)
        self.lbl_vbs4.pack(side="left", padx=10, fill="x", expand=True)

        frame_vbs4_setup = tk.Frame(self, bg=self["bg"])
        frame_vbs4_setup.pack(fill="x", pady=8, padx=20)
        tk.Button(frame_vbs4_setup, text="Set VBS4 Setup Launcher Location",
                  font=("Helvetica",20), bg="#444444", fg="white",
                  command=self._on_set_vbs4_setup) \
          .pack(side="left", ipadx=10, ipady=5)
        self.lbl_vbs4_setup = tk.Label(frame_vbs4_setup,
                                       text=config['General'].get('vbs4_setup_path', '') or "[not set]",
                                       font=("Helvetica",14),
                                       bg="#222222", fg="white",
                                       anchor="w", width=50)
        self.lbl_vbs4_setup.pack(side="left", padx=10, fill="x", expand=True)

        # BlueIG Install Location
        frame_blueig = tk.Frame(self, bg=self["bg"])
        frame_blueig.pack(fill="x", pady=8, padx=20)
        tk.Button(frame_blueig, text="Set BlueIG Install Location",
                  font=("Helvetica",20), bg="#444444", fg="white",
                  command=self._on_set_blueig) \
          .pack(side="left", ipadx=10, ipady=5)
        self.lbl_blueig = tk.Label(frame_blueig,
                                   text=get_blueig_install_path() or "[not set]",
                                   font=("Helvetica",14),
                                   bg="#222222", fg="white",
                                   anchor="w", width=50)
        self.lbl_blueig.pack(side="left", padx=10, fill="x", expand=True)

        # ARES Manager Install Location
        frame_ares = tk.Frame(self, bg=self["bg"])
        frame_ares.pack(fill="x", pady=8, padx=20)
        tk.Button(frame_ares, text="Set ARES Manager Location",
                  font=("Helvetica",20), bg="#444444", fg="white",
                  command=self._on_set_ares) \
          .pack(side="left", ipadx=10, ipady=5)
        self.lbl_ares = tk.Label(frame_ares,
                                 text=get_ares_manager_path() or "[not set]",
                                 font=("Helvetica",14),
                                 bg="#222222", fg="white",
                                 anchor="w", width=50)
        self.lbl_ares.pack(side="left", padx=10, fill="x", expand=True)

        # Default Browser
        frame_browser = tk.Frame(self, bg=self["bg"])
        frame_browser.pack(fill="x", pady=8, padx=20)
        tk.Button(frame_browser, text="Pick Default Browser",
                  font=("Helvetica",20), bg="#444444", fg="white",
                  command=self._on_set_browser) \
          .pack(side="left", ipadx=10, ipady=5)
        self.lbl_browser = tk.Label(frame_browser,
                                    text=get_default_browser() or "[not set]",
                                    font=("Helvetica",14),
                                    bg="#222222", fg="white",
                                    anchor="w", width=50)
        self.lbl_browser.pack(side="left", padx=10, fill="x", expand=True)

        # Back
        tk.Button(self, text="Back",
                  font=("Helvetica",18), bg="red", fg="white",
                  width=30, height=1,
                  command=lambda: controller.show('Main')) \
          .pack(pady=20)

    def _on_set_vbs4(self):
        set_vbs4_install_path()
        self.lbl_vbs4.config(text=get_vbs4_install_path() or "[not set]")

    def _on_set_vbs4_setup(self):
        path = filedialog.askopenfilename(
            title="Select VBSLauncher.exe",
            filetypes=[("Executable Files", "*.exe")]
        )
        if path and os.path.exists(path):
            config['General']['vbs4_setup_path'] = path
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
            self.lbl_vbs4_setup.config(text=path)
            messagebox.showinfo("Settings", f"VBS4 Setup Launcher path set to:\n{path}")
        else:
            messagebox.showerror("Settings", "Invalid VBS4 Setup Launcher path selected.")


    def _on_set_blueig(self):
        set_blueig_install_path()
        self.lbl_blueig.config(text=get_blueig_install_path() or "[not set]")

    def _on_set_ares(self):
        set_ares_manager_path()
        self.lbl_ares.config(text=get_ares_manager_path() or "[not set]")

    def _on_set_browser(self):
        set_default_browser()
        self.lbl_browser.config(text=get_default_browser() or "[not set]")

class TutorialsPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        set_background(self)

        tk.Label(self, text="Tutorials ❓",
                 font=("Helvetica", 36, "bold"),
                 bg='black', fg='white', pady=20)\
          .pack(fill='x')

        # Create a frame to hold all button sections
        content_frame = tk.Frame(self, bg='black')
        content_frame.pack(expand=True, fill='both', padx=20, pady=20)

        # Configure grid
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=1)
        content_frame.rowconfigure(0, weight=1)
        content_frame.rowconfigure(1, weight=1)

        # VBS4 Help Section
        vbs4_frame = self._create_section(content_frame, "VBS4 Help", 0, 0)
        self._add_buttons(vbs4_frame, vbs4_help_items)

        # BVI Help Section
        bvi_frame = self._create_section(content_frame, "BVI Help", 0, 1)
        self._add_buttons(bvi_frame, bvi_help_items)

        # One-Click Terrain Help Section (Coming Soon)
        oct_frame = self._create_section(content_frame, "One-Click Terrain Help", 1, 0)
        tk.Label(oct_frame, text="Tool coming soon...",
                 font=("Helvetica", 16), bg="#333333", fg="white", pady=20)\
          .pack(expand=True)

        # Blue IG Help Section
        blueig_frame = self._create_section(content_frame, "Blue IG Help", 1, 1)
        self._add_buttons(blueig_frame, blueig_help_items)

        # Back button
        tk.Button(self, text="Back",
                  font=("Helvetica", 18), bg="red", fg="white",
                  command=lambda: controller.show('Main'))\
          .pack(pady=20)

    def _create_section(self, parent, title, row, column):
        frame = tk.Frame(parent, bg='#333333', bd=2, relief=tk.RAISED)
        frame.grid(row=row, column=column, sticky='nsew', padx=10, pady=10)
        
        tk.Label(frame, text=title,
                 font=("Helvetica", 24, "bold"),
                 bg='#333333', fg='white', pady=10)\
          .pack(fill='x')
        
        return frame

    def _add_buttons(self, parent, items):
        button_frame = tk.Frame(parent, bg='#333333')
        button_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        rows = 3
        cols = 2
        for i, (txt, cmd) in enumerate(items.items()):
            row = i // cols
            col = i % cols
            tk.Button(button_frame, text=txt,
                      font=("Helvetica", 12), bg="#444444", fg="white",
                      command=cmd, wraplength=150)\
              .grid(row=row, column=col, padx=5, pady=5, sticky='nsew')
        
        # Configure grid
        for i in range(cols):
            button_frame.columnconfigure(i, weight=1)
        for i in range(rows):
            button_frame.rowconfigure(i, weight=1)

if __name__ == "__main__":
    MainApp().mainloop()
