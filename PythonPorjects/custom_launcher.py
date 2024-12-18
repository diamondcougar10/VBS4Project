import tkinter as tk
from tkinter import messagebox
import subprocess
import os
from PIL import Image, ImageTk

# Paths to the application executables and background image
bypass_launcher_path = r"C:\Bohemia Interactive Simulations\VBS4 24.1 YYMEA_General\VBS4.exe"
advanced_launcher_path = r"C:\Bohemia Interactive Simulations\VBS4 24.1 YYMEA_General\VBSLauncher.exe"
background_image_path = r"C:\Repos\VBS4Project\PythonPorjects\20240206_101613_026.jpg"

# Function to launch directly into battlespace using the batch file
def launch_mainspace():
    bat_file_path = r"C:\Repos\VBS4Project\PythonPorjects\Autolaunch_Batchfiles\Launch.bat"
    if os.path.exists(bat_file_path):
        try:
            subprocess.Popen([bat_file_path], shell=True)
            messagebox.showinfo("Launcher", "VBS4 launched successfully using the batch file!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch VBS4 via the batch file.\n{e}")
    else:
        messagebox.showerror("Error", "Batch file path does not exist.")
    root.destroy()  # Close menu after launcher button press

# Function to launch the advanced VBS Launcher
def launch_advanced_launcher():
    if os.path.exists(advanced_launcher_path):
        try:
            subprocess.Popen(advanced_launcher_path, shell=True)
            messagebox.showinfo("Launcher", "Launching Virtual Battlespace 4 Advanced Launcher!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch the advanced VBS Launcher.\n{e}")
    else:
        messagebox.showerror("Error", "Advanced Launcher application path does not exist.")
    root.destroy()  # Close menu after launcher button press

# Function to update tooltip at bottom of screen
def update_tooltip(text):
    tooltip_label.config(text=text)

# Function to exit the GUI
def exit_application():
    root.destroy()

# Create the main GUI window
root = tk.Tk()
root.title("STE Mission Planning Toolkit")
root.geometry("1600x800")
root.resizable(False, False)

# Load and set the background image
try:
    bg_image = Image.open(background_image_path)
    bg_image = bg_image.resize((1600, 800), Image.Resampling.LANCZOS)
    bg_photo = ImageTk.PhotoImage(bg_image)

    bg_label = tk.Label(root, image=bg_photo)
    bg_label.place(relwidth=1, relheight=1)
except Exception as e:
    messagebox.showerror("Error", f"Failed to load background image.\n{e}")

# Configure grid layout for centering and spacing
root.grid_rowconfigure(0, weight=1)
root.grid_rowconfigure(10, weight=1)
root.grid_columnconfigure(0, weight=1)
root.grid_columnconfigure(4, weight=1)

# Add header
header = tk.Label(root, text="STE Mission Planning Toolkit", font=("Helvetica", 30, "bold"),
                  bg="#000000", fg="white", relief="ridge", padx=10, pady=5)
header.grid(row=1, column=1, columnspan=2, pady=20)

# Add main buttons with descriptions
main_buttons = {
    "Launch 3D Wargame (VBS4)": "Launch the primary 3D virtual battlespace for training simulations.",
    "Launch VBS4 Advanced Launcher": "Open the advanced VBS4 launcher for additional configuration options."
}

mainspace_button = tk.Button(root, text="Launch 3D Wargame (VBS4)", command=launch_mainspace,
                             font=("Helvetica", 20), bg="blue", fg="white", width=30, height=2, relief="flat")
mainspace_button.grid(row=2, column=1, columnspan=2, pady=10)
mainspace_button.bind("<Enter>", lambda e: update_tooltip(main_buttons["Launch 3D Wargame (VBS4)"]))
mainspace_button.bind("<Leave>", lambda e: update_tooltip(""))

advanced_launcher_button = tk.Button(root, text="Launch VBS4 Advanced Launcher", command=launch_advanced_launcher,
                                     font=("Helvetica", 20), bg="green", fg="white", width=30, height=2, relief="flat")
advanced_launcher_button.grid(row=3, column=1, columnspan=2, pady=10)
advanced_launcher_button.bind("<Enter>", lambda e: update_tooltip(main_buttons["Launch VBS4 Advanced Launcher"]))
advanced_launcher_button.bind("<Leave>", lambda e: update_tooltip(""))

# Location buttons with descriptions
locations = {
    "Camp Atterbury": "Training location for reserve and active-duty units.",
    "Camp Shelby": "Mississippi National Guard's Joint Force Training Center.",
    "Ft Bliss (Armor)": "Major hub for heavy armored training operations.",
    "Ft Stewart": "Home of the 3rd Infantry Division, specializing in rapid deployment.",
    "Joint Base McGuire-Dix-Lakehurst": "Joint operations base for air mobility and combat training."
}

row_start = 4
col = 1
for idx, (location, description) in enumerate(locations.items()):
    btn = tk.Button(root, text=location, font=("Helvetica", 16), bg="#dddddd", fg="black", width=20, height=2, relief="flat")
    btn.grid(row=row_start + (idx // 2), column=col + (idx % 2), padx=10, pady=5)
    btn.bind("<Enter>", lambda e, desc=description: update_tooltip(desc))
    btn.bind("<Leave>", lambda e: update_tooltip(""))

# Add blank buttons 1-5 with descriptions
for i in range(5):
    blank_btn = tk.Button(root, text=f"Button {i+1}", font=("Helvetica", 16), bg="#dddddd", fg="black",
                          width=20, height=2, relief="flat")
    blank_btn.grid(row=6 + (i // 3), column=1 + (i % 2), padx=10, pady=5)
    blank_btn.bind("<Enter>", lambda e, i=i: update_tooltip(f"This is a blank button {i+1} for future use."))
    blank_btn.bind("<Leave>", lambda e: update_tooltip(""))

# Tooltip label at bottom
tooltip_label = tk.Label(root, text="", font=("Helvetica", 14), bg="black", fg="white", anchor="center")
tooltip_label.grid(row=10, column=0, columnspan=5, sticky="ew", pady=10)

# Add exit button
exit_button = tk.Button(root, text="Exit", command=exit_application, font=("Helvetica", 20),
                        bg="red", fg="white", width=20, height=2, relief="flat")
exit_button.grid(row=8, column=1, columnspan=2, pady=20)

root.mainloop()
