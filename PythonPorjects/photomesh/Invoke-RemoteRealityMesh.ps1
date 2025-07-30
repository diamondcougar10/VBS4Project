param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$TargetIP,

    [Parameter(Mandatory=$true, Position=1)]
    [string]$SettingsFile,

    [Parameter(Mandatory=$false, Position=2)]
    [string]$ShareRoot = "\\SharedDrive\PhotoMesh"
)

if (-not (Test-Path $SettingsFile)) {
    Write-Error "Settings file not found: $SettingsFile"
    exit 1
}

# Determine project name from settings file

$projectName = (Get-Content $SettingsFile | Where-Object { $_ -match '^project_name=' }) -replace 'project_name=', ''

# Prepare shared paths
$inputDir   = Join-Path $ShareRoot 'Input'
$outputBase = Join-Path $ShareRoot 'Output'
$timestamp  = Get-Date -Format 'yyyyMMdd_HHmmss'
$outputDir  = Join-Path $outputBase ("{0}_{1}" -f $projectName,$timestamp)

# Ensure required directories exist
if (-not (Test-Path $inputDir))   { New-Item -ItemType Directory -Path $inputDir   | Out-Null }
if (-not (Test-Path $outputDir))  { New-Item -ItemType Directory -Path $outputDir  | Out-Null }

# Copy settings file to the shared input folder
$settingsCopy = Join-Path $inputDir (Split-Path $SettingsFile -Leaf)
Copy-Item $SettingsFile $settingsCopy -Force

$session = New-PSSession -ComputerName $TargetIP
try {
    $remoteScript = Join-Path $ShareRoot 'photomesh\RealityMeshProcess.ps1'
    Write-Host "Running RealityMeshProcess.ps1 on $TargetIP" -ForegroundColor Cyan

    Invoke-Command -Session $session -ScriptBlock {
        param($scriptPath, $settingsPath)
        & $scriptPath $settingsPath 1
    } -ArgumentList $remoteScript, $settingsCopy

    $projectFolder = Join-Path $ShareRoot "Projects\$projectName"

    Invoke-Command -Session $session -ScriptBlock {
        param($src, $dest)
        if (Test-Path $src) {
            Move-Item $src $dest -Force
        }
    } -ArgumentList $projectFolder, $outputDir

    Write-Host "Output available at $outputDir" -ForegroundColor Green
}
finally {
    if ($session) {
        Remove-PSSession $session
    }
}
