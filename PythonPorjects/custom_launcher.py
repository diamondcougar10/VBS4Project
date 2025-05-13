import sys
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import subprocess
import os
from PIL import Image, ImageTk

# ======================== 📌 SETUP & CONFIGURATION ========================= #

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ======================== 📌 Path & File Locations ========================= #

logo_STE_path       = os.path.join(BASE_DIR, "logos", "STE_CFT_Logo.png")
logo_us_army_path   = os.path.join(BASE_DIR, "logos", "New_US_Army_Logo.png")
logo_first_army     = os.path.join(BASE_DIR, "logos", "First_Army_Logo.png")
logo_AFC_army       = os.path.join(BASE_DIR, "logos", "US_Army_AFC_Logo.png")

background_image_path = os.path.join(BASE_DIR, "20240206_101613_026.jpg")
PDF_FILE_PATH         = os.path.join(BASE_DIR, "STE_SMTP_KIT_GUIDE.pdf")
bvi_setup_doc_path    = os.path.join(BASE_DIR, "Help_Tutorials", "Bvi_Vbs4_Setup.pdf")
demo_video_path       = os.path.join(BASE_DIR, "Help_Tutorials", "BattleSpaceSetup.mkv")

BATCH_FOLDER = os.path.join(BASE_DIR, "Autolaunch_Batchfiles")
if not os.path.exists(BATCH_FOLDER):
    os.makedirs(BATCH_FOLDER)

# ======================== 📌 HELP & DEMO FUNCTIONS ========================= #

def open_bvi_setup_doc():
    if os.path.exists(bvi_setup_doc_path):
        try: subprocess.Popen([bvi_setup_doc_path], shell=True)
        except Exception as e: messagebox.showerror("Error", f"Failed to open BVI doc.\n{e}")
    else:
        messagebox.showerror("Error", "BVI VBS4 Setup document not found.")

def play_demo_video():
    if os.path.exists(demo_video_path):
        try: subprocess.Popen([demo_video_path], shell=True)
        except Exception as e: messagebox.showerror("Error", f"Failed to play demo video.\n{e}")
    else:
        messagebox.showerror("Error", "Demo video not found.")

# ======================== 📌 REUSABLE BUTTON FUNCTION ========================= #

def create_button(parent, text, command):
    return tk.Button(parent, text=text, command=command,
                     font=("Helvetica", 24), bg="#444444", fg="white",
                     width=30, height=1, relief="raised")

# ======================== 📌 INSTALL‑PATH FINDERS ========================= #

def open_setup_documentation():
    if os.path.exists(PDF_FILE_PATH):
        try: subprocess.Popen([PDF_FILE_PATH], shell=True)
        except Exception as e: messagebox.showerror("Error", f"Failed to open setup doc.\n{e}")
    else:
        messagebox.showerror("Error", "Setup documentation not found.")

def find_vbs4():
    paths = [
        os.path.join(os.getenv("PROGRAMFILES","C:\\Program Files"), "BISIM","VBS4","VBS4.exe"),
        os.path.join(os.getenv("PROGRAMFILES(X86)","C:\\Program Files (x86)"), "BISIM","VBS4","VBS4.exe"),
        r"C:\BISIM\VBS4\VBS4.exe"
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    messagebox.showwarning("VBS4 Not Found", "Select VBS4.exe manually.")
    f = filedialog.askopenfilename(title="Select VBS4.exe", filetypes=[("EXE","*.exe")])
    return f if os.path.exists(f) else None

def find_ares():
    paths = [
        os.path.join(os.getenv("PROGRAMFILES","C:\\Program Files"), "ARES","ARES-dev-release-v0.9.4-c1d3950","ares.manager","ares.manager.exe"),
        os.path.join(os.getenv("PROGRAMFILES(X86)","C:\\Program Files (x86)"), "ARES","ARES-dev-release-v0.9.4-c1d3950","ares.manager","ares.manager.exe")
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    messagebox.showwarning("ARES Not Found", "Select ares.manager.exe manually.")
    f = filedialog.askopenfilename(title="Select ARES Manager", filetypes=[("EXE","*.exe")])
    return f if os.path.exists(f) else None

vbs4_exe_path     = find_vbs4()
ares_manager_path = find_ares()
if not vbs4_exe_path or not ares_manager_path:
    messagebox.showerror("Error", "Required paths not found. Exiting.")
    sys.exit()

# ======================== 📌 BATCH FILE GENERATORS ========================= #

def create_batch_files(vbs4_path):
    host = os.path.join(BATCH_FOLDER, "Host_Launch.bat")
    user = os.path.join(BATCH_FOLDER, "User_Launch.bat")
    with open(host, "w") as f:
        f.write(f'@echo off\n"{vbs4_path}" -admin "-autoassign=admin" -forceSimul -window\nexit')
    with open(user, "w") as f:
        f.write(f'@echo off\n"{vbs4_path}" -forceSimul -window\nexit')
    return host, user

batch_files = create_batch_files(vbs4_exe_path)

def create_drone_scenario_batch(vbs4_path):
    fpath = os.path.join(BATCH_FOLDER, "DroneScenario.bat")
    with open(fpath, "w") as f:
        f.write(f'''@echo off
start "" "{vbs4_path}" -forceSimul -init=hostMission["Leonidas_demo"] -name=Admin -autoassign=Player1 -autostart=1
exit
''')
    return fpath

drone_scenario_batch = create_drone_scenario_batch(vbs4_exe_path)

def create_bvi_batch_file(ares_path):
    out = os.path.join(BATCH_FOLDER, "BVI_Manager.bat")
    xr  = ares_path.replace("ares.manager\\ares.manager.exe","ares.xr\\Windows\\AresXR.exe")
    with open(out, "w") as f:
        f.write(f'''@echo off
start "" "{ares_path}"
timeout /t 40 /nobreak
start "" "{xr}"
exit
''')
    return out

bvi_batch_file = create_bvi_batch_file(ares_manager_path)

# ======================== 📌 LAUNCH HELPERS ========================= #

def launch_application(app_path, app_name):
    if os.path.exists(app_path):
        try:
            root.destroy()
            subprocess.Popen(app_path, shell=True)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch {app_name}.\n{e}")
    else:
        messagebox.showerror("Error", f"{app_name} not found.")

def launch_bvi():
    launch_application(bvi_batch_file, "BVI (ARES Manager & XR)")

# ======================== 📌 FUNCTION TO SET BACKGROUND IMAGE ========================= #
def set_background(window):
    """Applies background image and adds four logos:
    - STE_CFT Logo (Top Left)
    - US Army AFC Logo (Next to STE_CFT Logo)
    - First Army Logo (Next to AFC Logo)
    - US Army Logo (Top Right)
    """
    try:
        # ✅ Load and set background image
        if os.path.exists(background_image_path):
            bg_image = Image.open(background_image_path)
            bg_image = bg_image.resize((1600, 800), Image.Resampling.LANCZOS)
            bg_photo = ImageTk.PhotoImage(bg_image)

            bg_label = tk.Label(window, image=bg_photo)
            bg_label.image = bg_photo  # Prevent garbage collection
            bg_label.place(relwidth=1, relheight=1)  # Stretch image to fit window
        else:
            print("❌ Background image not found!")

        # ✅ Function to place all logos after the window fully renders
        def place_logos():
            # ✅ Top Left Logo: STE_CFT_Logo
            if os.path.exists(logo_STE_path):
                ste_cft_logo_image = Image.open(logo_STE_path).convert("RGBA")  
                ste_cft_logo_image = ste_cft_logo_image.resize((90, 90), Image.Resampling.LANCZOS)

                ste_cft_logo_photo = ImageTk.PhotoImage(ste_cft_logo_image)

                ste_cft_logo_label = tk.Label(window, image=ste_cft_logo_photo, bg="black")  
                ste_cft_logo_label.image = ste_cft_logo_photo  
                ste_cft_logo_label.place(x=1, y=1)  # ✅ Positioned at Top Left
            else:
                print("❌ STE_CFT Logo image not found!")

            # ✅ Top Left (Next to STE_CFT Logo): US_Army_AFC_Logo
            if os.path.exists(logo_AFC_army):
                afc_army_logo_image = Image.open(logo_AFC_army).convert("RGBA")  
                afc_army_logo_image = afc_army_logo_image.resize((73, 95), Image.Resampling.LANCZOS)  # ✅ Resized proportionally

                afc_army_logo_photo = ImageTk.PhotoImage(afc_army_logo_image)

                afc_army_logo_label = tk.Label(window, image=afc_army_logo_photo, bg="black")  
                afc_army_logo_label.image = afc_army_logo_photo  
                
                # ✅ Position Next to STE_CFT Logo
                afc_army_logo_label.place(x=180, y=1)  # ✅ Positioned Right of STE_CFT Logo

            else:
                print("❌ US Army AFC Logo image not found!")

            # ✅ Top Left (Next to US Army AFC Logo): First_Army_Logo
            if os.path.exists(logo_first_army):
                first_army_logo_image = Image.open(logo_first_army).convert("RGBA")  
                first_army_logo_image = first_army_logo_image.resize((60, 90), Image.Resampling.LANCZOS)  # ✅ Resize proportionally

                first_army_logo_photo = ImageTk.PhotoImage(first_army_logo_image)

                first_army_logo_label = tk.Label(window, image=first_army_logo_photo, bg="black")  
                first_army_logo_label.image = first_army_logo_photo  
                
                # ✅ Position Next to US Army AFC Logo
                def position_first_army_logo():
                    first_army_logo_label.place(x=window.winfo_width() - 380, y=1)  # ✅ Positioned Right of AFC Logo

                window.after(10, position_first_army_logo)  # ✅ Delay to get correct position

            else:
                print("❌ First Army Logo image not found!")

            # ✅ Top Right Logo: New_US_Army_Logo
            if os.path.exists(logo_us_army_path):
                us_army_logo_image = Image.open(logo_us_army_path).convert("RGBA")  
                us_army_logo_image = us_army_logo_image.resize((230, 86), Image.Resampling.LANCZOS)

                us_army_logo_photo = ImageTk.PhotoImage(us_army_logo_image)

                us_army_logo_label = tk.Label(window, image=us_army_logo_photo, bg="black")  
                us_army_logo_label.image = us_army_logo_photo  
                
                # ✅ Adjusted for submenus using `.after()` to get correct width
                def position_us_army_logo():
                    us_army_logo_label.place(x=window.winfo_width() - 250, y=3)  # ✅ Positioned at Top Right

                window.after(10, position_us_army_logo)  # ✅ Delay to get correct width

            else:
                print("❌ New US Army Logo image not found!")

        # ✅ Delay placing the logos until the window fully renders
        window.after(100, place_logos)

    except Exception as e:
        messagebox.showerror("Error", f"Failed to load images.\n{e}")

# ======================== 📌 SUBMENU LOGIC ========================= #

def open_submenu(title, buttons):
    submenu = tk.Toplevel(root)
    submenu.title(title)
    submenu.geometry("1600x800")
    submenu.resizable(False, False)
    submenu.configure(bg=root["bg"])
    submenu.attributes('-transparentcolor', submenu["bg"])
    set_background(submenu)

    header = tk.Label(submenu, text=title, font=("Helvetica",36,"bold"),
                      bg="black", fg="white", pady=20)
    header.pack(fill="x")

    for txt, cmd in buttons.items():
        btn = tk.Button(submenu, text=txt, command=cmd,
                        font=("Helvetica",24), bg="#444444", fg="white",
                        width=30, height=1, relief="raised")
        btn.pack(pady=20)

    tk.Button(submenu, text="Back", command=submenu.destroy,
              font=("Helvetica",18), bg="red", fg="white",
              width=30, height=1, relief="raised").pack(pady=30)
    tk.Button(submenu, text="Exit", command=exit_application,
              font=("Helvetica",18), bg="red", fg="white",
              width=30, height=1, relief="raised").pack(pady=10)

def exit_application():
    root.destroy()

# ======================== 📌 MAIN WINDOW SETUP ========================= #

root = tk.Tk()
root.title("STE Mission Planning Toolkit")
root.geometry("1600x800")
root.resizable(False, False)

set_background(root)

tk.Label(root, text="STE Mission Planning Toolkit",
         font=("Helvetica",36,"bold"),
         bg="black", fg="white", pady=20).pack(fill="x")

tk.Button(root, text="SETUP DOCUMENTATION", command=open_setup_documentation,
          font=("Helvetica",20,"bold"), bg="#FFD700", fg="black",
          width=40, height=2, relief="raised").pack(pady=20)

# ======================== 📌 TUTORIALS “?” BUTTON ========================= #

vbs4_docs = {
    "VBS4 Official Documentation":         lambda: messagebox.showinfo("VBS4 Doc","Open VBS4 docs in browser"),
    "Script Wiki":                          lambda: messagebox.showinfo("Script Wiki","Open script wiki in browser"),
    "Video Tutorials":                      lambda: messagebox.showinfo("Video Tutorials","Play VBS4 tutorial videos"),
    "Support Website (requires Internet)":  lambda: messagebox.showinfo("Support","Open VBS4 support site"),
}

blueig_docs = {
    "Blue IG Official Documentation":      lambda: messagebox.showinfo("BlueIG Doc","Open BlueIG docs in browser"),
    "Video Tutorials":                      lambda: messagebox.showinfo("Video Tutorials","Play BlueIG tutorial videos"),
    "Support Website (requires Internet)":  lambda: messagebox.showinfo("Support","Open BlueIG support site"),
}

bvi_docs = {
    "BVI Official Documentation":          lambda: messagebox.showinfo("BVI Doc","Open BVI docs in browser"),
    "Video Tutorials":                      lambda: messagebox.showinfo("Video Tutorials","Play BVI tutorial videos"),
    "Support Website (requires Internet)":  lambda: messagebox.showinfo("Support","Open BVI support site"),
}

quick_start_docs = {
    "Video Tutorials": lambda: messagebox.showinfo("Quick‑Start","Play quick‑start videos"),
}

oneclick_docs = {
    "How to collect terrain scans w/ Drone":  lambda: messagebox.showinfo("One‑Click","Show drone collection guide"),
    "How to import terrain scans from drone": lambda: messagebox.showinfo("One‑Click","Show drone import guide"),
    "How to: Simulated Terrain":              lambda: open_submenu("Simulated Terrain Docs", {
        "Create Mesh Documentation": lambda: messagebox.showinfo("Mesh Doc","Show mesh creation guide"),
        "One‑Click Documentation":  lambda: messagebox.showinfo("One‑Click","Show one‑click terrain guide"),
    }),
}

tutorials_items = {
    "VBS4 Documentation":               lambda: open_submenu("VBS4 Documentation",    vbs4_docs),
    "Blue IG Documentation":            lambda: open_submenu("Blue IG Documentation", blueig_docs),
    "BVI Documentation":                lambda: open_submenu("BVI Documentation",     bvi_docs),
    "Quick‑Start Guide for entire kit": lambda: open_submenu("Quick‑Start Guide",    quick_start_docs),
    "One‑Click Terrain Documentation":  lambda: open_submenu("One‑Click Terrain Documentation", oneclick_docs),
}

tk.Button(root, text="?", command=lambda: open_submenu("Tutorials", tutorials_items),
          font=("Helvetica",24), bg="#FFD700", fg="black",
          width=2, height=1, relief="raised").place(x=1550, y=110)

# ======================== 📌 MAIN MENU BUTTONS ========================= #

main_buttons = {
    "VBS4 / BlueIG": lambda: open_submenu("VBS4 / BlueIG", {
        "Launch VBS4 as (Host)": lambda: launch_application(batch_files[0], "VBS4 (Host)"),
        "Launch VBS4 as (User)": lambda: launch_application(batch_files[1], "VBS4 (User)"),
        "One-Click Terrain":     lambda: open_submenu("One-Click Terrain", {
                                      "Select Imagery":     lambda: messagebox.showinfo("Terrain","Select Imagery"),
                                      "Create Mesh":        lambda: messagebox.showinfo("Terrain","Create Mesh"),
                                      "View Mesh (.obj)":   lambda: messagebox.showinfo("Terrain","View Mesh (.obj)"),
                                      "One-Click Tutorial": lambda: messagebox.showinfo("Terrain","Launch Tutorial"),
                                  }),
        "External Map":          lambda: open_submenu("External Map", {
                                      "Select User Profile": lambda: messagebox.showinfo("Map","Select Profile"),
                                      "Open External Map":   lambda: messagebox.showinfo("Map","Launching Browser"),
                                  }),
    }),
    "BVI":           lambda: open_submenu("BVI", {
                          "Launch BVI": launch_bvi,
                          "Terrains":   lambda: messagebox.showinfo("BVI","List terrains from web app"),
                      }),
    "Settings":      lambda: open_submenu("Settings", {
                          "Launch on Startup":          lambda: messagebox.showinfo("Settings","Toggle Launch on Startup"),
                          "Close on Software Launch?":  lambda: messagebox.showinfo("Settings","Toggle Close on Launch"),
                          "VBS4 Install Location":      lambda: messagebox.showinfo("Settings","Change VBS4 Path"),
                          "BlueIG Install":             lambda: messagebox.showinfo("Settings","Change BlueIG Path"),
                          "Pick Default Browser":       lambda: messagebox.showinfo("Settings","Select Default Browser"),
                      }),
}

for text, cmd in main_buttons.items():
    btn = create_button(root, text, cmd)
    btn.pack(pady=20)

root.mainloop()
