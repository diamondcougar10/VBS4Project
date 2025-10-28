param(
  [Parameter(Mandatory=$true)][string]$HostIP,
  [Parameter(Mandatory=$true)][string]$Targets,
  [string]$UserName,
  [string]$Password,
  [string]$SummaryOut = "$env:TEMP\deploy_summary.txt"
)

$ErrorActionPreference = 'Stop'
$PSDefaultParameterValues['*:ErrorAction'] = 'Stop'

function Write-Log {
  param([string]$Line)
  try {
    $dir = "C:\ProgramData\STE_Toolkit"
    if (!(Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $log = Join-Path $dir 'host-deploy.log'
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Add-Content -Path $log -Value "$ts $Line"
  } catch {}
}

function Hide-Start {
  param([string]$Exe, [string]$Args)
  try {
    Start-Process -FilePath $Exe -ArgumentList $Args -WindowStyle Hidden -Wait -NoNewWindow | Out-Null
    return $true
  } catch {
    return $false
  }
}

$summary = New-Object System.Collections.ArrayList
$targetsList = @()
if ($Targets) {
  $targetsList = $Targets.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' }
}

if (-not $targetsList -or $targetsList.Count -eq 0) {
  Write-Log "No targets specified. Exiting."
  [void]$summary.Add("No targets provided.")
  $summary -join "`r`n" | Set-Content -Path $SummaryOut -Encoding UTF8
  exit 1
}

$src = Join-Path $PSScriptRoot 'STE_Toolkit_Setup.exe'
if (-not (Test-Path $src)) {
  # Fallback: look in temp
  $src = Join-Path $env:TEMP 'STE_Toolkit_Setup.exe'
}

[void]$summary.Add("Host: $HostIP")
[void]$summary.Add("Targets: " + ($targetsList -join ', '))
[void]$summary.Add("")

foreach ($t in $targetsList) {
  if ([string]::IsNullOrWhiteSpace($t)) { continue }
  $ok = $false
  $msg = ""
  try {
    Write-Log "[$t] Starting deployment"

    if ($UserName -and $Password) {
      Write-Log "[$t] Storing credentials via cmdkey"
      Hide-Start "cmd.exe" "/c cmdkey /add:$t /user:$UserName /pass:$Password" | Out-Null
    }

    $dstDir = "\\$t\C$\Temp\STE"
    New-Item -ItemType Directory -Force -Path $dstDir | Out-Null

    if (-not (Test-Path $src)) { throw "Installer not found at $src" }
    Copy-Item -Path $src -Destination (Join-Path $dstDir 'STE_Toolkit_Setup.exe') -Force

    # Write first-run marker for diagnostics
    Set-Content -Path (Join-Path $dstDir 'first-run.inf') -Value "HOSTIP=$HostIP`r`n" -Encoding ASCII

    # Create scheduled task (SYSTEM) to run silent user install
    $tr = "C:\\Temp\\STE\\STE_Toolkit_Setup.exe /VERYSILENT /NORESTART /SUPPRESSMSGBOXES /LOG=\"C:\\ProgramData\\STE_Toolkit\\user-install.log\" /MODE=USER /HOSTIP=$HostIP"

    Write-Log "[$t] Creating task"
    Hide-Start "schtasks.exe" "/Create /S $t /RU SYSTEM /SC ONCE /TN STEUserInstall /TR \"$tr\" /ST 00:00 /F" | Out-Null

    Write-Log "[$t] Running task"
    Hide-Start "schtasks.exe" "/Run /S $t /TN STEUserInstall" | Out-Null

    # Poll for completion: look for user-install.log or task status
    $start = Get-Date
    $timeoutSec = 600
    $logPath = "\\$t\C$\ProgramData\STE_Toolkit\user-install.log"
    do {
      Start-Sleep -Seconds 5
      $elapsed = (Get-Date) - $start
      if (Test-Path $logPath) {
        $ok = $true
        break
      }
      # Query task last run result
      try {
        $q = schtasks /Query /S $t /TN STEUserInstall /V /FO LIST | Out-String
        if ($q -match 'Last Run Result:\s*0x0') {
          $ok = $true
          break
        }
        if ($q -match 'Could not start') { }
      } catch {}
    } while ($elapsed.TotalSeconds -lt $timeoutSec)

    if ($ok) {
      $msg = "OK - install triggered"
      Write-Log "[$t] SUCCESS"
    } else {
      $msg = "FAIL - timeout waiting for completion"
      Write-Log "[$t] TIMEOUT"
    }
  } catch {
    $ok = $false
    $msg = "FAIL - $($_.Exception.Message)"
    Write-Log "[$t] ERROR: $msg"
  }
  [void]$summary.Add("$t : $msg")
}

try { $summary -join "`r`n" | Set-Content -Path $SummaryOut -Encoding UTF8 } catch {}
