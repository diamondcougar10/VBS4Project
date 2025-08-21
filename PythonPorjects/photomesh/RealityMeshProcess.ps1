[CmdletBinding()]
param(
  [Parameter(Mandatory = $true, Position = 0)]
  [string]$SettingsFile,
  [Parameter(Position = 1)]
  [string]$FullyAutomate = '1'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$errors = $null; $tokens = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$tokens, [ref]$errors)
if ($errors -and $errors.Count -gt 0) {
  Write-Error ('Self-parse check failed at line {0}: {1}' -f $errors[0].Extent.StartLineNumber, $errors[0].Message)
  exit 2
}

# =========================
# Reality Mesh Runner (fixed UNC + robust paths)
# =========================

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
    # Remove invalid filename chars: \ / : * ? " < > | ( ) and trailing dots/spaces
    $n = $Name -replace '[\/:*?"<>|()]', '_'
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

function Resolve-TerraToolsPaths {
    param(
        [string]$SshPath,
        [string]$HomeHint
    )
    # Build ordered candidate TerraTools roots
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($HomeHint) { $candidates.Add($HomeHint) }

    if ($SshPath -and (Test-Path -LiteralPath $SshPath)) {
        # ...\TerraTools\bin\terratoolssh.exe -> ...\TerraTools
        $exeRoot = Split-Path -Parent (Split-Path -Parent $SshPath)
        if ($exeRoot) { $candidates.Add($exeRoot) }
    }

    $candidates.Add('C:\Program Files\Bohemia Interactive Simulations\TerraTools')
    $candidates.Add('C:\Program Files (x86)\Bohemia Interactive Simulations\TerraTools')

    # Dedup, keep order
    $seen=@{}; $ordered=@()
    foreach ($c in $candidates) { if ($c -and -not $seen.ContainsKey($c)) { $ordered += $c; $seen[$c]=$true } }

    foreach ($root in $ordered | Where-Object { Test-Path -LiteralPath $_ }) {
        $tcl1 = Join-Path $root 'tcl\tsdcore.tcl'
        $tcl2 = Join-Path $root 'lib\terratools\tcl\tsdcore.tcl'
        if (Test-Path -LiteralPath $tcl1) { return [pscustomobject]@{ Root=$root; TclFile=$tcl1; TclDir=(Split-Path -Parent $tcl1) } }
        if (Test-Path -LiteralPath $tcl2) { return [pscustomobject]@{ Root=$root; TclFile=$tcl2; TclDir=(Split-Path -Parent $tcl2) } }
    }

    # Last-ditch recursive search under first existing candidate
    $firstExisting = $ordered | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($firstExisting) {
        $hit = Get-ChildItem -LiteralPath $firstExisting -Recurse -Filter 'tsdcore.tcl' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return [pscustomobject]@{ Root=$firstExisting; TclFile=$hit.FullName; TclDir=(Split-Path -Parent $hit.FullName) } }
    }
    return $null
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
$SettingsFile = Normalize-UNCPath ($SettingsFile.Trim('"'))

# We are in second stage if the settings file is the kv file inside the BAT folder
$settingsLeaf   = Split-Path -Leaf   $SettingsFile
$settingsParent = Split-Path -Parent $SettingsFile
$IsSecondStage  = ($settingsParent -ieq $RemoteBatchRoot) -and ($settingsLeaf -match '-settings\.txt$')

# ---------- Settings Parsing ----------
$system_settings = Join-Path $PSScriptRoot 'RealityMeshSystemSettings.txt'

if (-not (Test-Path -LiteralPath $SettingsFile)) {
    throw ('project settings file does not exist: {0}' -f $SettingsFile)
}

if (-not (Test-Path -LiteralPath $system_settings)) {
    throw ('System settings file does not exist: {0}' -f $system_settings)
}

Write-Output ('Using settings: {0}' -f $SettingsFile)
Write-Host 'Project and System settings found' -ForegroundColor Green

# ---------- Locate RealityMesh_tt (portable-first, robust fallbacks) ----------
function Resolve-RealityMeshTTPath {
    param([Parameter(Mandatory)] [string]$ScriptRoot)
    $portable1    = Join-Path $ScriptRoot 'RealityMesh_tt'
    $portable2    = Join-Path (Split-Path $ScriptRoot -Parent) 'RealityMesh_tt'
    $envHome      = $env:STE_TOOLKIT_HOME
    $envPath      = if ($envHome) { Join-Path $envHome 'RealityMesh_tt' } else { $null }
    $installedNew = 'C:\Program Files (x86)\STE Toolkit\_internal\photomesh\RealityMesh_tt'
    $installedOld = 'C:\Program Files (x86)\STE Toolkit\RealityMesh_tt'

    $candidates = @($portable1, $portable2, $envPath, $installedNew, $installedOld) |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

    foreach ($p in $candidates) {
        if (Test-Path -LiteralPath $p -PathType Container) {
            $tcl = Join-Path $p 'RealityMeshProcess.tcl'
            if (Test-Path -LiteralPath $tcl -PathType Leaf) {
                if ($p -ieq $portable1 -or $p -ieq $portable2) {
                    Write-Host ("Using template path (portable): {0}" -f $p) -ForegroundColor Green
                } elseif ($p -ieq $installedNew -or $p -ieq $installedOld) {
                    Write-Host ("Using template path (installed): {0}" -f $p) -ForegroundColor Yellow
                } else {
                    Write-Host ("Using template path: {0}" -f $p) -ForegroundColor Green
                }
                return $p
            } else {
                Write-Warning ("Found RealityMesh_tt at '{0}' but it is missing RealityMeshProcess.tcl; skipping." -f $p)
            }
        }
    }

    $msg = @"
RealityMesh_tt folder not found with required files.
Tried:
 - $portable1
 - $portable2
 - $envPath
 - $installedNew
 - $installedOld
"@
    throw $msg
}

$RealityMeshTTPath = Resolve-RealityMeshTTPath -ScriptRoot $PSScriptRoot


# ---------- Project settings ----------
$project_name = Sanitize-Name ((Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^project_name=" }) -replace "project_name=", "")
$source_Directory_temp = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^source_Directory=" }) -replace "source_Directory=", ""
$source_Directory = Normalize-UNCPath $source_Directory_temp

# Validate data folder
if (-not (Test-Path -LiteralPath $source_Directory)) {
    throw ('source_Directory not found: {0}' -f $source_Directory)
}
$objFiles = @(Get-ChildItem -Path $source_Directory -Filter *.obj -Recurse -ErrorAction SilentlyContinue)
$lasFiles = @(Get-ChildItem -Path $source_Directory -Filter *.las -Recurse -ErrorAction SilentlyContinue)
$objCount = $objFiles.Count
$lasCount = $lasFiles.Count
Write-Output ('Data folder: {0} - Found {1} OBJ, {2} LAS' -f $source_Directory, $objCount, $lasCount)
if ($objCount -eq 0 -and $lasCount -eq 0) {
    throw ('No *.obj/*.las found under: {0}. Make sure your data folder points to the correct location.' -f $source_Directory)
}

# Locate Output-CenterPivotOrigin.json if available
$ocpo = Get-ChildItem -Path $source_Directory -Filter "Output-CenterPivotOrigin.json" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1

$sel_Area_Size         = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^sel_Area_Size=" }) -replace "sel_Area_Size=", ""
$offset_coordsys       = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^offset_coordsys=" }) -replace "offset_coordsys=", ""
$offset_hdatum         = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^offset_hdatum=" }) -replace "offset_hdatum=", ""
$offset_vdatum         = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^offset_vdatum=" }) -replace "offset_vdatum=", ""
$offset_x              = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^offset_x=" }) -replace "offset_x=", ""
$offset_y              = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^offset_y=" }) -replace "offset_y=", ""
$offset_z              = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^offset_z=" }) -replace "offset_z=", ""
$orthocam_Resolution   = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^orthocam_Resolution=" }) -replace "orthocam_Resolution=", ""
$orthocam_Render_Lowest= (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^orthocam_Render_Lowest=" }) -replace "orthocam_Render_Lowest=", ""
$tin_to_dem_Resolution = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^tin_to_dem_Resolution=" }) -replace "tin_to_dem_Resolution=", ""
$tile_scheme           = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^tile_scheme=" }) -replace "tile_scheme=", ""
$collision             = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^collision=" }) -replace "collision=", ""
$visualLODs            = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^visualLODs=" }) -replace "visualLODs=", ""
$project_vdatum        = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^project_vdatum=" }) -replace "project_vdatum=", ""
$offset_models         = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^offset_models=" }) -replace "offset_models=", ""
$csf_options           = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^csf_options=" }) -replace "csf_options=", ""
$faceThresh            = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^faceThresh=" }) -replace "faceThresh=", ""
$lodThresh             = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^lodThresh=" }) -replace "lodThresh=", ""
$tileSize              = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^tileSize=" }) -replace "tileSize=", ""
$srfResolution         = (Get-Content -LiteralPath $SettingsFile | Where-Object { $_ -match "^srfResolution=" }) -replace "srfResolution=", ""

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
        Write-Warning ('Failed to parse offsets from {0}: {1}' -f $ocpo.FullName, $_)
    }
}

# ---------- Stable run id & locations ----------
$RunId = Get-Date -Format 'yyyyMMdd_HHmmss'
$BaseName = ($project_name -replace '(_\d{8}_\d{6})+$','')
if ($BaseName.Length -gt 48) { $BaseName = $BaseName.Substring(0,48) }
if ($IsSecondStage) {
    $ProjectAlias = $project_name
} else {
    $ProjectAlias = '{0}_{1}' -f $BaseName, $RunId
}
$project_name  = $ProjectAlias
$projectFolder = Join-Path $inputRoot $ProjectAlias
$OutputDir     = Join-Path $outputRoot $ProjectAlias
Ensure-Directory $projectFolder
Ensure-Directory $OutputDir
if ((Join-Path $projectFolder ("{0}.txt" -f $ProjectAlias)).Length -ge 240) {
    throw "Project path too long. Please shorten project_name (current base: '$BaseName')."
}
$generated_settings_file = Join-Path $projectFolder ("{0}.txt" -f $ProjectAlias)

# ---------- System settings ----------
$blender_path = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^blender_path=" }) -replace "blender_path=", ""
$default_blender = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
if (!(Test-Path -LiteralPath $blender_path)) {
    if (Test-Path -LiteralPath $default_blender) {
        $blender_path = $default_blender
        Write-Output ('Using Blender found at {0}' -f $blender_path)
    } else {
        $search = Get-ChildItem "C:\Program Files\Blender Foundation" -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName 'blender.exe' } |
            Where-Object { Test-Path $_ } |
            Select-Object -First 1
        if ($search) {
            $blender_path = $search
            Write-Output ('Using Blender found at {0}' -f $blender_path)
        } else {
            throw 'Blender Path invalid'
        }
    }
}
$blender_threads               = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^blender_threads=" }) -replace "blender_threads=", ""
$override_Installation_VBS4    = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^override_Installation_VBS4=" }) -replace "override_Installation_VBS4=", ""
$override_Path_VBS4            = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^override_Path_VBS4=" }) -replace "override_Path_VBS4=", ""
if (($override_Installation_VBS4 -eq 1) -and !(Test-Path -LiteralPath $override_Path_VBS4)) {
    throw 'VBS4 path invalid'
}
$vbs4_version                  = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^vbs4_version=" }) -replace "vbs4_version=", ""
$override_Installation_DevSuite= (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^override_Installation_DevSuite=" }) -replace "override_Installation_DevSuite=", ""
$override_Path_DevSuite        = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^override_Path_DevSuite=" }) -replace "override_Path_DevSuite=", ""
$terratools_home_path          = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^terratools_home_path=" }) -replace "terratools_home_path=", ""
$terratools_ssh_path           = (Get-Content -LiteralPath $system_settings | Where-Object { $_ -match "^terratools_ssh_path=" }) -replace "terratools_ssh_path=", ""
if (!(Test-Path -LiteralPath $terratools_ssh_path)) {
    throw ('Terratools Path invalid: {0}' -f $terratools_ssh_path)
}

# ---------- Handle project name conflicts ----------
# Uniqueness handled by $ProjectAlias; no further mutation required.
$genDir = Join-Path $PSScriptRoot 'ProjectSettings'
$genDir = Join-Path $genDir 'GeneratedFiles_DoNotEdit'
Ensure-Directory $genDir
New-Item -Path (Join-Path $genDir 'AutomationHelper.txt') -ItemType File -Value $project_name -Force | Out-Null

# --- DevSuite cleanup (always P:\) ---
# We no longer try to infer a drive; DevSuite lives on P:\ in production.
$devsuiteRoot = 'P:\'

if ($override_Installation_DevSuite -eq 1) {
    if (-not (Test-Path -LiteralPath $devsuiteRoot)) {
        Write-Warning "DevSuite root P:\ not found; skipping DevSuite-specific cleanup."
    } else {
        $structuresPath = Join-Path $devsuiteRoot 'vbs2\customer\structures'
        $structuresProj = Join-Path $structuresPath $project_name

        if (Test-Path -LiteralPath $structuresProj) {
            Write-Output "Deleting $structuresProj"
            Remove-Item -LiteralPath $structuresProj -Recurse -Force
        } else {
            Write-Host "No existing structures dir for $project_name; skipping." -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "DevSuite cleanup disabled (override_Installation_DevSuite != 1); skipping." -ForegroundColor Yellow
}

if (-not $IsSecondStage) {
    # ---------- Build generated settings & output destinations ----------
    if (Test-Path -LiteralPath $generated_settings_file) {
        Remove-Item -LiteralPath $generated_settings_file -Force
    }

    $override_Installation_VBS4_bool = if ($override_Installation_VBS4 -eq 1) { "true" } else { "false" }

    $out_in_name = $ProjectAlias
    $out_in_name_with_drive = $OutputDir

    Write-Output ('ProjectName: {0}' -f $ProjectAlias)
    Write-Output ('DestDir: {0}' -f $OutputDir)
    Write-Output ('GeneratedSettingsFile: {0}' -f $generated_settings_file)

    # Create settings file
    New-Item -ItemType File -Path $generated_settings_file -Force | Out-Null
    Add-Content -LiteralPath $generated_settings_file -Value "set name {$ProjectAlias}"
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
    $kvSettingsLocal = Join-Path $projectFolder ("{0}-settings.txt" -f $ProjectAlias)
    $kvLines = @(
        "project_name=$ProjectAlias",
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
    if (-not (Test-Path -LiteralPath $RemoteBatchRoot)) { throw ('BAT root not found: {0}' -f $RemoteBatchRoot) }
    $BatSettingsPath = Join-Path $RemoteBatchRoot ("{0}-settings.txt" -f $ProjectAlias)
    Copy-Item -LiteralPath $kvSettingsLocal -Destination $BatSettingsPath -Force

    $command_path = $generated_settings_file

    # ---------- Copy project template ----------
    $templatePath = $RealityMeshTTPath
    $destinationPath = $projectFolder
    if (Test-Path -LiteralPath $templatePath) {
        & robocopy $templatePath $destinationPath *.* /E /DCOPY:DA /COPY:DAT /R:3 /W:5 | Out-Host
        $expectedTcl = Join-Path $destinationPath 'RealityMeshProcess.tcl'
        if (-not (Test-Path -LiteralPath $expectedTcl)) {
            throw ("Expected file not copied: {0}" -f $expectedTcl)
        }
    } else {
        throw ('Template folder not found at {0}' -f $templatePath)
    }

    Set-Location -LiteralPath $destinationPath

    # Rename .ttp safely
    $ttp = Join-Path $destinationPath 'RealityMeshProcess.ttp'
    if (Test-Path -LiteralPath $ttp) {
        Rename-Item -LiteralPath $ttp -NewName ('{0}.ttp' -f $project_name) -Force
    } else {
        Write-Warning ('Template .ttp not found at {0}' -f $ttp)
    }

    # Write small config files
    "set sourceDir `"$source_Directory`" " | Out-File -LiteralPath (Join-Path $destinationPath 'sourceDir.txt') -Encoding Default
    "set tileScheme `"$tile_scheme`" "   | Out-File -LiteralPath (Join-Path $destinationPath 'tileScheme.txt') -Encoding Default

    # --- n33.tbr generation is ONLY needed for the legacy TCL path ---
    if ($UseTclDirect) {
        $n33File = Join-Path $destinationPath 'n33.tbr'
        if (-not (Test-Path -LiteralPath $n33File)) {
            Write-Host 'n33.tbr not found. Generating with TSG_TBR_to_Vertex_Points_Unique.tcl...' -ForegroundColor Yellow

            $ttScript = Join-Path $destinationPath 'TSG_TBR_to_Vertex_Points_Unique.tcl'
            $inputTbr = Join-Path $destinationPath 'n32.tbr'

            if (Test-Path -LiteralPath $inputTbr) {
                $proc = Start-Process -FilePath $terratools_ssh_path `
                                      -ArgumentList @($ttScript, $inputTbr, $n33File) `
                                      -NoNewWindow -Wait -PassThru
                if ($proc.ExitCode -ne 0) {
                    Write-Warning "TerraTools returned $($proc.ExitCode) while generating n33.tbr"
                }
            } else {
                Write-Warning "Skipping n33.tbr generation: required input not found: $inputTbr"
            }
        }

        if (-not (Test-Path -LiteralPath $n33File)) {
            Write-Host 'ERROR: Required file n33.tbr could not be created for TCL path.' -ForegroundColor Red
            throw 'Required file n33.tbr could not be created'
        }
    } else {
        Write-Host 'Skipping n33.tbr generation (BAT mode does not require it).' -ForegroundColor Yellow
    }
}

# ---------- TerraTools environment resolution (handles both tcl\ and lib\terratools\tcl\ layouts) ----------
$tt = Resolve-TerraToolsPaths -SshPath $terratools_ssh_path -HomeHint $terratools_home_path
if (-not $tt) {
    $tried = @(
        $terratools_home_path,
        (if ($terratools_ssh_path) { (Split-Path -Parent (Split-Path -Parent $terratools_ssh_path)) }),
        'C:\Program Files\Bohemia Interactive Simulations\TerraTools',
        'C:\Program Files (x86)\Bohemia Interactive Simulations\TerraTools'
    ) | Where-Object { $_ } | Select-Object -Unique
    throw ("TerraTools Tcl core (tsdcore.tcl) not found. Tried:`n - " + ($tried -join "`n - "))
}

# Set env for current process (child processes inherit)
$terraSimHome        = Split-Path -Parent $tt.TclDir
$env:TERRASIM_HOME   = $terraSimHome
$env:TERRATOOLS_HOME = $tt.Root
$env:TCLLIBPATH      = $tt.TclDir

# Ensure bin on PATH
$terraBin = Join-Path $tt.Root 'bin'
if (Test-Path -LiteralPath $terraBin) {
    if (-not (($env:PATH -split ';') | Where-Object { $_ -ieq $terraBin })) {
        $env:PATH = $env:PATH + ';' + $terraBin
    }
}

# If configured ssh exe doesn’t exist, repair it from resolved root
if (-not (Test-Path -LiteralPath $terratools_ssh_path)) {
    $candidateSsh = Join-Path $terraBin 'terratoolssh.exe'
    if (Test-Path -LiteralPath $candidateSsh) {
        $terratools_ssh_path = $candidateSsh
        Write-Host ("Resolved terratools_ssh_path -> {0}" -f $terratools_ssh_path) -ForegroundColor Yellow
    } else {
        throw ("Terratools Path invalid: {0} (also not found at {1})" -f $terratools_ssh_path, $candidateSsh)
    }
}

Write-Host ("[TerraTools] Home : {0}" -f $tt.Root)    -ForegroundColor Green
Write-Host ("[TerraTools] Tcl  : {0}" -f $tt.TclFile) -ForegroundColor Green
Write-Host ("[TerraTools] Bin  : {0}" -f $terraBin)   -ForegroundColor Green

# ---------- Second stage: run TerraTools directly ----------
if ($IsSecondStage) {
    Write-Host 'Running TerraTools (second stage)...'

    $projDir     = $projectFolder
    $tclPath     = Join-Path $projDir 'RealityMeshProcess.tcl'
    $cmdFilePath = $generated_settings_file
    $cmdFileName = Split-Path $cmdFilePath -Leaf

    if (-not (Test-Path -LiteralPath $tclPath))     { throw "TCL not found: $tclPath" }
    if (-not (Test-Path -LiteralPath $cmdFilePath)) { throw "Command file not found: $cmdFilePath" }

    $proc = Start-Process -FilePath $terratools_ssh_path `
        -WorkingDirectory $projDir `
        -ArgumentList @($tclPath, '-cwd', $projDir, '-command_file', $cmdFileName) `
        -NoNewWindow -Wait -PassThru

    if ($proc.ExitCode -ne 0) {
        throw ("TerraTools returned {0}. Check license and files in: {1}" -f $proc.ExitCode, $projDir)
    }

    # Optional DONE marker
    $doneFile = Join-Path $OutputDir 'DONE.txt'
    New-Item -ItemType File -Path $doneFile -Force | Out-Null
    Write-Output "Created $doneFile"
    return
}

# ---------- Run the process ----------
if (-not $UseTclDirect) {
    $batPath = Join-Path $RemoteBatchRoot $RemoteBatchFile
    $BatSettingsPath = Join-Path $RemoteBatchRoot ("{0}-settings.txt" -f $project_name)

    Write-Host 'Starting Reality Mesh BAT...' -ForegroundColor Cyan
    $startTime = Get-Date
    $p = Start-Process -FilePath $batPath `
                       -ArgumentList @($BatSettingsPath) `
                       -WorkingDirectory $RemoteBatchRoot `
                       -NoNewWindow -PassThru
    $p.WaitForExit()
    if ($p.ExitCode -ne 0) { throw ("Reality Mesh BAT returned code {0}" -f $p.ExitCode) }
    $minutes = ((Get-Date) - $startTime).TotalSeconds / 60
    "Time to run BAT: $minutes minutes" | Out-File -LiteralPath (Join-Path $destinationPath 'TimingLog.txt') -Encoding Default -Append
} else {
    Write-Host ('Launching RealityMeshProcess.tcl with settings from {0}' -f $command_path) -ForegroundColor Cyan
    Write-Host 'Processing Reality Mesh... Please wait. Do not close this window.' -ForegroundColor Yellow
    Start-Sleep -Seconds 2

    $startTime = Get-Date
    $proc = Start-Process -FilePath $terratools_ssh_path -NoNewWindow -PassThru -ArgumentList @('RealityMeshProcess.tcl','-command_file',$command_path)
    $spinner = '/-\|'
    $i = 0
    while (-not $proc.HasExited) {
        $char = $spinner[$i % $spinner.Length]
        Write-Host -NoNewline ("`r{0} Processing..." -f $char)
        Start-Sleep -Seconds 1
        $i++
    }
    $proc.WaitForExit()
    Write-Host "`rProcessing complete.             "
    $time = (Get-Date) - $startTime
    $minutes = $time.TotalSeconds / 60
    Write-Output ('`nTime to run TT project: {0} minutes' -f $minutes)
    "Time to run TT project: $minutes minutes" | Out-File -LiteralPath (Join-Path $destinationPath 'TimingLog.txt') -Encoding Default -Append
}

# ---------- Signal completion for remote monitors ----------
$doneFile = Join-Path $OutputDir 'DONE.txt'
New-Item -ItemType File -Path $doneFile -Force | Out-Null
Write-Output ('Created {0}' -f $doneFile)

