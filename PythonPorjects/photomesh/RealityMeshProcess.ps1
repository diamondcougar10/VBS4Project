#Arugment parsing
$project_settings_File = $args[0]
$fully_automate = $args[1]

function Normalize-UNCPath {
    param([Parameter(Mandatory)][string]$Path)
    # Convert // to \ and collapse triples, normalize slashes
    $p = $Path -replace '/', '\'
    $p = $p -replace '^[\]+', '\'  # keep single leading backslash for now
    if ($p.StartsWith('\') -and -not $p.StartsWith('\\')) {
        $p = "\" + $p  # now \\...
    }
    # Ensure exactly two leading backslashes for UNC
    $p = $p -replace '^[\]{3,}', '\\'
    if ($p.StartsWith('\') -and -not $p.StartsWith('\\')) { $p = "\" + $p }
    if (-not $p.StartsWith('\\')) { $p = $p -replace '^[\]+', '' } # local paths stay local
    return $p
}

function Sanitize-Name {
    param([Parameter(Mandatory)][string]$Name)
    # Remove invalid filename chars: \ / : * ? " < > | and trailing dots/spaces
    $n = $Name -replace '[\/:*?"<>|]', '_'
    $n = $n.Trim().TrimEnd('.')
    return $n
}

function Ensure-Directory {
    param([Parameter(Mandatory)][string]$Dir)
    if (-not (Test-Path -LiteralPath $Dir)) {
        New-Item -ItemType Directory -Path $Dir | Out-Null
    }
}

function SafeJoin {
    param(
        [Parameter(Mandatory)][string]$Base,
        [Parameter(Mandatory)][string]$Child
    )
    return (Join-Path -Path $Base -ChildPath $Child)
}

# Base shared drive accessible by both the calling and remote machines
$sharedRoot = Normalize-UNCPath '\SharedMeshDrive\RealityMesh'
$inputRoot = Normalize-UNCPath (SafeJoin $sharedRoot 'Input')
$outputRoot = Normalize-UNCPath (SafeJoin $sharedRoot 'Output')

if ([string]::IsNullOrEmpty($project_settings_File))
{
	$project_settings_File = Read-Host -Prompt "Enter absolute path to project settings file"
}

if ([string]::IsNullOrEmpty($fully_automate))
{
        $fully_automate = 0
}

$project_settings_File = Normalize-UNCPath ($project_settings_File.Trim('"'))

#Settings Parsing
$system_settings = "$PSScriptRoot/RealityMeshSystemSettings.txt"

if (!(Test-Path -LiteralPath $project_settings_File)) {
	Write-Output "project settings file does not exist"
	Read-Host -Prompt "Press Enter to exit"
	Return
}

if (!(Test-Path -LiteralPath $system_settings))
{
	Write-Output "System settings file does not exist"
	Read-Host -Prompt "Press Enter to exit"
	Return
}

Write-Output "Project and System settings found"

# Determine the location of the RealityMesh_tt template folder. Prefer the
# copy distributed alongside this script. If that folder is not present,
# fall back to the legacy STE Toolkit install path.
$RealityMeshTTPath = Join-Path $PSScriptRoot 'RealityMesh_tt'
$defaultRealityMeshTTPath = "C:\Program Files (x86)\STE Toolkit\RealityMesh_tt"
if (!(Test-Path $RealityMeshTTPath)) {
    if (Test-Path $defaultRealityMeshTTPath) {
        $RealityMeshTTPath = $defaultRealityMeshTTPath
    } else {
        Write-Error "RealityMesh_tt folder not found at '$RealityMeshTTPath' or '$defaultRealityMeshTTPath'"
        return
    }
}

#Project settings
$project_name = Sanitize-Name ((Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^project_name=" }) -replace "project_name=", "")
$source_Directory_temp = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^source_Directory=" }) -replace "source_Directory=", ""
$source_Directory = Normalize-UNCPath $source_Directory_temp

# Attempt to derive a better project name from Output-CenterPivotOrigin.json
$ocpo = Get-ChildItem -Path $source_Directory -Filter "Output-CenterPivotOrigin.json" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if ($ocpo) {
    $projectRoot = Split-Path $ocpo.DirectoryName -Parent
    if ((Split-Path $ocpo.DirectoryName -Leaf) -like "Build_*") {
        $projectRoot = Split-Path $projectRoot -Parent
    }
    $derivedName = Split-Path $projectRoot -Leaf
    if ($derivedName) {
        $project_name = Sanitize-Name $derivedName
    }
}
$sel_Area_Size = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^sel_Area_Size=" }) -replace "sel_Area_Size=", ""
$offset_coordsys = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^offset_coordsys=" }) -replace "offset_coordsys=", ""
$offset_hdatum = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^offset_hdatum=" }) -replace "offset_hdatum=", ""
$offset_vdatum = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^offset_vdatum=" }) -replace "offset_vdatum=", ""
$offset_x = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^offset_x=" }) -replace "offset_x=", ""
$offset_y = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^offset_y=" }) -replace "offset_y=", ""
$offset_z = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^offset_z=" }) -replace "offset_z=", ""
$orthocam_Resolution = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^orthocam_Resolution=" }) -replace "orthocam_Resolution=", ""
$orthocam_Render_Lowest = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^orthocam_Render_Lowest=" }) -replace "orthocam_Render_Lowest=", ""
$tin_to_dem_Resolution = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^tin_to_dem_Resolution=" }) -replace "tin_to_dem_Resolution=", ""
$tile_scheme = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^tile_scheme=" }) -replace "tile_scheme=", ""
$collision = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^collision=" }) -replace "collision=", ""
$visualLODs = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^visualLODs=" }) -replace "visualLODs=", ""
$project_vdatum = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^project_vdatum=" }) -replace "project_vdatum=", ""
$offset_models = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^offset_models=" }) -replace "offset_models=", ""
$csf_options = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^csf_options=" }) -replace "csf_options=", ""
$faceThresh = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^faceThresh=" }) -replace "faceThresh=", ""
$lodThresh = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^lodThresh=" }) -replace "lodThresh=", ""
$tileSize = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^tileSize=" }) -replace "tileSize=", ""
$srfResolution = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^srfResolution=" }) -replace "srfResolution=", ""

#System settings
$blender_path = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^blender_path=" }) -replace "blender_path=", ""
$default_blender = "C:\\Program Files\\Blender Foundation\\Blender 4.5\\blender.exe"
if (!(Test-Path $blender_path)) {
        if (Test-Path $default_blender) {
                $blender_path = $default_blender
                Write-Output "Using Blender found at $blender_path"
        } else {
                $search = Get-ChildItem "C:\\Program Files\\Blender Foundation" -Directory -ErrorAction SilentlyContinue |
                    Sort-Object Name -Descending |
                    ForEach-Object { Join-Path $_.FullName 'blender.exe' } |
                    Where-Object { Test-Path $_ } |
                    Select-Object -First 1

                if ($search) {
                        $blender_path = $search
                        Write-Output "Using Blender found at $blender_path"
                } else {
                        Write-Output "Blender Path invalid"
                        Read-Host -Prompt "Press Enter to exit"
                        Return
                }
        }
}
$blender_threads = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^blender_threads=" }) -replace "blender_threads=", ""
$override_Installation_VBS4 = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^override_Installation_VBS4=" }) -replace "override_Installation_VBS4=", ""
$override_Path_VBS4 = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^override_Path_VBS4=" }) -replace "override_Path_VBS4=", ""
if (($override_Installation_VBS4 -eq 1) -and !(Test-Path -LiteralPath $override_Path_VBS4)) {	
	Write-Output "VBS4 path invalid"
	Read-Host -Prompt "Press Enter to exit"
	Return
}
$vbs4_version = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^vbs4_version=" }) -replace "vbs4_version=", ""
$override_Installation_DevSuite = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^override_Installation_DevSuite=" }) -replace "override_Installation_DevSuite=", ""
$override_Path_DevSuite = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^override_Path_DevSuite=" }) -replace "override_Path_DevSuite=", ""
$terratools_home_path = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^terratools_home_path=" }) -replace "terratools_home_path=", ""
$terratools_ssh_path = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^terratools_ssh_path=" }) -replace "terratools_ssh_path=", ""
if (!(Test-Path -LiteralPath $terratools_ssh_path)) {	
	Write-Output "Terratools Path invalid"
	Read-Host -Prompt "Press Enter to exit"
	Return
}


#Running with found settings
$AREYOUSURE = ""
if ($fully_automate -eq 0) 
{
	$AREYOUSURE = Read-Host -Prompt "This script will execute a reality mesh data import process that will produce a new set of terrain inset files ready to use in VBS4. Processing time for the import process will vary with the data being imported. Do you want to proceed (Y/[N])? "
}
else {
	$AREYOUSURE = "y"
}


if ($AREYOUSURE -eq 'y') {
	
	if ($fully_automate -eq 0) 
	{
                if (Test-Path (Join-Path $inputRoot $project_name))
		{
			$newName = Read-Host -Prompt "$project_name already exists in projects folder.  Do you want to rename the project(a)?  Or cancel the process(b)?  (a/b)? "
			if ($newName -eq 'a') {
                                $project_name = Sanitize-Name (Read-Host -Prompt "Enter new name for project: ")
			}
			else {
				Read-Host -Prompt "Process cancelled.  Press Enter to exit"
				Return
			}
		}
	}
	else {
                if (Test-Path (Join-Path $inputRoot $project_name))
		{
			$timestamp = Get-Date -UFormat "%D_%T" | ForEach-Object { $_ -replace ":", "_" } | ForEach-Object { $_ -replace "/", "-" }
			$tempPath = ($project_name + "_" + $timestamp)
			$project_name = $tempPath
		}
		
		New-Item -Path "$PSScriptRoot\ProjectSettings\GeneratedFiles_DoNotEdit\AutomationHelper.txt" -ItemType "File" -Value "$project_name" -Force
	}
	
	
	$delete = ""
	if ($fully_automate -eq 0) 
	{
		$delete = Read-Host -Prompt "This will delete all temporary data on your devsuite drive for this project name. Do you want to proceed (y/[n])? "
	}
	else {
		$delete = "y"
	}
	
        if ($delete -eq 'y') {
                #Command to clean out &override_Path_DevSuite%):\$project_name and $override_Path_DevSuite:\vbs2\customer\structures\%Name% on each run
                $deletePath = "${override_Path_DevSuite}:\temp\RealityMesh\$project_name\"
                if (Test-Path -LiteralPath $deletePath) {
                        Write-Output "Deleting $deletePath"
                        Remove-Item -LiteralPath $deletePath -Force -Recurse
                }

                $deletePath2 = "${override_Path_DevSuite}:\vbs2\customer\structures\$project_name\"
                if (Test-Path -LiteralPath $deletePath2) {
                        Write-Output "Deleting $deletePath2"
                        Remove-Item -LiteralPath $deletePath2 -Force -Recurse
                }

                Write-Output "Cleaned files before creating new ones"
        }

        #Delete existing settings and create new file in the shared Input folder
        $projectFolder = Normalize-UNCPath (SafeJoin $inputRoot $project_name)
        Ensure-Directory $projectFolder

        $generated_settings_file = Normalize-UNCPath (SafeJoin $projectFolder "$project_name.txt")
        if (Test-Path -LiteralPath $generated_settings_file) {
                Remove-Item -LiteralPath $generated_settings_file
        }

        $override_Installation_VBS4_bool = "false"
        if ($override_Installation_VBS4 -eq 1) {
                $override_Installation_VBS4_bool = "true"
        }

        $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
        $out_in_name = "$project_name"
        $out_in_name_with_drive = Normalize-UNCPath (SafeJoin $outputRoot "${project_name}_$timestamp")
        Ensure-Directory $out_in_name_with_drive

        Write-Output "ProjectName: $project_name"
        Write-Output "DestDir: $out_in_name_with_drive"
        Write-Output "GeneratedSettingsFile: $generated_settings_file"

        New-Item -ItemType File -Path $generated_settings_file -Force | Out-Null
        Add-Content -LiteralPath $generated_settings_file -Value "set name {$project_name}"
        Add-Content -LiteralPath $generated_settings_file -Value "set blender_path {$blender_path}"
        Add-Content -LiteralPath $generated_settings_file -Value "set blender_threads {$blender_threads}"
        Add-Content -LiteralPath $generated_settings_file -Value "set override_Installation_VBS4_bool {$override_Installation_VBS4_bool}"
        Add-Content -LiteralPath $generated_settings_file -Value "set override_Path_VBS4 {$override_Path_VBS4}"
        Add-Content -LiteralPath $generated_settings_file -Value "set vbs4_version {$vbs4_version}"
        Add-Content -LiteralPath $generated_settings_file -Value "set override_Installation_DevSuite {$override_Installation_DevSuite}"
        Add-Content -LiteralPath $generated_settings_file -Value "set override_Path_DevSuite {$override_Path_DevSuite}"
        Add-Content -LiteralPath $generated_settings_file -Value "set offset_x {$offset_x}"
        Add-Content -LiteralPath $generated_settings_file -Value "set offset_y {$offset_y}"
        Add-Content -LiteralPath $generated_settings_file -Value "set offset_z {$offset_z}"
        Add-Content -LiteralPath $generated_settings_file -Value "set offset_coordsys {$offset_coordsys}"
        Add-Content -LiteralPath $generated_settings_file -Value "set offset_hdatum {$offset_hdatum}"
        Add-Content -LiteralPath $generated_settings_file -Value "set offset_vdatum {$offset_vdatum}"
        Add-Content -LiteralPath $generated_settings_file -Value "set orthocam_Resolution {$orthocam_Resolution}"
        Add-Content -LiteralPath $generated_settings_file -Value "set orthocam_Render_Lowest {$orthocam_Render_Lowest}"
        Add-Content -LiteralPath $generated_settings_file -Value "set tin_to_dem_Resolution {$tin_to_dem_Resolution}"
        Add-Content -LiteralPath $generated_settings_file -Value "set override_Installation_VBS4 {$override_Installation_VBS4}"
        Add-Content -LiteralPath $generated_settings_file -Value "set sel_Area_Size {$sel_Area_Size}"
        Add-Content -LiteralPath $generated_settings_file -Value "set out_in_name {$out_in_name}"
        Add-Content -LiteralPath $generated_settings_file -Value "set out_in_name_with_drive {$out_in_name_with_drive}"
        Add-Content -LiteralPath $generated_settings_file -Value "set collision {$collision}"
        Add-Content -LiteralPath $generated_settings_file -Value "set visualLODs {$visualLODs}"
        Add-Content -LiteralPath $generated_settings_file -Value "set project_vdatum {$project_vdatum}"
        Add-Content -LiteralPath $generated_settings_file -Value "set offset_models {$offset_models}"
        Add-Content -LiteralPath $generated_settings_file -Value "set csf_options {$csf_options}"
        Add-Content -LiteralPath $generated_settings_file -Value "set faceThresh {$faceThresh}"
        Add-Content -LiteralPath $generated_settings_file -Value "set lodThresh {$lodThresh}"
        Add-Content -LiteralPath $generated_settings_file -Value "set tileSize {$tileSize}"
        Add-Content -LiteralPath $generated_settings_file -Value "set srfResolution {$srfResolution}"

        $command_path = $generated_settings_file

        # Copy the project template files from the repository location.
        # Previously this expected the template folder to exist under the STE
        # Toolkit installation directory.  Use the template bundled with this
        # script instead to avoid relying on a fixed install path.
        # Use the previously resolved RealityMesh template path
        $templatePath = $RealityMeshTTPath
        $destinationPath = $projectFolder
        if (Test-Path -LiteralPath $templatePath) {
                robocopy "$templatePath" "$destinationPath" | Out-Null
        }
        else {
                Write-Output "Template folder not found at $templatePath"
                Return
        }

        Set-Location -LiteralPath $destinationPath

        Rename-Item -LiteralPath "RealityMeshProcess.ttp" -NewName "$project_name.ttp"

        "set sourceDir `"$source_Directory`" " | Out-File sourceDir.txt -Encoding Default
        "set tileScheme `"$tile_scheme`" " | Out-File tileScheme.txt -Encoding Default

        # Ensure n33.tbr exists before running the main TCL script
        $n33File = "n33.tbr"
        if (-not (Test-Path $n33File)) {
                Write-Host "n33.tbr not found. Generating with TSG_TBR_to_Vertex_Points_Unique.tcl..." -ForegroundColor Yellow
                & tclsh "TSG_TBR_to_Vertex_Points_Unique.tcl"
        }

        if (-not (Test-Path $n33File)) {
                Write-Host "ERROR: Required file n33.tbr could not be created." -ForegroundColor Red
                if ($fully_automate -eq 0) { Read-Host -Prompt "Press Enter to exit" }
                return
        }

        if (!([string]::IsNullOrEmpty($terratools_home_path)) -and (Test-Path $terratools_home_path)) {
                Write-Output "Using custom TERRATOOLS_HOME path at $terratools_home_path"
                $env:TERRASIM_HOME = $terratools_home_path
        }

        Write-Host "Launching RealityMeshProcess.tcl with settings from $command_path" -ForegroundColor Cyan
        Write-Host "🚧 Processing Reality Mesh... Please wait. Do not close this window." -ForegroundColor Yellow
        Start-Sleep -Seconds 2

        $startTime = Get-Date
        $proc = Start-Process -FilePath "$terratools_ssh_path" -NoNewWindow -PassThru -ArgumentList "RealityMeshProcess.tcl -command_file `"$command_path`""
        $spinner = '/-\|'
        $i = 0
        while (-not $proc.HasExited) {
                $char = $spinner[$i % $spinner.Length]
                Write-Host -NoNewline "`r$char Processing..."
                Start-Sleep -Seconds 1
                $i++
        }
        $proc.WaitForExit()
        Write-Host "`rProcessing complete.             "
        $time = (Get-Date) - $startTime
        $minutes = $time.TotalSeconds / 60
        Write-Output "`nTime to run TT project: $minutes minutes"

        "Time to run TT project: $minutes minutes" | Out-File TimingLog.txt -Encoding Default

        # Signal completion for remote monitors
        $doneFile = Normalize-UNCPath (SafeJoin $out_in_name_with_drive 'DONE.txt')
        New-Item -ItemType File -Path $doneFile -Force | Out-Null
        Write-Output "Created $doneFile"
} 
else 
{
	Write-Output "You will need to change the project name to avoid overwriting temprory data.  Change the project_name and rerun the ps1"
}

if ($fully_automate -eq 0) 
{
	Read-Host -Prompt "Press Enter to exit"
}