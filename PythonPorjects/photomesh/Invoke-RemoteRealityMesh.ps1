<# ======================================================================
 Invoke-RemoteRealityMesh.ps1  (PRODUCTION)
 Repo layout expected:
   PythonPorjects\
     Tools\PsExec.exe
     photomesh\Invoke-RemoteRealityMesh.ps1   <-- this file
 Network layout expected:
   \\HAMMERKIT1-4\SharedMeshDrive\RealityMesh\Input\<ProjectFolder>\ 
      - RealityMeshProcess.ps1
      - <ProjectFolder>.txt
 ===================================================================== #>

[CmdletBinding()]
param(
    # Remote PC IP or hostname
    [Parameter(Mandatory=$true, Position=0)]
    [string]$Target,

    # EITHER a project folder name under ...\RealityMesh\Input\
    # OR a local absolute path to a <Project>.txt settings file (current usage)
    [Parameter(Mandatory=$true, Position=1)]
    [string]$ProjectOrLocalSettings,

    # Root UNC share for RealityMesh
    [Parameter(Position=2)]
    [string]$ShareRoot = "\\HAMMERKIT1-4\SharedMeshDrive\RealityMesh",

    # Optional credentials (Domain\User or .\User)
    [Parameter(Position=3)]
    [PSCredential]$Credential,

    # Hide the yellow “in progress” banner on the remote window
    [Parameter(Position=4)]
    [switch]$NoBanner
)

# ------------------- Paths & Logging -------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PsExecPath = Join-Path (Split-Path $ScriptDir -Parent) "Tools\PsExec.exe"

# Your known-good RealityMeshProcess.ps1 source on THIS machine:
$localRmPs1 = "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\photomesh\RealityMeshProcess.ps1"

$LogFile = Join-Path $ScriptDir "Invoke-RemoteRealityMesh.log"
function Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $LogFile -Value $line
}

if (-not (Test-Path $PsExecPath)) { throw "PsExec.exe not found. Expected at: $PsExecPath" }
& $PsExecPath -accepteula | Out-Null

# Shared roots
$InputRoot  = Join-Path $ShareRoot 'Input'
$OutputRoot = Join-Path $ShareRoot 'Output'
if (-not (Test-Path $InputRoot))  { New-Item -ItemType Directory -Path $InputRoot -Force | Out-Null }
if (-not (Test-Path $OutputRoot)) { New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null }

# ------------------- Resolve project + settings + tiles -------------------
$usingLocalSettings = $false
$LocalSettingsPath  = $null
$ProjectFolder      = $null
$SourceTilesLocal   = $null

# Heuristic: if the arg looks like a rooted path to a .txt, treat as local settings file
if ([System.IO.Path]::IsPathRooted($ProjectOrLocalSettings) -and
    $ProjectOrLocalSettings.ToLower().EndsWith(".txt") -and
    (Test-Path $ProjectOrLocalSettings)) {

    $usingLocalSettings = $true
    $LocalSettingsPath  = $ProjectOrLocalSettings

    Log "Detected local settings file: $LocalSettingsPath"
    $settingsContent = Get-Content -LiteralPath $LocalSettingsPath
    $ProjectFolder   = ($settingsContent | Where-Object { $_ -match '^project_name=' }) -replace 'project_name=',''
    $SourceTilesLocal= ($settingsContent | Where-Object { $_ -match '^source_Directory=' }) -replace 'source_Directory=',''

    if ([string]::IsNullOrWhiteSpace($ProjectFolder)) { throw "project_name not found in settings: $LocalSettingsPath" }
    if (-not (Test-Path $SourceTilesLocal)) { throw "source_Directory not found on disk: $SourceTilesLocal" }
}
else {
    # Treat as a project folder name already in the share
    $ProjectFolder = $ProjectOrLocalSettings
    Log "Using project folder name provided: $ProjectFolder"
}

$ProjectPathUNC = Join-Path $InputRoot $ProjectFolder
if (-not (Test-Path $ProjectPathUNC)) {
    Log "Creating project folder on share: $ProjectPathUNC"
    New-Item -ItemType Directory -Path $ProjectPathUNC -Force | Out-Null
}

# ------------------- Ensure files exist in project folder on share -------------------
# 1) Settings file on share
$ShareSettingsPath = Join-Path $ProjectPathUNC ("{0}.txt" -f $ProjectFolder)

if ($usingLocalSettings) {
    # Mirror tiles to \\...\Input\<Project>\data
    $destDataDir = Join-Path $ProjectPathUNC 'data'
    Log "Mirroring local tiles to $destDataDir ..."
    $rc = robocopy $SourceTilesLocal $destDataDir /MIR /R:3 /W:5 /NP
    # robocopy returns weird codes; continue unless > 7 (8+ = failure)
    if ($LASTEXITCODE -ge 8) { throw "Robocopy failed mirroring tiles. Exit: $LASTEXITCODE" }

    # Copy local settings and rewrite source_Directory to the shared location
    Copy-Item -LiteralPath $LocalSettingsPath -Destination $ShareSettingsPath -Force
    (Get-Content -LiteralPath $ShareSettingsPath) | ForEach-Object {
        if ($_ -match '^source_Directory=') { "source_Directory=$destDataDir" } else { $_ }
    } | Set-Content -LiteralPath $ShareSettingsPath -Encoding UTF8
}
else {
    # If not using local settings, require it to already be present on share
    if (-not (Test-Path $ShareSettingsPath)) {
        throw "Expected settings file not found on share: $ShareSettingsPath (Provide a local settings path or place it on the share)."
    }
}

# 2) RealityMeshProcess.ps1 on share (copy your known-good one each run)
$rmPs1 = Join-Path $ProjectPathUNC 'RealityMeshProcess.ps1'
if (-not (Test-Path $localRmPs1)) { throw "Local RealityMeshProcess.ps1 not found: $localRmPs1" }
Copy-Item -LiteralPath $localRmPs1 -Destination $rmPs1 -Force
if (-not (Test-Path $rmPs1)) {
    throw "Process script not found after copy: $rmPs1"
}

Log "Target            : $Target"
Log "Project folder    : $ProjectFolder"
Log "Process script    : $rmPs1"
Log "Settings file     : $ShareSettingsPath"
Log "Share root        : $ShareRoot"
Log "PsExec            : $PsExecPath"

# ------------------- Credentials -------------------
if (-not $Credential) {
    $Credential = Get-Credential -Message "Enter credentials for $Target (local admin or domain account)"
}
$user = $Credential.UserName
if ($user -notmatch '^[^\\]+\\[^\\]+$') { $user = ".\${user}" }

# plaintext pw (PsExec requirement)
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Credential.Password)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)

    # ------------------- Preflight: ADMIN$ access -------------------
    Log "Testing ADMIN$ on \\$Target..."
    $netCmd = "net use \\$Target\ADMIN$ /user:$user `"$plain`""
    $netUse = cmd /c $netCmd
    if ($LASTEXITCODE -ne 0) {
        Log "ADMIN$ test failed. Output:"
        Log $netUse
        throw "Cannot access \\$Target\ADMIN$ as $user. Enable File & Printer Sharing, ensure local admin + LocalAccountTokenFilterPolicy=1."
    }
    cmd /c "net use \\$Target\ADMIN$ /delete" | Out-Null

    # -------- Remote command string --------
    $escapedPs1 = $rmPs1.Replace("'", "''").Replace('`','``')
    $escapedTxt = $ShareSettingsPath.Replace("'", "''").Replace('`','``')
    $banner     = if ($NoBanner) { "" } else { "Write-Host 'RealityMeshProcess in progress - do not turn off PC' -ForegroundColor Yellow; " }
    $remoteCmd  = ("{0}& '{1}' '{2}' 1" -f $banner, $escapedPs1, $escapedTxt)

    # ---- PsExec args ----
    $psArgs = @(
        "\\$Target", "-i", "-h",
        "-u", $user, "-p", $plain,
        "powershell", "-NoExit", "-ExecutionPolicy", "Bypass",
        "-Command", $remoteCmd
    )

    Log "Starting remote PowerShell window..."
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName               = $PsExecPath
    $psi.Arguments              = ($psArgs | ForEach-Object {
        if ($_ -match '\s|;|&|\(|\)|\^|\|' ) { '"{0}"' -f $_ } else { $_ }
    }) -join ' '
    $psi.UseShellExecute        = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true

    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()

    if ($stdout) { Log $stdout.Trim() }
    if ($stderr) { Log ("STDERR: " + $stderr.Trim()) }

    if ($proc.ExitCode -ne 0) {
        throw "PsExec returned exit code $($proc.ExitCode). See log for details."
    }

    Log "Remote window launched. Operators can watch progress on $Target."
}
finally {
    if ($ptr) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    if ($plain) {
        [System.Array]::Clear([char[]]$plain, 0, $plain.Length) 2>$null
        $plain = $null
    }
}
