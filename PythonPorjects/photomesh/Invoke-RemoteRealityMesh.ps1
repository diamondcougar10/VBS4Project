param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$TargetIP,
    [Parameter(Mandatory=$true, Position=1)]
    [string]$SettingsFile,
    [Parameter(Position=2)]
    [string]$ResultsDir = "$PSScriptRoot\Results"
)

# Shared drive used by both machines
$sharedRoot = "\\\SharedDrive\PhotoMesh"
$inputRoot = Join-Path $sharedRoot 'Input'
$outputRoot = Join-Path $sharedRoot 'Output'

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
    Write-Host "Launching RealityMeshProcess.ps1 on $TargetIP" -ForegroundColor Cyan
    Invoke-Command -Session $session -ScriptBlock {
        param($script, $settings)
        Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File `\"$script`\" `\"$settings`\"" -NoNewWindow
    } -ArgumentList $scriptPath, $remoteSettings
}
finally {
    if ($session) {
        Remove-PSSession $session
    }
}

$start = Get-Date
Write-Host "Waiting for completion flag..." -ForegroundColor Yellow
$doneFile = $null
while (-not $doneFile) {
    $folder = Get-ChildItem -Path $outputRoot -Filter "${projectName}_*" -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($folder) {
        $candidate = Join-Path $folder.FullName 'DONE.txt'
        if (Test-Path $candidate) { $doneFile = $candidate; break }
    }
    Start-Sleep -Seconds 30
}

$elapsed = (Get-Date) - $start
$finalDir = Split-Path $doneFile
$destDir = Join-Path $ResultsDir (Split-Path $finalDir -Leaf)
Write-Host "Copying results to $destDir" -ForegroundColor Cyan
robocopy $finalDir $destDir /MIR | Out-Null

$log = Join-Path $PSScriptRoot 'RemoteProcess.log'
"$projectName completed in $($elapsed.TotalMinutes) minutes" | Out-File -FilePath $log -Append

# Cleanup temporary data
Remove-Item $finalDir -Recurse -Force
