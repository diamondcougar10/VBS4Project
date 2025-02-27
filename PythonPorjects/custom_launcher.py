import tkinter as tk
from tkinter import messagebox
import subprocess
import os
from PIL import Image, ImageTk

# Paths to batch files and executables
batch_folder = r"C:\Repos\VBS4Project\PythonPorjects\Autolaunch_Batchfiles"
batch_files = {
    "Launch 3D Wargame (VBS4)": os.path.join(batch_folder, "Launch.bat"),
    "Launch BVI": os.path.join(batch_folder, "BVi_Launch.bat"),
    "Launch DXTRS": os.path.join(batch_folder, "Dxtrs_Launch.bat")
}
vbs4_setup_path = r"C:\Bohemia Interactive Simulations\VBS4 24.1 YYMEA_General\VBSLauncher.exe"
background_image_path = r"C:\Repos\VBS4Project\PythonPorjects\20240206_101613_026.jpg"

# Function to launch batch files or executables
def launch_application(app_path, app_name):
    if os.path.exists(app_path):
        try:
            subprocess.Popen(app_path, shell=True)
            messagebox.showinfo("Launcher", f"{app_name} launched successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch {app_name}.\n{e}")
    else:
        messagebox.showerror("Error", f"{app_name} path not found.")

# Function to apply background image to a window
def set_background(window):
    bg_image = Image.open(background_image_path)
    bg_image = bg_image.resize((1600, 800), Image.Resampling.LANCZOS)  # Fit image to window size
    bg_photo = ImageTk.PhotoImage(bg_image)

    bg_label = tk.Label(window, image=bg_photo)
    bg_label.image = bg_photo  # Keep a reference to prevent garbage collection
    bg_label.place(relwidth=1, relheight=1)

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
        "Launch 3D Wargame (VBS4)": lambda: launch_application(batch_files["Launch 3D Wargame (VBS4)"], "VBS4"),
        "VBS4 Setup": lambda: launch_application(vbs4_setup_path, "VBS4 Setup"),
        "Launch BVI": lambda: launch_application(batch_files["Launch BVI"], "BVI"),
        "Launch DXTRS": lambda: launch_application(batch_files["Launch DXTRS"], "DXTRS")
    }),
    "Scenarios": lambda: open_submenu("Scenarios", {
        "Scenario 1": lambda: messagebox.showinfo("Scenario", "Launching Scenario 1..."),
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
