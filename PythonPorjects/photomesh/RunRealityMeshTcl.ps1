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
        Write-Host "Generating missing n33.tbr with TSG_TBR_to_Vertex_Points_Unique.tcl..." -ForegroundColor Yellow
        $genOutput = & tclsh "TSG_TBR_to_Vertex_Points_Unique.tcl" 2>&1
        $exitCode = $LASTEXITCODE
        $genOutput | ForEach-Object { Write-Host $_ }
    }

    if (-not (Test-Path $n33File) -or $exitCode -ne 0) {
        Write-Host "ERROR: Required file n33.tbr could not be created." -ForegroundColor Red
        Write-Host "Did TSG_TBR_to_Vertex_Points_Unique.tcl run without errors?" -ForegroundColor Red
        Write-Host "Was it run in the correct directory?" -ForegroundColor Red
        exit 1
    }

    Write-Host "Launching RealityMeshProcess.tcl with settings from $SettingsFile" -ForegroundColor Cyan
    Write-Host "🚧 Processing Reality Mesh... Please wait. Do not close this window." -ForegroundColor Yellow
    Start-Sleep -Seconds 2
    & tclsh $tclScript -command_file "$SettingsFile"
} finally {
    Pop-Location
}

Read-Host -Prompt "Press Enter to exit"
