import sys
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import subprocess
import os
from PIL import Image, ImageTk

# ======================== 📌 SETUP & CONFIGURATION ========================= #

# def resource_path(relative_path):
#     """ Get absolute path to resource, works for dev and for PyInstaller """
#     try:
#         # PyInstaller creates a temp folder and stores path in _MEIPASS
#         base_path = sys._MEIPASS
#     except Exception:
#         base_path = os.path.abspath(".")

#     return os.path.join(base_path, relative_path)

# Get the base directory of the project

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ======================== 📌 Path & File Locations ========================= #

# Path to the Logos
logo_STE_path = os.path.join(BASE_DIR, "logos", "STE_CFT_Logo.png")
logo_us_army_path = os.path.join(BASE_DIR, "logos", "New_US_Army_Logo.png")
logo_first_army  = os.path.join(BASE_DIR, "logos", "First_Army_Logo.png")
logo_AFC_army  = os.path.join(BASE_DIR, "logos", "US_Army_AFC_Logo.png ")

# Define the background image path
background_image_path = os.path.join(BASE_DIR, "20240206_101613_026.jpg")

# Path to the Setup Documentation PDF
PDF_FILE_PATH = os.path.join(BASE_DIR, "STE_SMTP_KIT_GUIDE.pdf")

#Path to help and tutorials files
bvi_setup_doc_path = os.path.join(BASE_DIR, "Help_Tutorials", "Bvi_Vbs4_Setup.pdf")
# Path to the Demo Video
demo_video_path = os.path.join(BASE_DIR, "Help_Tutorials", "BattleSpaceSetup.mkv")

# Paths to batch files and executables (Relative)
BATCH_FOLDER = os.path.join(BASE_DIR, "Autolaunch_Batchfiles")
if not os.path.exists(BATCH_FOLDER):
    os.makedirs(BATCH_FOLDER)  # Create batch folder if missing

#============================📌 HElP AND tutorials FUNCTION =============================#

def open_bvi_setup_doc():
    """Opens the BVI VBS4 Setup document with the default Word processor."""
    if os.path.exists(bvi_setup_doc_path):
        try:
            subprocess.Popen([bvi_setup_doc_path], shell=True)  # Open with default app
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open BVI VBS4 Setup document.\n{e}")
    else:
        messagebox.showerror("Error", "BVI VBS4 Setup document not found.")

def play_demo_video():
    """Opens the demo video using the default media player."""
    if os.path.exists(demo_video_path):
        try:
            subprocess.Popen([demo_video_path], shell=True)  # Opens with the default video player
        except Exception as e:
            messagebox.showerror("Error", f"Failed to play demo video.\n{e}")
    else:
        messagebox.showerror("Error", "Demo video not found.")

# ======================== 📌 REUSABLE BUTTON FUNCTION ========================= #

def create_button(parent, text, command):
    """Reusable function to create styled buttons."""
    return tk.Button(parent, text=text, command=command, font=("Helvetica", 24), 
                     bg="#444444", fg="white", width=30, height=1, relief="raised")

# ======================== 📌 FUNCTION TO FIND INSTALLATION PATHS ========================= #

    # Function to open setup documentation
def open_setup_documentation():
    if os.path.exists(PDF_FILE_PATH):
        try:
            subprocess.Popen([PDF_FILE_PATH], shell=True)  # Opens with default PDF viewer
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open Setup Documentation.\n{e}")
    else:
        messagebox.showerror("Error", "Setup Documentation file not found.")

# Function to find VBS4 installation path dynamically
def find_vbs4():
    possible_paths = [
        os.path.join(os.getenv("PROGRAMFILES", "C:\\Program Files"), "BISIM", "VBS4", "VBS4.exe"),
        os.path.join(os.getenv("PROGRAMFILES(X86)", "C:\\Program Files (x86)"), "BISIM", "VBS4", "VBS4.exe"),
        r"C:\BISIM\VBS4\VBS4.exe"  # Default known path
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    # If VBS4 isn't found, prompt the user to select it manually
    messagebox.showwarning("VBS4 Not Found", "VBS4 installation not found. Please select VBS4.exe manually.")
    file_path = filedialog.askopenfilename(title="Select VBS4.exe", filetypes=[("Executable Files", "*.exe")])
    
    return file_path if os.path.exists(file_path) else None

# Function to find ARES (BVI) installation path dynamically
def find_ares():
    possible_paths = [
        os.path.join(os.getenv("PROGRAMFILES", "C:\\Program Files"), "ARES", "ARES-dev-release-v0.9.4-c1d3950", "ares.manager", "ares.manager.exe"),
        os.path.join(os.getenv("PROGRAMFILES(X86)", "C:\\Program Files (x86)"), "ARES", "ARES-dev-release-v0.9.4-c1d3950", "ares.manager", "ares.manager.exe")
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    messagebox.showwarning("ARES Not Found", "ARES installation not found. Please select ares.manager.exe manually.")
    file_path = filedialog.askopenfilename(title="Select ARES Manager Executable", filetypes=[("Executable Files", "*.exe")])
    
    return file_path if os.path.exists(file_path) else None

# Detect VBS4 Path
vbs4_exe_path = find_vbs4()
if not vbs4_exe_path:
    messagebox.showerror("Error", "VBS4 path not found. Exiting application.")
    exit()

# Detect ARES Path
ares_manager_path = find_ares()
if not ares_manager_path:
    messagebox.showerror("Error", "ARES path not found. Exiting application.")
    exit()

# ======================== 📌 FUNCTION TO CREATE & LAUNCH BATCH FILES ========================= #

# Function to create batch files dynamically
def create_batch_files(vbs4_path):
    host_batch = os.path.join(BATCH_FOLDER, "Host_Launch.bat")
    user_batch = os.path.join(BATCH_FOLDER, "User_Launch.bat")

    with open(host_batch, "w") as f:
        f.write(f'@echo off\n"{vbs4_path}" -admin "-autoassign=admin" -forceSimul -window\nexit')

    with open(user_batch, "w") as f:
        f.write(f'@echo off\n"{vbs4_path}" -forceSimul -window\nexit')

    return host_batch, user_batch

# Generate batch files
batch_files = create_batch_files(vbs4_exe_path)

# Function to create the Drone Scenario batch file with the correct parameters
def create_drone_scenario_batch(vbs4_path):
    drone_batch = os.path.join(BATCH_FOLDER, "DroneScenario.bat")

    with open(drone_batch, "w") as f:
        f.write(f'''@echo off
start "" "{vbs4_path}" -forceSimul -init=hostMission["Leonidas_demo"] -name=Admin -autoassign=Player1 -autostart=1
exit
''')

    return drone_batch

# Generate the Drone Scenario batch file dynamically (No Admin)
drone_scenario_batch = create_drone_scenario_batch(vbs4_exe_path)

# Function to create the correct BVI batch file
def create_bvi_batch_file(ares_path):
    manager_batch = os.path.join(BATCH_FOLDER, "BVI_Manager.bat")

    # Construct the XR path dynamically
    xr_path = ares_path.replace("ares.manager\\ares.manager.exe", "ares.xr\\Windows\\AresXR.exe")

    with open(manager_batch, "w") as f:
        f.write(f'''@echo off
start "" "{ares_path}"
timeout /t 40 /nobreak
start "" "{xr_path}"
exit
''')

    return manager_batch
# Generate batch file for BVI dynamically
bvi_batch_file = create_bvi_batch_file(ares_manager_path)

# Function to launch BVI
def launch_bvi():
    launch_application(bvi_batch_file, "BVI (ARES Manager & XR)")

# Function to launch batch files or executables and close the GUI
def launch_application(app_path, app_name):
    if os.path.exists(app_path):
        try:
            root.destroy()  # Close the GUI window
            subprocess.Popen(app_path, shell=True)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch {app_name}.\n{e}")
    else:
        messagebox.showerror("Error", f"{app_name} path not found.")

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


# ======================== 📌 FUNCTION TO OPEN SUBMENU ========================= #

def open_submenu(title, buttons):
    submenu = tk.Toplevel(root)
    submenu.title(title)
    submenu.geometry("1600x800")
    submenu.resizable(False, False)

    submenu.configure(bg=root["bg"])  # Use the same background as root
    submenu.attributes('-transparentcolor', submenu["bg"])  # Make it transparent
    set_background(submenu)

    header = tk.Label(submenu, text=title, font=("Helvetica", 36, "bold"),
                      bg="black", fg="white", pady=20)
    header.pack(fill="x")  # Ensure it stretches across the top

    for btn_text, command in buttons.items():
        btn = tk.Button(submenu, text=btn_text, command=command, font=("Helvetica", 24),
                        bg="#444444", fg="white", width=30, height=1, relief="raised")
        btn.pack(pady=20)

    back_btn = tk.Button(submenu, text="Back", command=submenu.destroy, font=("Helvetica", 18),
                         bg="red", fg="white", width=30, height=1, relief="raised")
    back_btn.pack(pady=30)

    exit_btn = tk.Button(submenu, text="Exit", command=exit_application, font=("Helvetica", 18),
                         bg="red", fg="white", width=30, height=1, relief="raised")
    exit_btn.pack(pady=10)

# ======================== 📌 FUNCTION TO EXIT APPLICATION ========================= #

# Function to exit the GUI
def exit_application():
    root.destroy()

# ======================== 📌 CREATE MAIN WINDOW ========================= #

# Create main window
root = tk.Tk()
root.title("STE Mission Planning Toolkit")
root.geometry("1600x800")
root.resizable(False, False)  # Lock window size

set_background(root)  # Apply background image

# Header
header = tk.Label(root, text="STE Mission Planning Toolkit", font=("Helvetica", 36, "bold"), 
                  bg="black", fg="white", pady=20)
header.pack(fill="x")

# **Setup Documentation Button**
setup_doc_button = tk.Button(root, text="SETUP DOCUMENTATION", command=open_setup_documentation, 
                             font=("Helvetica", 20, "bold"), bg="#FFD700", fg="black", width=40, height=2, relief="raised")
setup_doc_button.pack(pady=20)  # Add button at the top

# ======================== 📌 MAIN MENU BUTTONS ========================= #

# Main Menu Buttons
main_buttons = {
    "Tools": lambda: open_submenu("Tools", {
        "Launch VBS4 as (Host)": lambda: launch_application(batch_files[0], "VBS4 (Host)"),
        "Launch VBS4 as (User)": lambda: launch_application(batch_files[1], "VBS4 (User)"),
        "Launch BVI": launch_bvi,
        "VBS4 Setup": lambda: launch_application(vbs4_exe_path, "VBS4 Setup"),
    }),
    "Scenarios": lambda: open_submenu("Scenarios", {
        "Launch Leonidas Demo": lambda: launch_application(drone_scenario_batch, "Drone Scenario"),
        "Scenario 2": lambda: messagebox.showinfo("Scenario", "Launching Scenario 2..."),
        "Scenario 3": lambda: messagebox.showinfo("Scenario", "Launching Scenario 3...")
    }),
    "Terrain": lambda: open_submenu("Terrain", {
        "NTC": lambda: messagebox.showinfo("Terrain", "Loading NTC Terrain..."),
        "Stewart": lambda: messagebox.showinfo("Terrain", "Loading Stewart Terrain..."),
        "Muscatuck": lambda: messagebox.showinfo("Terrain", "Loading Muscatuck Terrain..."),
        "Orlando": lambda: messagebox.showinfo("Terrain", "Loading Orlando Terrain...")
    }),
    "Help - Tutorials": lambda: open_submenu("Help - Tutorials", {
    "Build a Scenario": lambda: messagebox.showinfo("Help", "Opening Build a Scenario Tutorial..."),
    "Load a Terrain": lambda: messagebox.showinfo("Help", "Opening Load a Terrain Tutorial..."),
    "BVI VBS4 Setup Guide": open_bvi_setup_doc,
    "Import a BattleSpace": play_demo_video 
})
}

# Loop through and create buttons directly inside root
for btn_text, command in main_buttons.items():
    btn = tk.Button(root, text=btn_text, command=command, font=("Helvetica", 24), 
                    bg="#444444", fg="white", width=30, height=1, relief="raised")
    btn.pack(pady=20) 
root.mainloop()
