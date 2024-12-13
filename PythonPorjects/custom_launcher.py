import tkinter as tk
from tkinter import messagebox
import subprocess
import os
from PIL import Image, ImageTk

# Paths to the application executables and background image
bypass_launcher_path = r"C:\Bohemia Interactive Simulations\VBS4 24.1 YYMEA_General\VBS4.exe"
regular_launcher_path = r"C:\Bohemia Interactive Simulations\VBS4 24.1 YYMEA_General\VBSLauncher.exe"
background_image_path = r"C:\Repos\VBS4Project\PythonPorjects\20240206_101613_026.jpg"

# Function to launch directly into battlespace
def launch_mainspace():
    bat_file_path = r"C:\Repos\VBS4Project\PythonPorjects\Autolaunch_Batchfiles\Launch.bat"  # Replace with the actual path to your .bat file

    if os.path.exists(bat_file_path):
        try:
            subprocess.Popen([bat_file_path], shell=True)
            messagebox.showinfo("Launcher", "VBS4 launched successfully using the batch file!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch VBS4 via the batch file.\n{e}")
    else:
        messagebox.showerror("Error", "Batch file path does not exist.")

# Function to launch the regular VBS Launcher
def launch_regular():
    if os.path.exists(regular_launcher_path):
        try:
            subprocess.Popen(regular_launcher_path, shell=True)
            messagebox.showinfo("Launcher", "VBS4 launched with the regular startup window!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch the regular VBS Launcher.\n{e}")
    else:
        messagebox.showerror("Error", "Regular application path does not exist.")

# Function to exit the GUI
def exit_application():
    root.destroy()

# Create the main GUI window
root = tk.Tk()
root.title("VBS4 Custom Launcher")
root.geometry("1600x800")  # Adjust to match the image dimensions or desired window size
root.resizable(False, False)  # Disable resizing for both width and height

# Load and set the background image
try:
    bg_image = Image.open(background_image_path)
    bg_image = bg_image.resize((1600, 800), Image.Resampling.LANCZOS)  # Use the updated Resampling.
    bg_photo = ImageTk.PhotoImage(bg_image)

    bg_label = tk.Label(root, image=bg_photo)
    bg_label.place(relwidth=1, relheight=1)  # Cover the entire window with the background image
except Exception as e: 
    messagebox.showerror("Error", f"Failed to load background image.\n{e}")

# Add a header label with styling (over background)
header = tk.Label(
    root, text="STE Mission planning tool Launcher", font=("Helvetica", 30, "bold"), bg="#000000", fg="white", relief="ridge", padx=10, pady=5
)
header.pack(pady=40)

# Add buttons for each option
mainspace_button = tk.Button(
    root, text="VBS4 Launch", command=launch_mainspace, font=("Helvetica", 20), bg="blue", fg="white", width=30, height=3
)
mainspace_button.pack(pady=30) 

regular_button = tk.Button(
    root, text="Setup VBS4 Launch", command=launch_regular, font=("Helvetica", 20), bg="green", fg="white", width=30, height=3
)
regular_button.pack(pady=30) 

exit_button = tk.Button(
    root, text="Exit", command=exit_application, font=("Helvetica", 20), bg="red", fg="white", width=30, height=3
)
exit_button.pack(pady=30) 

root.mainloop()
