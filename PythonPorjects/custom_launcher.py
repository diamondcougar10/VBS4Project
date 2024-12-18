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

# Configure grid weights for centering
root.grid_rowconfigure(0, weight=1)  # Top spacer
root.grid_rowconfigure(10, weight=1)  # Bottom spacer
root.grid_columnconfigure(0, weight=1)  # Left spacer
root.grid_columnconfigure(4, weight=1)  # Right spacer

# Add header label
header = tk.Label(
    root, text="STE Mission Planning Toolkit", font=("Helvetica", 30, "bold"),
    bg="#000000", fg="white", relief="ridge", padx=10, pady=5
)
header.grid(row=1, column=1, columnspan=3, pady=20)

# Add main buttons
mainspace_button = tk.Button(
    root, text="Launch 3D Wargame (VBS4)", command=launch_mainspace,
    font=("Helvetica", 20), bg="blue", fg="white", width=30, height=2
)
mainspace_button.grid(row=2, column=1, columnspan=3, pady=10)

advanced_launcher_button = tk.Button(
    root, text="Launch VBS4 Advanced Launcher", command=launch_advanced_launcher,
    font=("Helvetica", 20), bg="green", fg="white", width=30, height=2
)
advanced_launcher_button.grid(row=3, column=1, columnspan=3, pady=10)

# Add expandable buttons 1-8 in two columns
expandable_buttons = []
for i in range(8):  # Add 8 expandable buttons
    btn = tk.Button(
        root, text=f"Button {i+1}", command=lambda i=i: print(f"Button {i+1} pressed"),
        font=("Helvetica", 16), bg="#dddddd", fg="black", width=20, height=2
    )
    expandable_buttons.append(btn)
    # Place buttons in 2 columns
    btn.grid(row=4 + (i // 2), column=1 + (i % 2), padx=10, pady=10)

# Add exit button
exit_button = tk.Button(
    root, text="Exit", command=exit_application,
    font=("Helvetica", 20), bg="red", fg="white", width=20, height=2
)
exit_button.grid(row=8, column=1, columnspan=3, pady=20)

root.mainloop()
