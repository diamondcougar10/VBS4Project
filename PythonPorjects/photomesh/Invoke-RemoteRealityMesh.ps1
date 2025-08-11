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

    # Project folder name under ...\RealityMesh\Input\ (omit to auto-pick latest)
    [Parameter(Position=1)]
    [string]$ProjectFolder,

    # Root UNC share for RealityMesh
    [Parameter(Position=2)]
    [string]$ShareRoot = "\\HAMMERKIT1-4\SharedMeshDrive\RealityMesh",

    # Optional pre-supplied credentials (Domain\User or .\User)
    [Parameter(Position=3)]
    [PSCredential]$Credential,

    # Hide the yellow “in progress” banner on the remote window
    [Parameter(Position=4)]
    [switch]$NoBanner
)

# ------------------- Paths & Logging -------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# PsExec is in ..\Tools\PsExec.exe (one level above this photomesh folder)
$PsExecPath = Join-Path (Split-Path $ScriptDir -Parent) "Tools\PsExec.exe"

$LogFile   = Join-Path $ScriptDir "Invoke-RemoteRealityMesh.log"
function Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $LogFile -Value $line
}

if (-not (Test-Path $PsExecPath)) { throw "PsExec.exe not found. Expected at: $PsExecPath" }
# Accept EULA silently (first run on a machine)
& $PsExecPath -accepteula | Out-Null

$InputRoot  = Join-Path $ShareRoot 'Input'
$OutputRoot = Join-Path $ShareRoot 'Output'
if (-not (Test-Path $InputRoot))  { throw "Input root not found: $InputRoot" }
if (-not (Test-Path $OutputRoot)) { New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null }

# Auto-pick latest project folder if not provided
if (-not $ProjectFolder) {
    $latest = Get-ChildItem -Path $InputRoot -Directory |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) { throw "No project directories found under $InputRoot" }
    $ProjectFolder = $latest.Name
    Log "Auto-selected latest project folder: $ProjectFolder"
}

$ProjectPathUNC = Join-Path $InputRoot $ProjectFolder
if (-not (Test-Path $ProjectPathUNC)) { throw "Project folder not found: $ProjectPathUNC" }

# Expect: RealityMeshProcess.ps1 + <ProjectFolder>.txt
$Ps1Path = Join-Path $ProjectPathUNC 'RealityMeshProcess.ps1'
$TxtPath = Join-Path $ProjectPathUNC ("{0}.txt" -f $ProjectFolder)
if (-not (Test-Path $Ps1Path)) { throw "Process script not found: $Ps1Path" }
if (-not (Test-Path $TxtPath)) { throw "Settings file not found: $TxtPath" }

Log "Target            : $Target"
Log "Project folder    : $ProjectFolder"
Log "Process script    : $Ps1Path"
Log "Settings file     : $TxtPath"
Log "Share root        : $ShareRoot"
Log "PsExec            : $PsExecPath"

# ------------------- Credentials -------------------
if (-not $Credential) {
    $Credential = Get-Credential -Message "Enter credentials for $Target (local admin or domain account)"
}
# Normalize username for workgroup/local if not Domain\User format
$user = $Credential.UserName
if ($user -notmatch '^[^\\]+\\[^\\]+$') { $user = ".\${user}" }
 
# PsExec requires plaintext password; zero it in finally
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
        throw "Cannot access \\$Target\ADMIN$ as $user. Enable File & Printer Sharing, ensure account is in local Administrators group, and set LocalAccountTokenFilterPolicy=1."
    }
    # Clean mapping
    cmd /c "net use \\$Target\ADMIN$ /delete" | Out-Null

    # -------- build the remote command safely --------
    $escapedPs1 = $Ps1Path.Replace("'", "''").Replace('`','``')
    $escapedTxt = $TxtPath.Replace("'", "''").Replace('`','``')
    $banner = if ($NoBanner) { "" } else { "Write-Host 'RealityMeshProcess in progress - do not turn off PC' -ForegroundColor Yellow; " }
    $remoteCmd = ("{0}& '{1}' '{2}' 1" -f $banner, $escapedPs1, $escapedTxt)

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
