param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$TargetIP,
    [Parameter(Mandatory=$true, Position=1)]
    [string]$SettingsFile
)

# Shared drive used by both machines
$sharedRoot = "\\\SharedDrive\PhotoMesh"
$inputRoot = Join-Path $sharedRoot 'Input'

if (-not (Test-Path $SettingsFile)) {
    Write-Error "Settings file not found: $SettingsFile"
    exit 1
}

# Read basic info from the local settings file
$settingsContent = Get-Content $SettingsFile
$projectName = ($settingsContent | Where-Object { $_ -match '^project_name=' }) -replace 'project_name=', ''
$sourceDir = ($settingsContent | Where-Object { $_ -match '^source_Directory=' }) -replace 'source_Directory=', ''

$projectInputDir = Join-Path $inputRoot $projectName
New-Item -ItemType Directory -Path $projectInputDir -Force | Out-Null
$destDataDir = Join-Path $projectInputDir 'data'
robocopy $sourceDir $destDataDir /MIR | Out-Null

# Copy and update the settings file on the shared drive
$remoteSettings = Join-Path $projectInputDir (Split-Path $SettingsFile -Leaf)
Copy-Item $SettingsFile $remoteSettings -Force
(Get-Content $remoteSettings) | ForEach-Object {
    if ($_ -match '^source_Directory=') { "source_Directory=$destDataDir" } else { $_ }
} | Set-Content $remoteSettings

$session = New-PSSession -ComputerName $TargetIP
try {
    $scriptPath = Join-Path $PSScriptRoot 'RealityMeshProcess.ps1'
    Write-Host "Running RealityMeshProcess.ps1 on $TargetIP" -ForegroundColor Cyan
    $output = Invoke-Command -Session $session -FilePath $scriptPath -ArgumentList $remoteSettings
    Write-Output $output
}
finally {
    if ($session) {
        Remove-PSSession $session
    }
}
