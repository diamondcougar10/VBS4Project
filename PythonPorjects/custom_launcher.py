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

def ensure_executable(config_key: str, defaults: list[str], prompt_title: str) -> str:
    saved = config['General'].get(config_key, '').strip()
    for candidate in [saved] + defaults:
        if candidate and os.path.isfile(candidate):
            return candidate
    selected = prompt_for_exe(prompt_title)
    if not selected or not os.path.isfile(selected):
        raise FileNotFoundError(f"No executable found for '{config_key}'.")
    config['General'][config_key] = selected
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
    return selected

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
# Prepare batch files on startup
# VBS4
vbs4_exe = ensure_executable(
    'vbs4_path',
    [
        os.path.join(os.getenv("PROGRAMFILES","C:\\Program Files"), "BISIM","VBS4","VBS4.exe"),
        os.path.join(os.getenv("PROGRAMFILES(X86)","C:\\Program Files (x86)"), "BISIM","VBS4","VBS4.exe"),
        r"C:\BISIM\VBS4\VBS4.exe"
    ],
    "Select VBS4.exe"
)
_write_vbs4_bat(vbs4_exe)

# BlueIG
blueig_exe = ensure_executable('blueig_path', [], "Select BlueIG.exe")
_write_blueig_bat(blueig_exe)

# BVI (ARES Manager)
ares_exe    = ensure_executable('bvi_manager_path', [], "Select ARES Manager executable")
bvi_batch_file = create_bvi_batch_file(ares_exe)

def launch_vbs4():
    try:
        subprocess.Popen(["cmd.exe","/c", VBS4_BAT], cwd=BATCH_FOLDER)
        messagebox.showinfo("Launch Successful", "VBS4 has started.")
        if is_close_on_launch_enabled():
            sys.exit(0)
    except Exception as e:
        messagebox.showerror("Launch Failed", f"Couldn’t launch VBS4:\n{e}")

def launch_blueig():
    try:
        subprocess.Popen(["cmd.exe","/c", BLUEIG_BAT], cwd=BATCH_FOLDER)
        messagebox.showinfo("Launch Successful", "BlueIG has started.")
        if is_close_on_launch_enabled():
            sys.exit(0)
    except Exception as e:
        messagebox.showerror("Launch Failed", f"Couldn’t launch BlueIG:\n{e}")

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
# ─── SUBMENUS ────────────────────────────
def open_submenu(title, buttons):
    sub = tk.Toplevel()
    sub.title(title)
    sub.geometry("1600x800")
    sub.transient()
    sub.grab_set()
    set_background(sub)            
    tk.Label(sub, text=title,
             font=("Helvetica",28,"bold"),
             bg='black', fg='white', pady=10).pack(fill='x')
    for txt, cmd in buttons.items():
        tk.Button(sub, text=txt, command=cmd,
                  font=("Helvetica",18), bg="#444", fg="white",
                  width=30, height=1).pack(pady=5, padx=10)
    tk.Button(sub, text="Close", command=sub.destroy,
              font=("Helvetica",16), bg="red", fg="white").pack(pady=15)
# Path constants
VBS4_HTML    = r"C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\Help_Tutorials\VBS4_Manuals_EN.htm"
SCRIPT_WIKI  = r"C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\Help_Tutorials\Wiki\SQF_Reference.html"
SUPPORT_SITE = "https://bisimulations.com/support/"
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

    open_submenu("VBS4 PDF Manuals", items)

video_items = {
    "VBS4 Video Tutorials":   lambda: messagebox.showinfo("VBS4 Videos", "Play VBS4 tutorial videos"),
    "BlueIG Video Tutorials": lambda: messagebox.showinfo("BlueIG Videos", "Play BlueIG tutorial videos"),
    "BVI Video Tutorials":    lambda: messagebox.showinfo("BVI Videos", "Play BVI tutorial videos"),
}
vbs4_help_items = {
    "VBS4 Official Documentation": lambda: subprocess.Popen([VBS4_HTML], shell=True),
       "VBS4 PDF Manuals":   open_vbs4_pdfs,
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

def get_vbs4_install_path() -> str:
    """Return the currently saved VBS4 path (or empty string if none)."""
    return config['General'].get('vbs4_path', '')

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
def select_user_profile(parent):
    """
    1) Ask the user to pick their UserConfiguration.json
    2) Parse out all the loginName entries
    3) Prompt them to choose one from a dropdown
    4) (Placeholder) launch the external map for that profile
    """
    # 1) Let the user pick the JSON (defaults to your Map\External folder)
    default_dir = os.path.expanduser(r"~/Documents/VBS4/Map/External")
    cfg_path = filedialog.askopenfilename(
        title="Select UserConfiguration.json",
        initialdir=default_dir,
        filetypes=[("JSON Files", "*.json")],
        parent=parent
    )
    if not cfg_path:
        return

    # 2) Load and extract all loginName entries
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        users = data if isinstance(data, list) else data.get("Users", [])
        names = [u["loginName"] for u in users if "loginName" in u]
    except Exception as e:
        messagebox.showerror(
            "Error",
            f"Failed to read JSON:\n{e}",
            parent=parent
        )
        return

    if not names:
        messagebox.showinfo(
            "No Profiles",
            "No loginName entries found in that file.",
            parent=parent
        )
        return

    # 3) Ask the user to pick one
    choice = simpledialog.askstring(
        "Select Profile",
        "Available profiles:\n\n" + "\n".join(names) + "\n\nEnter one exactly:",
        parent=parent
    )
    if not choice or choice not in names:
        messagebox.showwarning(
            "Invalid Selection",
            "You must enter one of the listed loginNames.",
            parent=parent
        )
        return

    # 4) Launch the external map (placeholder)
    messagebox.showinfo(
        "External Map",
        f"Opening External Map for '{choice}' …\n\n"
        "— your real launch logic goes here —",
        parent=parent
    )

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

        for txt, cmd in [
            ("Launch VBS4",    launch_vbs4),
            ("Launch BlueIG",  launch_blueig),
            ("Launch BVI",     launch_bvi),
            ("Settings",       lambda: controller.show('Settings')),
            ("Tutorials",      lambda: controller.show('Tutorials')),
            ("Exit",           controller.destroy),
        ]:
            tk.Button(self, text=txt,
                      font=("Helvetica",24), bg="#444444", fg="white",
                      width=30, height=1, command=cmd) \
              .pack(pady=10)

# ─── Pannel Classes for each selected menu ──────────────────────────────────────────────────────
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

        tk.Button(self, text="Launch BlueIG",
                  font=("Helvetica",20), bg="#444", fg="white",
                  command=launch_blueig)\
          .pack(pady=8, ipadx=10, ipady=5)

        # ─── new One-Click Terrain Converter stub button ───────────────────────
        tk.Button(self, text="One-Click Terrain Converter",
                  font=("Helvetica",20), bg="#444", fg="white",
                  command=lambda: messagebox.showinfo(
                      "One-Click Terrain Converter",
                      "Tool coming soon…"
                  ))\
          .pack(pady=8, ipadx=10, ipady=5)

        # ─── new External Map button ───────────────────────────────────────────
        tk.Button(self,
                  text="External Map",
                  font=("Helvetica",20), bg="#444", fg="white",
                  command=lambda: select_user_profile(self)
        ).pack(pady=8, ipadx=10, ipady=5)

        # back to main menu
        tk.Button(self, text="Back",
                  font=("Helvetica",18), bg="red", fg="white",
                  command=lambda: controller.show('Main'))\
          .pack(pady=20)

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

    def _on_set_blueig(self):
        set_blueig_install_path()
        self.lbl_blueig.config(text=get_blueig_install_path() or "[not set]")

    def _on_set_ares(self):
        set_ares_manager_path()
        self.lbl_ares.config(text=get_ares_manager_path() or "[not set]")

    def _on_set_browser(self):
        set_default_browser()
        self.lbl_browser.config(text=get_default_browser() or "[not set]")

# ─── ? menu config pannel ──────────────────────────────────────────────────────
class TutorialsPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        set_background(self)

        tk.Label(self, text="Tutorials ❓",
                 font=("Helvetica",36,"bold"),
                 bg='black', fg='white', pady=20)\
          .pack(fill='x')

        # top-level buttons:
        specs = [
            ("VBS4 Help",            lambda: open_submenu("VBS4 Help", vbs4_help_items)),
            ("BVI Help",             lambda: open_submenu("BVI Help", bvi_help_items)),
            ("One-Click Terrain Help", lambda: open_submenu("Terrain Help", oct_help_items)),
            ("Blue IG Help",         lambda: open_submenu("Blue IG Help", blueig_help_items)),
            ("Back",                 lambda: controller.show('Main')),
        ]

        for txt, cmd in specs:
            tk.Button(self, text=txt,
                      font=("Helvetica",20), bg="#444444", fg="white",
                      width=30, height=1, command=cmd)\
              .pack(pady=8)

if __name__ == "__main__":
    MainApp().mainloop()
