# =========================
# Reality Mesh Runner (fixed UNC + robust paths)
# =========================

# Argument parsing
$project_settings_File = $args[0]
$fully_automate = $args[1]

# ---------- Helpers ----------
function Normalize-UNCPath {
    param([Parameter(Mandatory)][string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $Path }

    # 1) Normalize slashes
    $p = $Path -replace '/', '\'

    # 2) If it looks like UNC (starts with at least two backslashes), collapse 3+ to exactly 2
    if ($p -match '^[\\]{2,}') {
        $p = $p -replace '^[\\]{2,}', '\\\\'
        return $p
    }

    # 3) Otherwise (local/relative), just return the normalized slashes
    return $p
}

function Sanitize-Name {
    param([Parameter(Mandatory)][string]$Name)
    # Remove invalid filename chars: \ / : * ? " < > | and trailing dots/spaces
    $n = $Name -replace '[\/:*?"<>|]', '_'
    $n = $n.Trim().TrimEnd('.')
    if ([string]::IsNullOrWhiteSpace($n)) { $n = 'Project' }
    return $n
}

function Ensure-Directory {
    param([Parameter(Mandatory)][string]$Dir)
    if (-not (Test-Path -LiteralPath $Dir)) {
        New-Item -ItemType Directory -Path $Dir -Force | Out-Null
    }
}

function SafeJoin {
    param(
        [Parameter(Mandatory)][string]$Base,
        [Parameter(Mandatory)][string]$Child
    )
    return (Join-Path -Path $Base -ChildPath $Child)
}

# ---------- BAT integration ----------
# Use the script's directory as the root that contains the BAT file.
$RemoteBatchRoot = $PSScriptRoot
$RemoteBatchFile = "RealityMeshProcess.bat"                                        # BAT filename
[bool]$UseTclDirect = $false  # when true, use old TCL path; default is BAT mode

# ---------- Shared roots (MUST include server name) ----------
# Base shared drive accessible by both the calling and remote machines
$sharedRoot = '\\HAMMERKIT1-4\SharedMeshDrive\RealityMesh'
$inputRoot  = Join-Path $sharedRoot 'Input'
$outputRoot = Join-Path $sharedRoot 'Output'

Ensure-Directory $sharedRoot
Ensure-Directory $inputRoot
Ensure-Directory $outputRoot

# ---------- Prompt/defaults ----------
if ([string]::IsNullOrEmpty($project_settings_File)) {
    throw "Project settings file path is required. Pass it as the first arg."
}
$fully_automate = 1
$project_settings_File = Normalize-UNCPath ($project_settings_File.Trim('"'))

# ---------- Settings Parsing ----------
$system_settings = "$PSScriptRoot/RealityMeshSystemSettings.txt"

if (-not (Test-Path -LiteralPath $project_settings_File)) {
    throw "project settings file does not exist: $project_settings_File"
}

if (-not (Test-Path -LiteralPath $system_settings)) {
    throw "System settings file does not exist: $system_settings"
}

Write-Host "Project and System settings found" -ForegroundColor Green

# Determine the location of the RealityMesh_tt template folder.
$RealityMeshTTPath = Join-Path $PSScriptRoot 'RealityMesh_tt'
$defaultRealityMeshTTPath = "C:\Program Files (x86)\STE Toolkit\RealityMesh_tt"
if (-not (Test-Path -LiteralPath $RealityMeshTTPath)) {
    if (Test-Path -LiteralPath $defaultRealityMeshTTPath) {
        $RealityMeshTTPath = $defaultRealityMeshTTPath
    } else {
        throw "RealityMesh_tt folder not found at '$RealityMeshTTPath' or '$defaultRealityMeshTTPath'"
    }
}

# ---------- Project settings ----------
$project_name = Sanitize-Name ((Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^project_name=" }) -replace "project_name=", "")
$source_Directory_temp = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^source_Directory=" }) -replace "source_Directory=", ""
$source_Directory = Normalize-UNCPath $source_Directory_temp

# Validate data folder
if (-not (Test-Path -LiteralPath $source_Directory)) {
    throw "source_Directory not found: $source_Directory"
}
$objFiles = @(Get-ChildItem -Path $source_Directory -Filter *.obj -Recurse -ErrorAction SilentlyContinue)
$lasFiles = @(Get-ChildItem -Path $source_Directory -Filter *.las -Recurse -ErrorAction SilentlyContinue)
$objCount = $objFiles.Count
$lasCount = $lasFiles.Count
Write-Output "Data folder: $source_Directory — Found $objCount OBJ, $lasCount LAS"
if ($objCount -eq 0 -and $lasCount -eq 0) {
    throw "No *.obj/*.las found under: $source_Directory. Make sure your data folder points to the correct location."
}

# Locate Output-CenterPivotOrigin.json if available
$ocpo = Get-ChildItem -Path $source_Directory -Filter "Output-CenterPivotOrigin.json" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1

$sel_Area_Size         = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^sel_Area_Size=" }) -replace "sel_Area_Size=", ""
$offset_coordsys       = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^offset_coordsys=" }) -replace "offset_coordsys=", ""
$offset_hdatum         = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^offset_hdatum=" }) -replace "offset_hdatum=", ""
$offset_vdatum         = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^offset_vdatum=" }) -replace "offset_vdatum=", ""
$offset_x              = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^offset_x=" }) -replace "offset_x=", ""
$offset_y              = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^offset_y=" }) -replace "offset_y=", ""
$offset_z              = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^offset_z=" }) -replace "offset_z=", ""
$orthocam_Resolution   = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^orthocam_Resolution=" }) -replace "orthocam_Resolution=", ""
$orthocam_Render_Lowest= (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^orthocam_Render_Lowest=" }) -replace "orthocam_Render_Lowest=", ""
$tin_to_dem_Resolution = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^tin_to_dem_Resolution=" }) -replace "tin_to_dem_Resolution=", ""
$tile_scheme           = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^tile_scheme=" }) -replace "tile_scheme=", ""
$collision             = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^collision=" }) -replace "collision=", ""
$visualLODs            = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^visualLODs=" }) -replace "visualLODs=", ""
$project_vdatum        = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^project_vdatum=" }) -replace "project_vdatum=", ""
$offset_models         = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^offset_models=" }) -replace "offset_models=", ""
$csf_options           = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^csf_options=" }) -replace "csf_options=", ""
$faceThresh            = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^faceThresh=" }) -replace "faceThresh=", ""
$lodThresh             = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^lodThresh=" }) -replace "lodThresh=", ""
$tileSize              = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^tileSize=" }) -replace "tileSize=", ""
$srfResolution         = (Get-Content -LiteralPath $project_settings_File | Where-Object { $_ -match "^srfResolution=" }) -replace "srfResolution=", ""

# Override offsets from Output-CenterPivotOrigin.json and derive project name
if ($ocpo) {
    $projectRoot = Split-Path $ocpo.DirectoryName -Parent
    if ((Split-Path $ocpo.DirectoryName -Leaf) -like "Build_*") {
        $projectRoot = Split-Path $projectRoot -Parent
    }
    $derivedName = Split-Path $projectRoot -Leaf
    if ($derivedName) {
        $project_name = Sanitize-Name $derivedName
    }
    try {
        $json = Get-Content -LiteralPath $ocpo.FullName -Raw | ConvertFrom-Json

        $tmp = $json.offset_x
        if ($null -eq $tmp) { $tmp = $json.x }
        if ($null -eq $tmp -and $json.offset) { $tmp = $json.offset.x }
        if ($null -ne $tmp) { $offset_x = $tmp }

        $tmp = $json.offset_y
        if ($null -eq $tmp) { $tmp = $json.y }
        if ($null -eq $tmp -and $json.offset) { $tmp = $json.offset.y }
        if ($null -ne $tmp) { $offset_y = $tmp }

        $tmp = $json.offset_z
        if ($null -eq $tmp) { $tmp = $json.z }
        if ($null -eq $tmp -and $json.offset) { $tmp = $json.offset.z }
        if ($null -ne $tmp) { $offset_z = $tmp }

        $tmp = $json.offset_coordsys
        if ($null -eq $tmp) { $tmp = $json.coordinateSystem }
        if ($null -eq $tmp) { $tmp = $json.coordSystem }
        if ($null -ne $tmp) { $offset_coordsys = $tmp }

        $tmp = $json.offset_hdatum
        if ($null -eq $tmp) { $tmp = $json.horizontalDatum }
        if ($null -eq $tmp) { $tmp = $json.hdatum }
        if ($null -ne $tmp) { $offset_hdatum = $tmp }

        $tmp = $json.offset_vdatum
        if ($null -eq $tmp) { $tmp = $json.verticalDatum }
        if ($null -eq $tmp) { $tmp = $json.vdatum }
        if ($null -ne $tmp) { $offset_vdatum = $tmp }
    } catch {
        Write-Warning "Failed to parse offsets from $($ocpo.FullName): $_"
    }
}

# ---------- System settings ----------
$blender_path = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^blender_path=" }) -replace "blender_path=", ""
$default_blender = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
if (!(Test-Path -LiteralPath $blender_path)) {
    if (Test-Path -LiteralPath $default_blender) {
        $blender_path = $default_blender
        Write-Output "Using Blender found at $blender_path"
    } else {
        $search = Get-ChildItem "C:\Program Files\Blender Foundation" -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName 'blender.exe' } |
            Where-Object { Test-Path $_ } |
            Select-Object -First 1
        if ($search) {
            $blender_path = $search
            Write-Output "Using Blender found at $blender_path"
        } else {
            throw "Blender Path invalid"
        }
    }
}
$blender_threads               = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^blender_threads=" }) -replace "blender_threads=", ""
$override_Installation_VBS4    = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^override_Installation_VBS4=" }) -replace "override_Installation_VBS4=", ""
$override_Path_VBS4            = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^override_Path_VBS4=" }) -replace "override_Path_VBS4=", ""
if (($override_Installation_VBS4 -eq 1) -and !(Test-Path -LiteralPath $override_Path_VBS4)) {
    throw "VBS4 path invalid"
}
$vbs4_version                  = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^vbs4_version=" }) -replace "vbs4_version=", ""
$override_Installation_DevSuite= (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^override_Installation_DevSuite=" }) -replace "override_Installation_DevSuite=", ""
$override_Path_DevSuite        = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^override_Path_DevSuite=" }) -replace "override_Path_DevSuite=", ""
$terratools_home_path          = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^terratools_home_path=" }) -replace "terratools_home_path=", ""
$terratools_ssh_path           = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^terratools_ssh_path=" }) -replace "terratools_ssh_path=", ""
if (!(Test-Path -LiteralPath $terratools_ssh_path)) {
    throw "Terratools Path invalid: $terratools_ssh_path"
}

# ---------- Handle project name conflicts ----------
if (Test-Path (Join-Path $inputRoot $project_name)) {
    $project_name = "{0}_{1}" -f $project_name, (Get-Date -Format "yyyyMMdd_HHmmss")
}
Ensure-Directory "$PSScriptRoot\ProjectSettings\GeneratedFiles_DoNotEdit"
New-Item -Path "$PSScriptRoot\ProjectSettings\GeneratedFiles_DoNotEdit\AutomationHelper.txt" -ItemType "File" -Value "$project_name" -Force | Out-Null

# ---------- Cleanup DevSuite temp ----------
$deletePath  = "${override_Path_DevSuite}:\temp\RealityMesh\$project_name\"
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

# ---------- Build generated settings & output destinations ----------
$projectFolder = Join-Path $inputRoot $project_name
Ensure-Directory $projectFolder

$generated_settings_file = Join-Path $projectFolder "$project_name.txt"
if (Test-Path -LiteralPath $generated_settings_file) {
    Remove-Item -LiteralPath $generated_settings_file -Force
}

$override_Installation_VBS4_bool = if ($override_Installation_VBS4 -eq 1) { "true" } else { "false" }

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$out_in_name = "$project_name"
$out_in_name_with_drive = Join-Path $outputRoot "${project_name}_$timestamp"
Ensure-Directory $out_in_name_with_drive

Write-Output "ProjectName: $project_name"
Write-Output "DestDir: $out_in_name_with_drive"
Write-Output "GeneratedSettingsFile: $generated_settings_file"

# Create settings file
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

# ---------- Build key=value settings for BAT ----------
$kvSettingsLocal = Join-Path $projectFolder ("{0}-settings.txt" -f $project_name)
$kvLines = @(
    "project_name=$project_name",
    "source_Directory=$source_Directory",
    "offset_coordsys=$offset_coordsys",
    "offset_hdatum=$offset_hdatum",
    "offset_vdatum=$offset_vdatum",
    "offset_x=$offset_x",
    "offset_y=$offset_y",
    "offset_z=$offset_z",
    "orthocam_Resolution=$orthocam_Resolution",
    "orthocam_Render_Lowest=$orthocam_Render_Lowest",
    "tin_to_dem_Resolution=$tin_to_dem_Resolution",
    "sel_Area_Size=$sel_Area_Size",
    "tile_scheme=$tile_scheme",
    "collision=$collision",
    "visualLODs=$visualLODs",
    "project_vdatum=$project_vdatum",
    "offset_models=$offset_models",
    "csf_options=$csf_options",
    "faceThresh=$faceThresh",
    "lodThresh=$lodThresh",
    "tileSize=$tileSize",
    "srfResolution=$srfResolution"
)
$kvLines | Out-File -LiteralPath $kvSettingsLocal -Encoding UTF8 -Force

# Place settings on top of the BAT folder
if (-not (Test-Path -LiteralPath $RemoteBatchRoot)) { throw "BAT root not found: $RemoteBatchRoot" }
$BatSettingsPath = Join-Path $RemoteBatchRoot ("{0}-settings.txt" -f $project_name)
Copy-Item -LiteralPath $kvSettingsLocal -Destination $BatSettingsPath -Force

$command_path = $generated_settings_file

# ---------- Copy project template ----------
$templatePath = $RealityMeshTTPath
$destinationPath = $projectFolder
if (Test-Path -LiteralPath $templatePath) {
    $rc = @('robocopy', ('"'+$templatePath+'"'), ('"'+$destinationPath+'"'),
            '*.*','/E','/DCOPY:DA','/COPY:DAT','/R:3','/W:5') -join ' '
    cmd /c $rc | Out-Host
} else {
    throw "Template folder not found at $templatePath"
}

Set-Location -LiteralPath $destinationPath

# Rename .ttp safely
$ttp = Join-Path $destinationPath 'RealityMeshProcess.ttp'
if (Test-Path -LiteralPath $ttp) {
    Rename-Item -LiteralPath $ttp -NewName "$project_name.ttp" -Force
} else {
    Write-Warning "Template .ttp not found at $ttp"
}

# Write small config files
"set sourceDir `"$source_Directory`" " | Out-File -LiteralPath (Join-Path $destinationPath 'sourceDir.txt') -Encoding Default
"set tileScheme `"$tile_scheme`" "   | Out-File -LiteralPath (Join-Path $destinationPath 'tileScheme.txt') -Encoding Default

# Ensure n33.tbr exists before running the main TCL script
$n33File = Join-Path $destinationPath 'n33.tbr'
if (-not (Test-Path -LiteralPath $n33File)) {
    Write-Host "n33.tbr not found. Generating with TSG_TBR_to_Vertex_Points_Unique.tcl..." -ForegroundColor Yellow

    $ttScript  = Join-Path $destinationPath 'TSG_TBR_to_Vertex_Points_Unique.tcl'
    $inputTbr  = Join-Path $destinationPath 'n32.tbr'
    $ttShell   = $terratools_ssh_path

    if (Test-Path -LiteralPath $inputTbr) {
        $ttArgs = "`"$ttScript`" `"$inputTbr`" `"$n33File`""
        $proc   = Start-Process -FilePath $ttShell -ArgumentList $ttArgs -NoNewWindow -Wait -PassThru

        if ($proc.ExitCode -ne 0) {
            Write-Host "Failed to generate n33.tbr via TerraTools" -ForegroundColor Red
        }
    } else {
        Write-Host "Required input TBR not found: $inputTbr" -ForegroundColor Red
    }
}

if (-not (Test-Path -LiteralPath $n33File)) {
    Write-Host "ERROR: Required file n33.tbr could not be created." -ForegroundColor Red
    throw "Required file n33.tbr could not be created"
}

# TERRATOOLS_HOME override
if (!([string]::IsNullOrEmpty($terratools_home_path)) -and (Test-Path -LiteralPath $terratools_home_path)) {
    Write-Output "Using custom TERRATOOLS_HOME path at $terratools_home_path"
    $env:TERRASIM_HOME = $terratools_home_path
}

# ---------- Run the process ----------
if (-not $UseTclDirect) {
    $batPath = Join-Path $RemoteBatchRoot $RemoteBatchFile
    if (-not (Test-Path -LiteralPath $batPath)) { throw "BAT not found: $batPath" }
    Write-Host "Starting Reality Mesh BAT..." -ForegroundColor Cyan
    $startTime = Get-Date
    $p = Start-Process -FilePath $batPath -NoNewWindow -PassThru
    $p.WaitForExit()
    if ($LASTEXITCODE -ne 0 -and $p.ExitCode -ne 0) {
        throw "Reality Mesh BAT returned code $($p.ExitCode)"
    }
    $minutes = ((Get-Date) - $startTime).TotalSeconds / 60
    "Time to run BAT: $minutes minutes" | Out-File -LiteralPath (Join-Path $destinationPath 'TimingLog.txt') -Encoding Default -Append
} else {
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
    "Time to run TT project: $minutes minutes" | Out-File -LiteralPath (Join-Path $destinationPath 'TimingLog.txt') -Encoding Default -Append
}

# ---------- Signal completion for remote monitors ----------
$doneFile = Join-Path $out_in_name_with_drive 'DONE.txt'
New-Item -ItemType File -Path $doneFile -Force | Out-Null
Write-Output "Created $doneFile"
