#requires -Version 5.1

[CmdletBinding()]
param(
  # Deprecated (kept for compatibility)
  [Parameter(Position=0)][string]$Target,
  [Parameter(Mandatory,Position=1)][string]$SettingsPath,  # LOCAL absolute path to <project>-settings.txt
  # Deprecated (kept for compatibility)
  [Parameter(Position=2)][string]$ShareRoot,
  [Parameter(Position=3)][PSCredential]$Credential,
  [switch]$NoBanner
)

# Where the BAT and template live locally (adjust if needed)
$RemoteBatchRoot = "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\photomesh"
$RemoteBatchFile = "RealityMeshProcess.bat"

# Shared roots for inputs and outputs
$sharedRoot = '\\HAMMERKIT1-4\SharedMeshDrive\RealityMesh'
$inputRoot  = Join-Path $sharedRoot 'Input'
$outputRoot = Join-Path $sharedRoot 'Output'

$RunStamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$LogDir   = Join-Path $PSScriptRoot 'Logs'
if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$RunLog   = Join-Path $LogDir ("RemoteRunner_{0}.log" -f $RunStamp)

function Write-Log {
  param([Parameter(Mandatory)][string]$Message,[ValidateSet('INFO','WARN','ERROR','STEP')][string]$Level='INFO')
  $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
  $line = "[{0}] [{1}] {2}" -f $ts,$Level,$Message
  switch ($Level) {
    'INFO'  { Write-Host $line }
    'WARN'  { Write-Host $line -ForegroundColor Yellow }
    'ERROR' { Write-Host $line -ForegroundColor Red }
    'STEP'  { Write-Host $line -ForegroundColor Cyan }
  }
  Add-Content -LiteralPath $RunLog -Value $line
}

if ($Target -or $ShareRoot -or $Credential) {
  Write-Log "Remote params detected (Target/ShareRoot/Credential) are ignored in local one-click mode." 'WARN'
}

function Get-SettingsMap {
  param([string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { throw "Settings file not found: $Path" }
  $map = @{}
  Get-Content -LiteralPath $Path | ForEach-Object {
    if ($_ -match '^\s*#') { return }
    if ($_ -notmatch '=') { return }
    $kv = $_.Split('=',2)
    $k  = ($kv[0]).Trim()
    $v  = ($kv[1]).Trim()
    if ($k) { $map[$k] = $v }
  }
  return $map
}
$settings = Get-SettingsMap -Path $SettingsPath

$ProjectName = $settings['project_name']
$SourceDir   = $settings['source_Directory']
if (-not $ProjectName) { throw "Settings missing 'project_name'." }
if (-not (Test-Path -LiteralPath $SourceDir)) { throw "source_Directory not found: $SourceDir" }
$hasObj = Get-ChildItem -Path $SourceDir -Recurse -Filter *.obj -ErrorAction SilentlyContinue | Select-Object -First 1
$hasLas = Get-ChildItem -Path $SourceDir -Recurse -Filter *.las -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $hasObj -and -not $hasLas) { throw "No *.obj or *.las under: $SourceDir" }
Write-Log "Settings: project_name=$ProjectName" STEP

if (-not (Test-Path -LiteralPath $RemoteBatchRoot)) { throw "BAT root not found: $RemoteBatchRoot" }
$BatSettingsPath = Join-Path $RemoteBatchRoot ("{0}-settings.txt" -f $ProjectName)
Copy-Item -LiteralPath $SettingsPath -Destination $BatSettingsPath -Force
Write-Log "Placed settings for BAT: $BatSettingsPath" STEP

$batPath = Join-Path $RemoteBatchRoot $RemoteBatchFile
if (-not (Test-Path -LiteralPath $batPath)) { throw "BAT not found: $batPath" }

$batArgs = '"' + $BatSettingsPath + '"'
$startTime = Get-Date
$p = Start-Process -FilePath $batPath -ArgumentList $batArgs -NoNewWindow -PassThru
$p.WaitForExit()
if ($LASTEXITCODE -ne 0 -and $p.ExitCode -ne 0) {
    throw "Reality Mesh BAT returned code $($p.ExitCode)"
}

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$out_in_name_with_drive = Join-Path $outputRoot ("{0}_{1}" -f $ProjectName, $timestamp)
if (-not (Test-Path -LiteralPath $out_in_name_with_drive)) {
    New-Item -ItemType Directory -Path $out_in_name_with_drive -Force | Out-Null
}

$doneFile = Join-Path $out_in_name_with_drive 'DONE.txt'
New-Item -ItemType File -Path $doneFile -Force | Out-Null

$logCopy = Join-Path $out_in_name_with_drive (Split-Path $RunLog -Leaf)
Copy-Item -LiteralPath $RunLog -Destination $logCopy -Force
$timingLog = Join-Path $RemoteBatchRoot 'TimingLog.txt'
if (Test-Path -LiteralPath $timingLog) {
    Copy-Item -LiteralPath $timingLog -Destination (Join-Path $out_in_name_with_drive 'TimingLog.txt') -Force
}
Write-Log "Created $doneFile" STEP
Write-Log "Full run log: $RunLog"

