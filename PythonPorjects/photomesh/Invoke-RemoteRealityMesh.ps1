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
$RemoteBatchRoot = "C:\Users\User\Documents\BiSim\Datasets_and_Template\Template"
$RemoteBatchFile = "RealityMeshProcess.bat"

# Optional DevSuite/P: semantics for DONE marker (legacy path behavior)
$override_Installation_DevSuite = 0
$override_Path_DevSuite        = "D"   # drive letter only, e.g. "D"

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

function Invoke-LoggedProcess {
  param(
    [Parameter(Mandatory)][string]$FilePath,
    [string]$Arguments = '',
    [string]$WorkingDirectory = $PSScriptRoot,
    [int]$ProgressId = 1,
    [string]$ProgressActivity = "Running external process"
  )
  $si = New-Object System.Diagnostics.ProcessStartInfo
  $si.FileName  = $FilePath
  $si.Arguments = $Arguments
  $si.WorkingDirectory = $WorkingDirectory
  $si.UseShellExecute = $false
  $si.RedirectStandardOutput = $true
  $si.RedirectStandardError  = $true
  $si.CreateNoWindow = $true

  $p = New-Object System.Diagnostics.Process
  $p.StartInfo = $si
  $p.add_OutputDataReceived({ if ($_.Data) { Write-Log $_.Data 'INFO' } })
  $p.add_ErrorDataReceived( { if ($_.Data) { Write-Log $_.Data 'ERROR' } })

  [void]$p.Start()
  $p.BeginOutputReadLine()
  $p.BeginErrorReadLine()

  $started = Get-Date
  while (-not $p.HasExited) {
    $elapsed = (Get-Date) - $started
    Write-Progress -Id $ProgressId -Activity $ProgressActivity -Status ("Elapsed {0:n0}s" -f $elapsed.TotalSeconds) -PercentComplete 50
    Start-Sleep -Milliseconds 250
  }
  Write-Progress -Id $ProgressId -Completed -Activity $ProgressActivity
  return $p.ExitCode
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

if ($override_Installation_DevSuite -eq 1) {
  $OutPath = ("{0}:\temp\RealityMesh\{1}" -f $override_Path_DevSuite, $ProjectName)
} else {
  $OutPath = "P:\temp\RealityMesh\$ProjectName"
}
if (-not (Test-Path -LiteralPath $OutPath)) { New-Item -ItemType Directory -Path $OutPath -Force | Out-Null }

if (-not (Test-Path -LiteralPath $RemoteBatchRoot)) { throw "BAT root not found: $RemoteBatchRoot" }
$BatSettings = Join-Path $RemoteBatchRoot ("{0}-settings.txt" -f $ProjectName)
Copy-Item -LiteralPath $SettingsPath -Destination $BatSettings -Force
Write-Log "Placed settings for BAT: $BatSettings" STEP

$batPath = Join-Path $RemoteBatchRoot $RemoteBatchFile
if (-not (Test-Path -LiteralPath $batPath)) { throw "BAT not found: $batPath" }
Write-Log "Starting Reality Mesh BAT..." STEP
$exit = Invoke-LoggedProcess -FilePath $batPath -Arguments '' -WorkingDirectory $RemoteBatchRoot -ProgressId 2 -ProgressActivity "RealityMesh BAT"
if ($exit -ne 0) { throw "Reality Mesh BAT returned exit code $exit" }

$doneFile = Join-Path $OutPath 'DONE.txt'
New-Item -ItemType File -Path $doneFile -Force | Out-Null
Write-Log "Created $doneFile" STEP
Write-Log "Full run log: $RunLog"

