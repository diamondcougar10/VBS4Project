Param(
    [string]$ShareRoot = "\\HAMMERKIT1-4\SharedMeshDrive\RealityMesh",
    [int]$PollSeconds = 10
)

$LocalRoot = 'C:\ProgramData\RealityMesh\Worker'
$LocalLog = Join-Path $LocalRoot 'worker.log'
if (-not (Test-Path $LocalRoot)) { New-Item -Path $LocalRoot -ItemType Directory -Force | Out-Null }
if (-not (Test-Path $LocalLog)) { New-Item -Path $LocalLog -ItemType File -Force | Out-Null }

function Write-Log {
    param([string]$Message, [string]$ProjectLog)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -Path $LocalLog -Value $line -Encoding UTF8
    if ($ProjectLog) { Add-Content -Path $ProjectLog -Value $line -Encoding UTF8 }
}

function Try-ClaimProject {
    param([string]$ProjectPath)
    $lockPath = Join-Path $ProjectPath "CLAIMED_BY_$env:COMPUTERNAME.lock"
    try {
        $fs = [System.IO.File]::Open($lockPath,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::ReadWrite,[System.IO.FileShare]::None)
        return @{ LockPath = $lockPath; Stream = $fs }
    } catch {
        return $null
    }
}

function Release-Claim {
    param($claim)
    if ($null -ne $claim) {
        try { $claim.Stream.Dispose() } catch {}
        Remove-Item -Path $claim.LockPath -ErrorAction SilentlyContinue
    }
}

function Run-Project {
    param([string]$ProjectName,[string]$ProjectPath,$claim)
    $runnerLog = Join-Path $ProjectPath "runner-$env:COMPUTERNAME.log"
    Write-Log "Starting $ProjectName" $runnerLog
    $cmd = "& '$ProjectPath\\RealityMeshProcess.ps1' '$ProjectPath\\$ProjectName.txt' 1 2>&1 | Tee-Object -FilePath '$runnerLog' -Append"
    try {
        $proc = Start-Process -FilePath 'powershell' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-Command',$cmd -WindowStyle Hidden -PassThru
        $proc.WaitForExit()
        $exit = $proc.ExitCode
        Write-Log "$ProjectName finished with code $exit" $runnerLog
        $done = Join-Path $ProjectPath 'DONE.txt'
        if (-not (Test-Path $done)) {
            "Completed by $env:COMPUTERNAME at $(Get-Date -Format 's') ExitCode=$exit" | Set-Content -Path $done -Encoding UTF8
        }
    } catch {
        Write-Log "Error running $ProjectName: $_" $runnerLog
    } finally {
        Release-Claim $claim
    }
}

Write-Log "RealityMeshWorker starting. ShareRoot=$ShareRoot PollSeconds=$PollSeconds" $null

while ($true) {
    try {
        $inputRoot = Join-Path $ShareRoot 'Input'
        $projects = Get-ChildItem -Path $inputRoot -Directory -ErrorAction SilentlyContinue
        foreach ($p in $projects) {
            $projectName = $p.Name
            $projectPath = $p.FullName
            $txt = Join-Path $projectPath "$projectName.txt"
            $runner = Join-Path $projectPath 'RealityMeshProcess.ps1'
            $done = Join-Path $projectPath 'DONE.txt'
            if ((Test-Path $txt) -and (Test-Path $runner) -and -not (Test-Path $done)) {
                $claim = Try-ClaimProject $projectPath
                if ($claim) {
                    Run-Project $projectName $projectPath $claim
                }
            }
        }
    } catch {
        Write-Log "Worker loop error: $_" $null
    }
    Start-Sleep -Seconds $PollSeconds
}
