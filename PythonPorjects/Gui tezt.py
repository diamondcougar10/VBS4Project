import tkinter as tk
from tkinter import messagebox
import subprocess
import os

# Paths to the application executables
bypass_launcher_path = r"C:\Bohemia Interactive Simulations\VBS4 24.1 YYMEA_General\VBS4.exe" 
regular_launcher_path = r"C:\Bohemia Interactive Simulations\VBS4 24.1 YYMEA_General\VBSLauncher.exe"  # Regular launcher path

# Function to launch the application in bypass mode
def launch_bypass():
    if os.path.exists(bypass_launcher_path):
        try:
            subprocess.Popen(bypass_launcher_path, shell=True)
            messagebox.showinfo("Launcher", "VBS4 launched in bypass mode!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch in bypass mode.\n{e}")
    else:
        messagebox.showerror("Error", "Bypass application path does not exist.")

# Function to launch the regular application
def launch_regular():
    if os.path.exists(regular_launcher_path):
        try:
            subprocess.Popen(regular_launcher_path, shell=True)
            messagebox.showinfo("Launcher", "VBS4 launched with the regular startup window!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch with the regular startup window.\n{e}")
    else:
        messagebox.showerror("Error", "Regular application path does not exist.")

# Function to exit the GUI
def exit_application():
    root.destroy()

# Create the main GUI window
root = tk.Tk()
root.title("VBS4 Custom Launcher")
root.geometry("400x300")  # Set the window size

# Add a label to the GUI
label = tk.Label(root, text="VBS4 Custom Launcher", font=("Helvetica", 16))
label.pack(pady=20)

# Add buttons for each option
bypass_button = tk.Button(root, text="Launch VBS4", command=launch_bypass, font=("Helvetica", 12), bg="blue", fg="white")
bypass_button.pack(pady=10)

regular_button = tk.Button(root, text="Launch VBS4 Setup", command=launch_regular, font=("Helvetica", 12), bg="green", fg="white")
regular_button.pack(pady=10)

exit_button = tk.Button(root, text="Exit", command=exit_application, font=("Helvetica", 12), bg="red", fg="white")
exit_button.pack(pady=10)

# Run the Tkinter event loop
root.mainloop()
