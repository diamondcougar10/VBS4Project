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

# Ensure n33.tbr is present before running the main TCL script
Push-Location $tclWorkingDir
try {
    $n33File = "n33.tbr"
    if (-not (Test-Path $n33File)) {
        Write-Host "n33.tbr not found. Generating with TSG_TBR_to_Vertex_Points_Unique.tcl..." -ForegroundColor Yellow
        & tclsh "TSG_TBR_to_Vertex_Points_Unique.tcl"
    }

    if (-not (Test-Path $n33File)) {
        Write-Host "ERROR: Required file n33.tbr could not be created." -ForegroundColor Red
        exit 1
    }

    Write-Host "Launching RealityMeshProcess.tcl with settings from $SettingsFile" -ForegroundColor Cyan
    Write-Host "🚧 Processing Reality Mesh... Please wait. Do not close this window." -ForegroundColor Yellow
    Start-Sleep -Seconds 2

    $proc = Start-Process tclsh -ArgumentList "`"$tclScript`" -command_file `"$SettingsFile`"" -NoNewWindow -PassThru
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
} finally {
    Pop-Location
}
