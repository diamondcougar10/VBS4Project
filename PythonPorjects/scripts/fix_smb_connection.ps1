# Fix SMB Connection Issues
# Run this script as Administrator on the PC that cannot access the share
#
# This script clears all cached SMB sessions and credentials, then tests connectivity

param(
    [string]$TargetServer = "192.168.10.201",
    [string]$ShareName = "SharedMeshDrive"
)

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "SMB Connection Fix Tool" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "Target: \\$TargetServer\$ShareName" -ForegroundColor White
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Running as Administrator - OK" -ForegroundColor Green
Write-Host ""

# Step 1: Basic network connectivity test
Write-Host "STEP 1: Testing network connectivity to $TargetServer" -ForegroundColor Yellow
Write-Host "--------------------------------------------------------" -ForegroundColor Yellow

$pingResult = Test-Connection -ComputerName $TargetServer -Count 2 -Quiet -ErrorAction SilentlyContinue
if ($pingResult) {
    Write-Host "✓ Ping successful - network is reachable" -ForegroundColor Green
} else {
    Write-Host "✗ Ping FAILED - network connectivity issue!" -ForegroundColor Red
    Write-Host "  Check that:" -ForegroundColor Yellow
    Write-Host "    - The target server ($TargetServer) is online" -ForegroundColor White
    Write-Host "    - Both PCs are on the same network/subnet" -ForegroundColor White
    Write-Host "    - Firewall isn't blocking ICMP" -ForegroundColor White
}
Write-Host ""

# Step 2: Check SMB port
Write-Host "STEP 2: Testing SMB port (445)" -ForegroundColor Yellow
Write-Host "------------------------------" -ForegroundColor Yellow

$portTest = Test-NetConnection -ComputerName $TargetServer -Port 445 -WarningAction SilentlyContinue -ErrorAction SilentlyContinue
if ($portTest.TcpTestSucceeded) {
    Write-Host "✓ SMB port 445 is open" -ForegroundColor Green
} else {
    Write-Host "✗ SMB port 445 is BLOCKED!" -ForegroundColor Red
    Write-Host "  Check firewall on $TargetServer" -ForegroundColor Yellow
}
Write-Host ""

# Step 3: Show current SMB sessions
Write-Host "STEP 3: Current SMB connections" -ForegroundColor Yellow
Write-Host "--------------------------------" -ForegroundColor Yellow
$currentConnections = net use 2>$null
if ($currentConnections) {
    Write-Host $currentConnections
} else {
    Write-Host "(No active connections)" -ForegroundColor Gray
}
Write-Host ""

# Step 4: Delete ALL existing SMB connections
Write-Host "STEP 4: Clearing ALL cached SMB sessions" -ForegroundColor Yellow
Write-Host "-----------------------------------------" -ForegroundColor Yellow

# Delete all connections
try {
    net use * /delete /yes 2>&1 | Out-Null
    Write-Host "✓ Cleared all SMB sessions" -ForegroundColor Green
} catch {
    Write-Host "Note: $_" -ForegroundColor Gray
}

# Specifically target the problem server
try {
    net use "\\$TargetServer\IPC$" /delete /yes 2>$null
    net use "\\$TargetServer\$ShareName" /delete /yes 2>$null
    Write-Host "✓ Cleared connections to $TargetServer" -ForegroundColor Green
} catch {
    Write-Host "Note: No specific connections to clear" -ForegroundColor Gray
}
Write-Host ""

# Step 5: Clear Windows Credential Manager
Write-Host "STEP 5: Clearing cached credentials" -ForegroundColor Yellow
Write-Host "------------------------------------" -ForegroundColor Yellow

# List all credentials
$credList = cmdkey /list 2>$null
$serverCreds = $credList | Select-String -Pattern $TargetServer

if ($serverCreds) {
    Write-Host "Found cached credentials for $TargetServer - removing..." -ForegroundColor Gray
    
    # Try various credential formats
    cmdkey /delete:$TargetServer 2>$null
    cmdkey /delete:"$TargetServer" 2>$null
    cmdkey /delete:"\\$TargetServer" 2>$null
    cmdkey /delete:"Domain:target=$TargetServer" 2>$null
    cmdkey /delete:"LegacyGeneric:target=$TargetServer" 2>$null
    
    Write-Host "✓ Cleared cached credentials" -ForegroundColor Green
} else {
    Write-Host "No cached credentials found for $TargetServer" -ForegroundColor Gray
}
Write-Host ""

# Step 6: Enable guest authentication
Write-Host "STEP 6: Enabling guest authentication" -ForegroundColor Yellow
Write-Host "--------------------------------------" -ForegroundColor Yellow

$regPath = "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters"
try {
    $currentValue = (Get-ItemProperty -Path $regPath -Name "AllowInsecureGuestAuth" -ErrorAction SilentlyContinue).AllowInsecureGuestAuth
    
    if ($currentValue -eq 1) {
        Write-Host "✓ Guest authentication already enabled" -ForegroundColor Green
    } else {
        Set-ItemProperty -Path $regPath -Name "AllowInsecureGuestAuth" -Value 1 -Type DWord
        Write-Host "✓ Enabled guest authentication" -ForegroundColor Green
    }
} catch {
    Write-Host "ERROR: Could not configure guest auth - $_" -ForegroundColor Red
}
Write-Host ""

# Step 7: Flush DNS cache
Write-Host "STEP 7: Flushing DNS and NetBIOS cache" -ForegroundColor Yellow
Write-Host "---------------------------------------" -ForegroundColor Yellow

try {
    ipconfig /flushdns | Out-Null
    nbtstat -R | Out-Null
    Write-Host "✓ Flushed DNS and NetBIOS cache" -ForegroundColor Green
} catch {
    Write-Host "Note: Could not flush cache" -ForegroundColor Gray
}
Write-Host ""

# Step 8: Restart workstation service
Write-Host "STEP 8: Restarting Workstation service" -ForegroundColor Yellow
Write-Host "---------------------------------------" -ForegroundColor Yellow

try {
    Restart-Service LanmanWorkstation -Force -ErrorAction Stop
    Write-Host "✓ Workstation service restarted" -ForegroundColor Green
    Start-Sleep -Seconds 3
} catch {
    Write-Host "Could not restart service - reboot may be required" -ForegroundColor Yellow
}
Write-Host ""

# Step 9: Test connection
Write-Host "STEP 9: Testing share access" -ForegroundColor Yellow
Write-Host "-----------------------------" -ForegroundColor Yellow

$sharePath = "\\$TargetServer\$ShareName"

# Try to connect
Write-Host "Attempting to connect to $sharePath ..." -ForegroundColor Gray

try {
    # First try net use
    $connectResult = net use $sharePath 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Connected successfully via net use!" -ForegroundColor Green
    } else {
        Write-Host "net use result: $connectResult" -ForegroundColor Yellow
    }
} catch {
    Write-Host "net use failed: $_" -ForegroundColor Yellow
}

# Try to access via Test-Path
try {
    $testResult = Test-Path $sharePath -ErrorAction Stop
    if ($testResult) {
        Write-Host "✓ Share is accessible via Test-Path!" -ForegroundColor Green
        
        # Try to list contents
        $items = Get-ChildItem $sharePath -ErrorAction Stop | Select-Object -First 5
        if ($items) {
            Write-Host "✓ Can list share contents:" -ForegroundColor Green
            $items | ForEach-Object { Write-Host "    $($_.Name)" -ForegroundColor Gray }
        }
    } else {
        Write-Host "✗ Test-Path returned false" -ForegroundColor Red
    }
} catch {
    Write-Host "✗ Cannot access share: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "Diagnostics Complete" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

# Final recommendations
Write-Host "If the share still doesn't work:" -ForegroundColor Yellow
Write-Host "  1. REBOOT this PC (clears all cached sessions)" -ForegroundColor White
Write-Host "  2. Check that Windows Firewall allows SMB on the HOST PC" -ForegroundColor White
Write-Host "  3. On the HOST PC, run: Get-SmbShareAccess -Name '$ShareName'" -ForegroundColor White
Write-Host "  4. Try accessing by IP: \\$TargetServer\$ShareName" -ForegroundColor White
Write-Host ""

Read-Host "Press Enter to exit"
