import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import subprocess
import os
from PIL import Image, ImageTk

# Get the base directory of the project
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Paths to batch files and executables (Relative)
BATCH_FOLDER = os.path.join(BASE_DIR, "Autolaunch_Batchfiles")
if not os.path.exists(BATCH_FOLDER):
    os.makedirs(BATCH_FOLDER)  # Create batch folder if missing

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


# Function to apply background image
background_image_path = os.path.join(BASE_DIR, "20240206_101613_026.jpg")
def set_background(window):
    try:
        bg_image = Image.open(background_image_path)
        bg_image = bg_image.resize((1600, 800), Image.Resampling.LANCZOS)  # Fit image to window size
        bg_photo = ImageTk.PhotoImage(bg_image)

        bg_label = tk.Label(window, image=bg_photo)
        bg_label.image = bg_photo  # Keep a reference to prevent garbage collection
        bg_label.place(relwidth=1, relheight=1)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load background image.\n{e}")

# Function to open a submenu
def open_submenu(title, buttons):
    submenu = tk.Toplevel(root)
    submenu.title(title)
    submenu.geometry("1600x800")
    submenu.resizable(False, False)  # Lock window size

    set_background(submenu)  # Apply background

    # Header Label
    label = tk.Label(submenu, text=title, font=("Helvetica", 30, "bold"), bg="black", fg="white", pady=15)
    label.pack(fill="x")

    # Button Frame (To keep buttons centered)
    button_frame = tk.Frame(submenu, bg="black")
    button_frame.pack(pady=50)

    for btn_text, command in buttons.items():
        btn = tk.Button(button_frame, text=btn_text, command=command, font=("Helvetica", 18), 
                        bg="#555555", fg="white", width=40, height=2, relief="raised")
        btn.pack(pady=15)

    # Back Button
    back_btn = tk.Button(button_frame, text="Back", command=submenu.destroy, font=("Helvetica", 18), 
                         bg="red", fg="white", width=40, height=2, relief="raised")
    back_btn.pack(pady=30)

    # Exit Button in Submenu
    exit_btn = tk.Button(button_frame, text="Exit", command=exit_application, font=("Helvetica", 18),
                         bg="red", fg="white", width=40, height=2, relief="raised")
    exit_btn.pack(pady=10)

# Function to exit the GUI
def exit_application():
    root.destroy()

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
        "Load a Terrain": lambda: messagebox.showinfo("Help", "Opening Load a Terrain Tutorial...")
    })
}

# Create Main Buttons (Centered in a Frame)
button_frame = tk.Frame(root, bg="black")
button_frame.pack(pady=50)

for btn_text, command in main_buttons.items():
    btn = tk.Button(button_frame, text=btn_text, command=command, font=("Helvetica", 24), 
                    bg="#444444", fg="white", width=40, height=2, relief="raised")
    btn.pack(pady=20)

# Exit Button in Main Menu
exit_button = tk.Button(root, text="Exit", command=exit_application, font=("Helvetica", 24), 
                        bg="red", fg="white", width=40, height=2, relief="raised")
exit_button.pack(pady=30)

root.mainloop()
