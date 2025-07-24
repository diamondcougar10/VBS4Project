# One-Click Reality Mesh Workflow

This repository contains automation scripts for processing PhotoMesh builds and packaging them for VBS4. The workflow for the post-processing steps is outlined below.

## Post-Project Wizard Steps
1. **Generate Project Structure** – After PhotoMesh finishes generating OBJ files in `Build_1/out`, the toolkit creates an output folder for the project.
2. **Create `/Data` Folder and Copy OBJs** – The entire OBJ directory is copied into `Data/OBJ` inside the new project folder.
3. **Create Project Settings File** – A text file next to `Data` stores project metadata and configuration for the `RealityMeshProcess.ps1` script.
4. **(Optional) Split Mesh into 4 Sub‑Projects** – If implemented, the mesh can be divided into four regions for parallel processing.
5. **Trigger Reality Mesh PowerShell Script** – `RealityMeshProcess.ps1` is executed with the settings file to build the VBS4 terrain package.
6. **Done Message and Log File** – Processing progress is logged and a completion message is displayed.
7. **Progress Bar** – The GUI now shows a status bar indicating processing percentage while the Reality Mesh script runs.
8. **Copy Output to All VBS4 Install Locations** – Generated terrain is replicated to all configured VBS4 installations as defined in `distribution_paths.json`.
9. **Close PhotoMesh Fuser Processes** – All running `Fuser.exe` instances are terminated.

The `distribution_paths.json` file lists remote VBS4 install paths. Update it with UNC paths to ensure terrain packages are synchronized across machines.

## Running the Standalone Post‑Processor

The GUI for post‑processing is located under `PythonPorjects/RealityMeshStandalone.py`.
Launch it from the repository root with:

```bash
python PythonPorjects/RealityMeshStandalone.py
```

Avoid hard‑coded absolute paths so the tool can be executed from any checkout location.
The required `RealityMeshProcess.ps1` script and `RealityMeshSystemSettings.txt` file
are bundled under `PythonPorjects/photomesh`. The GUI automatically points to these
files so the user only needs to browse to the `Build_1/out` folder.

### Configuring Tool Paths

Edit `PythonPorjects/photomesh/RealityMeshSystemSettings.txt` to point to your
local installations of Blender and TerraTools. For Bisim standard installs you
can use:

```
blender_path=C:\Program Files\Blender Foundation\Blender 4.5\blender.exe
terratools_ssh_path=C:\Program Files\Bohemia Interactive Simulations\TerraTools\bin\terratoolssh.exe
terratools_home_path=C:\Program Files\Bohemia Interactive Simulations\TerraTools
dataset_root=C:\BiSim OneClick\Datasets
```

`dataset_root` specifies where new project folders are created before
running the Reality Mesh process.

Adjust these paths if your installers reside elsewhere or you need to reference
additional tools like ModelExchanger.
