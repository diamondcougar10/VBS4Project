# =========================
# Reality Mesh Runner (UNC + local BAT/PS1)
# =========================


[CmdletBinding()]
param(
  [Parameter(Position=0,Mandatory=$true)][string]$project_settings_File,
  [string]$fully_automate,
  [switch]$PackageOnly
)
$EffectivePackageOnly = $PackageOnly -or ($env:RM_PACKAGE_ONLY -eq '1')
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# ---- helpers ----
function Normalize-UNCPath {
  param([Parameter(Mandatory)][string]$Path)
  if ([string]::IsNullOrWhiteSpace($Path)) { return $Path }
  $p = $Path -replace '/', '\'
  if ($p -match '^[\\]{2,}') { $p = $p -replace '^[\\]{2,}', '\\\\' }
  return $p
}
function Sanitize-Name {
  param([Parameter(Mandatory)][string]$Name)
  $n = $Name -replace '[\/:*?"<>|]', '_' ; $n = $n.Trim().TrimEnd('.')
  if ([string]::IsNullOrWhiteSpace($n)) { $n = 'Project' }
  return $n
}
function Ensure-Directory {
  param([Parameter(Mandatory)][string]$Dir)
  if (-not (Test-Path -LiteralPath $Dir)) { New-Item -ItemType Directory -Path $Dir -Force | Out-Null }
}

# ---- BAT/PS1 live HERE ----
$RemoteBatchRoot = $PSScriptRoot
$RemoteBatchFile = "RealityMeshProcess.bat"
[bool]$UseTclDirect = $false   # set $true only if you want the old TCL path

# ---- Shared roots (UNC) ----
$sharedRoot = '\\HAMMERKIT1-4\SharedMeshDrive\RealityMesh'
$inputRoot  = Join-Path $sharedRoot 'Input'
$outputRoot = Join-Path $sharedRoot 'Output'
Ensure-Directory $sharedRoot; Ensure-Directory $inputRoot; Ensure-Directory $outputRoot

# ---- parse inputs ----
if ([string]::IsNullOrWhiteSpace($project_settings_File)) { throw "Project settings file path is required." }
$project_settings_File = Normalize-UNCPath ($project_settings_File.Trim('"'))
$system_settings = Join-Path $PSScriptRoot 'RealityMeshSystemSettings.txt'
if (-not (Test-Path -LiteralPath $project_settings_File)) { throw "project settings file does not exist: $project_settings_File" }
if (-not (Test-Path -LiteralPath $system_settings))        { throw "System settings file does not exist: $system_settings" }

# ---- RealityMesh_tt template path ----
$RealityMeshTTPath = Join-Path $PSScriptRoot 'RealityMesh_tt'
$defaultRealityMeshTTPath = 'C:\Program Files (x86)\STE Toolkit\RealityMesh_tt'
if (-not (Test-Path -LiteralPath $RealityMeshTTPath)) {
  if (Test-Path -LiteralPath $defaultRealityMeshTTPath) { $RealityMeshTTPath = $defaultRealityMeshTTPath }
  else { throw "RealityMesh_tt folder not found at '$RealityMeshTTPath' or '$defaultRealityMeshTTPath'" }
}

# ---- project settings ----
$project_name = Sanitize-Name ((Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^project_name=' }) -replace 'project_name=','')
$source_Directory = Normalize-UNCPath ((Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^source_Directory=' }) -replace 'source_Directory=','')

$sel_Area_Size         = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^sel_Area_Size=' }) -replace 'sel_Area_Size=',''
$offset_coordsys       = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^offset_coordsys=' }) -replace 'offset_coordsys=',''
$offset_hdatum         = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^offset_hdatum=' }) -replace 'offset_hdatum=',''
$offset_vdatum         = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^offset_vdatum=' }) -replace 'offset_vdatum=',''
$offset_x              = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^offset_x=' }) -replace 'offset_x=',''
$offset_y              = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^offset_y=' }) -replace 'offset_y=',''
$offset_z              = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^offset_z=' }) -replace 'offset_z=',''
$orthocam_Resolution   = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^orthocam_Resolution=' }) -replace 'orthocam_Resolution=',''
$orthocam_Render_Lowest= (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^orthocam_Render_Lowest=' }) -replace 'orthocam_Render_Lowest=',''
$tin_to_dem_Resolution = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^tin_to_dem_Resolution=' }) -replace 'tin_to_dem_Resolution=',''
$tile_scheme           = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^tile_scheme=' }) -replace 'tile_scheme=',''
$collision             = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^collision=' }) -replace 'collision=',''
$visualLODs            = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^visualLODs=' }) -replace 'visualLODs=',''
$project_vdatum        = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^project_vdatum=' }) -replace 'project_vdatum=',''
$offset_models         = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^offset_models=' }) -replace 'offset_models=',''
$csf_options           = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^csf_options=' }) -replace 'csf_options=',''
$faceThresh            = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^faceThresh=' }) -replace 'faceThresh=',''
$lodThresh             = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^lodThresh=' }) -replace 'lodThresh=',''
$tileSize              = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^tileSize=' }) -replace 'tileSize=',''
$srfResolution         = (Get-Content -LiteralPath $project_settings_File | ? { $_ -match '^srfResolution=' }) -replace 'srfResolution=',''

# Preflight
if (-not (Test-Path -LiteralPath $source_Directory)) { throw "source_Directory not found: $source_Directory" }
$hasObj = Get-ChildItem -Path $source_Directory -Recurse -Filter *.obj -ErrorAction SilentlyContinue | Select-Object -First 1
$hasLas = Get-ChildItem -Path $source_Directory -Recurse -Filter *.las -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $hasObj -and -not $hasLas) { throw "No *.obj/*.las found under: $source_Directory. Make sure your data folder points to the correct location." }

# Optional: derive better name from Output-CenterPivotOrigin.json
$ocpo = Get-ChildItem -Path $source_Directory -Filter 'Output-CenterPivotOrigin.json' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if ($ocpo) {
  $projectRoot = Split-Path $ocpo.DirectoryName -Parent
  if ((Split-Path $ocpo.DirectoryName -Leaf) -like 'Build_*') { $projectRoot = Split-Path $projectRoot -Parent }
  $derivedName = Split-Path $projectRoot -Leaf
  if ($derivedName) { $project_name = Sanitize-Name $derivedName }
}

# ---- system settings (only what we need here) ----
$blender_path = (Get-Content -LiteralPath $system_settings | ? { $_ -match '^blender_path=' }) -replace 'blender_path=',''
$default_blender = 'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe'
if (-not (Test-Path -LiteralPath $blender_path)) {
  if (Test-Path -LiteralPath $default_blender) { $blender_path = $default_blender }
  else { throw "Blender Path invalid (checked: '$blender_path', '$default_blender')" }
}
$override_Installation_VBS4 = (Get-Content -LiteralPath $system_settings | ? { $_ -match '^override_Installation_VBS4=' }) -replace 'override_Installation_VBS4=',''
$override_Path_DevSuite     = (Get-Content -LiteralPath $system_settings | ? { $_ -match '^override_Path_DevSuite=' }) -replace 'override_Path_DevSuite=',''
$terratools_ssh_path        = (Get-Content -LiteralPath $system_settings | ? { $_ -match '^terratools_ssh_path=' }) -replace 'terratools_ssh_path=',''
if (-not (Test-Path -LiteralPath $terratools_ssh_path)) { throw "Terratools Path invalid: $terratools_ssh_path" }

# ---- project I/O layout on share ----
if (Test-Path (Join-Path $inputRoot $project_name)) {
  $project_name = "{0}_{1}" -f $project_name, (Get-Date -Format 'yyyyMMdd_HHmmss')
}
$projectFolder = Join-Path $inputRoot $project_name
Ensure-Directory $projectFolder

$generated_settings_file = Join-Path $projectFolder ("{0}.txt" -f $project_name)    # TCL-style set-file (legacy)
if (Test-Path -LiteralPath $generated_settings_file) { Remove-Item -LiteralPath $generated_settings_file -Force }
$override_Installation_VBS4_bool = if ($override_Installation_VBS4 -eq 1) { 'true' } else { 'false' }

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$out_in_name = $project_name
$out_in_name_with_drive = Join-Path $outputRoot ("{0}_{1}" -f $project_name,$timestamp)
Ensure-Directory $out_in_name_with_drive

Write-Host "ProjectName: $project_name"
Write-Host "DestDir:     $out_in_name_with_drive"
Write-Host "GenFile:     $generated_settings_file"

# ---- write TCL set-file (kept for completeness) ----
New-Item -ItemType File -Path $generated_settings_file -Force | Out-Null
$append = { param($k,$v) Add-Content -LiteralPath $generated_settings_file -Value ("set {0} {{{1}}}" -f $k,$v) }
&$append 'name'                         $project_name
&$append 'blender_path'                 $blender_path
&$append 'override_Installation_VBS4'   $override_Installation_VBS4
&$append 'sel_Area_Size'                $sel_Area_Size
&$append 'out_in_name'                  $out_in_name
&$append 'out_in_name_with_drive'       $out_in_name_with_drive
# (add others if your TCL flow still uses them)

# ---- key=value settings for BAT/PS1 ----
$kvSettingsLocal = Join-Path $projectFolder ("{0}-settings.txt" -f $project_name)
$kv = @(
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
$kv | Out-File -LiteralPath $kvSettingsLocal -Encoding UTF8 -Force

# copy settings next to BAT & PS1
if (-not (Test-Path -LiteralPath $RemoteBatchRoot)) { throw "BAT root not found: $RemoteBatchRoot" }
$BatSettingsPath = Join-Path $RemoteBatchRoot ("{0}-settings.txt" -f $project_name)
Copy-Item -LiteralPath $kvSettingsLocal -Destination $BatSettingsPath -Force

# ---- copy project template into project folder ----
if (Test-Path -LiteralPath $RealityMeshTTPath) {
  $rc = @('robocopy', ('"'+$RealityMeshTTPath+'"'), ('"'+$projectFolder+'"'),
          '*.*','/E','/DCOPY:DA','/COPY:DAT','/R:3','/W:5') -join ' '
  cmd /c $rc | Out-Host
} else {
  throw "Template folder not found at $RealityMeshTTPath"
}

Set-Location -LiteralPath $projectFolder
# rename .ttp
$ttp = Join-Path $projectFolder 'RealityMeshProcess.ttp'
if (Test-Path -LiteralPath $ttp) { Rename-Item -LiteralPath $ttp -NewName ("{0}.ttp" -f $project_name) -Force }

# drop small config files for TCL (harmless for BAT flow)
"set sourceDir `"$source_Directory`" " | Out-File -LiteralPath (Join-Path $projectFolder 'sourceDir.txt') -Encoding Default
"set tileScheme `"$tile_scheme`" "   | Out-File -LiteralPath (Join-Path $projectFolder 'tileScheme.txt') -Encoding Default

# make sure n33.tbr exists (if TCL ever runs)
if ($UseTclDirect -and -not $EffectivePackageOnly) {
  $n33File = Join-Path $projectFolder 'n33.tbr'
  if (-not (Test-Path -LiteralPath $n33File)) {
    if (Test-Path (Join-Path $projectFolder 'TSG_TBR_to_Vertex_Points_Unique.tcl')) {
      & tclsh (Join-Path $projectFolder 'TSG_TBR_to_Vertex_Points_Unique.tcl')
    }
  }
} elseif ($EffectivePackageOnly) {
  Write-Host "Skipping any Tcl/TerraTools steps on unlicensed machine." -ForegroundColor Yellow
}

# ---- run ----
if ($EffectivePackageOnly) {
  # always write a READY.txt in the project folder
  $ready = Join-Path $projectFolder 'READY.txt'
  New-Item -ItemType File -Path $ready -Force | Out-Null
  Write-Host "Packaged inputs at: $projectFolder"
  Write-Host "Settings for build: $kvSettingsLocal"
  Write-Host "Output target:      $out_in_name_with_drive"
  Write-Host "Package-only mode: READY.txt created. No BAT/PS1/TerraTools launched on this machine."
  exit 0
}

if (-not $UseTclDirect) {
  $batPath = Join-Path $RemoteBatchRoot $RemoteBatchFile
  if (-not (Test-Path -LiteralPath $batPath)) { throw "BAT not found: $batPath" }
  Write-Host "Starting Reality Mesh BAT..." -ForegroundColor Cyan
  Write-Host ("Using settings: {0}" -f $BatSettingsPath)

  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  $p = Start-Process -FilePath $batPath `
                     -ArgumentList ('"'+$BatSettingsPath+'"') `
                     -WorkingDirectory $RemoteBatchRoot `
                     -NoNewWindow -PassThru
  $p.WaitForExit()
  $sw.Stop()

  if ($p.ExitCode -ne 0) { throw "Reality Mesh BAT returned exit code $($p.ExitCode)" }

  "Time to run BAT: {0:n1} minutes" -f ($sw.Elapsed.TotalMinutes) |
    Out-File -LiteralPath (Join-Path $projectFolder 'TimingLog.txt') -Encoding Default -Append

  $doneFile = Join-Path $out_in_name_with_drive 'DONE.txt'
  New-Item -ItemType File -Path $doneFile -Force | Out-Null
  Write-Host ("Created {0}" -f $doneFile)
} else {
  # old TCL path if ever needed
  $terratools_ssh_path = $terratools_ssh_path  # already read above
  Write-Host "Launching TCL path..." -ForegroundColor Cyan
  $startTime = Get-Date
  $proc = Start-Process -FilePath $terratools_ssh_path -NoNewWindow -PassThru -ArgumentList "RealityMeshProcess.tcl -command_file `"$generated_settings_file`""
  $proc.WaitForExit()
  $minutes = ((Get-Date) - $startTime).TotalSeconds / 60
  "Time to run TT project: $minutes minutes" | Out-File -LiteralPath (Join-Path $projectFolder 'TimingLog.txt') -Encoding Default -Append

  $doneFile = Join-Path $out_in_name_with_drive 'DONE.txt'
  New-Item -ItemType File -Path $doneFile -Force | Out-Null
  Write-Host ("Created {0}" -f $doneFile)
}
