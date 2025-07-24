Create a text file in this folder named ``RealityMeshSystemSettings.txt``. The
VBS4 path no longer needs to be edited manually – it will be updated
automatically based on the toolkit configuration.  The remaining values are
examples that can be tailored to your machine.  This file only needs to be
created once.  To note, ``1`` = true, ``0`` = false.

blender_path=C:\Program Files\Blender Foundation\Blender 4.5\blender.exe
blender_threads=6
override_Installation_VBS4=1
# Path and version are injected automatically when the scripts run
override_Path_VBS4=
vbs4_version=
override_Installation_DevSuite=0
override_Path_DevSuite=P
terratools_ssh_path=C:\Program Files\Bohemia Interactive Simulations\TerraTools\bin\terratoolssh.exe

###This line can be used to configure a loose files/dev build of terratools to work with the script // dont include lines with ### in the final settings file
terratools_home_path=C:\Program Files\Bohemia Interactive Simulations\TerraTools

# Optional: set paths to other tools such as ModelExchanger if required.
dataset_root=C:\BiSim OneClick\Datasets  # where project folders will be stored
