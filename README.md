# One-Click Reality Mesh Workflow

This repository contains automation scripts for processing PhotoMesh builds and packaging them for VBS4. The workflow for the post-processing steps is outlined below.

## Post-Project Wizard Steps
1. **Generate Project Structure** – After PhotoMesh finishes generating OBJ files in `Build_1/out`, the toolkit creates an output folder for the project.
2. **Create `/Data` Folder and Copy OBJs** – The entire OBJ directory is copied into `Data/OBJ` inside the new project folder.
3. **Create Project Settings File** – A text file next to `Data` stores project metadata and configuration for the `RealityMeshProcess.ps1` script.
4. **(Optional) Split Mesh into 4 Sub‑Projects** – If implemented, the mesh can be divided into four regions for parallel processing.
5. **Trigger Reality Mesh PowerShell Script** – `Invoke-RemoteRealityMesh.ps1` launches `RealityMeshProcess.ps1` on a remote workstation via PowerShell Remoting.
6. **Monitor for `DONE.txt`** – The script waits for a `DONE.txt` flag in the shared output directory then copies the finished project back to the local results folder.
7. **Done Message and Log File** – Processing progress is logged and a completion message is displayed.
8. **Progress Bar** – The GUI now shows a status bar indicating processing percentage while the Reality Mesh script runs.
9. **Copy Output to All VBS4 Install Locations** – Generated terrain is replicated to all configured VBS4 installations as defined in `distribution_paths.json`.
10. **Close PhotoMesh Fuser Processes** – All running `Fuser.exe` instances are terminated.

The `distribution_paths.json` file lists remote VBS4 install paths. Update it with UNC paths to ensure terrain packages are synchronized across machines.

## Running the Standalone Post‑Processor

The GUI for post‑processing is located under `PythonPorjects/RealityMeshStandalone.py`.
Launch it from the repository root with:

```bash
python PythonPorjects/RealityMeshStandalone.py
```

When running a packaged release created with PyInstaller, a
`RealityMeshStandalone.exe` is located next to the main toolkit
executable. The "Open Standalone Post-Processor" button now looks for
this executable and launches it when available.

Avoid hard‑coded absolute paths so the tool can be executed from any checkout location.
The required `RealityMeshProcess.ps1` script and `RealityMeshSystemSettings.txt` file
are bundled under `PythonPorjects/photomesh`. The GUI automatically points to
these files so the user only needs to browse to the PhotoMesh project folder.

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

`dataset_root` specifies where new project folders are created before running
the Reality Mesh process. The folder will be created automatically the first
time the tool runs if it does not already exist.

Once a project is processed, the toolkit saves the full path to the generated
dataset under a `[BiSimOneClickPath]` section in `config.ini`. The Settings
panel now exposes this path and allows manually browsing for a different
output folder.

Adjust these paths if your installers reside elsewhere or you need to reference
additional tools like ModelExchanger.

### Remote Processing

Enter the destination workstation's IP address in the **Remote Host** field of
the GUI to offload processing. When a remote host is provided the toolkit calls
`Invoke-RemoteRealityMesh.ps1` which launches `RealityMeshProcess.ps1` on the
remote machine and copies the finished dataset back to the results folder.
While running remotely a visible command window pops up on the target machine
stating `RealityMeshProcess in progress do not turn off pc` to indicate that the
script is executing. The "Post-Process Last Build" button prompts for a remote
host similarly when launched from the main STE Toolkit.
