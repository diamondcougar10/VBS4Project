# One-Click Reality Mesh Workflow

This repository contains automation scripts for processing PhotoMesh builds and packaging them for VBS4. The workflow for the post-processing steps is outlined below.

## Post-Project Wizard Steps
1. **Generate Project Structure** – After PhotoMesh finishes generating OBJ files in `Build_1/out`, the toolkit creates an output folder for the project.
2. **Create `/Data` Folder and Copy OBJs** – The entire OBJ directory is copied into `Data/OBJ` inside the new project folder.
3. **Create Project Settings File** – A text file next to `Data` stores project metadata and configuration for the `RealityMeshProcessor.ps1` script.
4. **(Optional) Split Mesh into 4 Sub‑Projects** – If implemented, the mesh can be divided into four regions for parallel processing.
5. **Trigger Reality Mesh PowerShell Script** – `RealityMeshProcessor.ps1` is executed with the settings file to build the VBS4 terrain package.
6. **Done Message and Log File** – Processing progress is logged and a completion message is displayed.
7. **Copy Output to All VBS4 Install Locations** – Generated terrain is replicated to all configured VBS4 installations as defined in `distribution_paths.json`.
8. **Close PhotoMesh Fuser Processes** – All running `Fuser.exe` instances are terminated.

The `distribution_paths.json` file lists remote VBS4 install paths. Update it with UNC paths to ensure terrain packages are synchronized across machines.
