# PowerShell script to run RealityMeshProcess.tcl without hard-coded paths
param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$SettingsFile
)

# Path to RealityMeshProcess.tcl relative to this script
$tclScript = Join-Path $PSScriptRoot "RealityMesh_tt\RealityMeshProcess.tcl"

# Directory containing the TCL script
$tclWorkingDir = Split-Path $tclScript

# Validate that the settings file exists
if (-not (Test-Path $SettingsFile)) {
    Write-Error "Settings file not found: $SettingsFile"
    exit 1
}

Write-Host "Launching RealityMeshProcess.tcl with settings from $SettingsFile" -ForegroundColor Cyan

# Execute the TCL script using tclsh within the correct working directory
Push-Location $tclWorkingDir
try {
    Write-Host "🚧 Processing Reality Mesh... Please wait. Do not close this window." -ForegroundColor Yellow
    Start-Sleep -Seconds 2
    & tclsh $tclScript -command_file "$SettingsFile"
} finally {
    Pop-Location
}
