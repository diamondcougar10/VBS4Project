# Clear SMB Credentials and Sessions for PC 3 (192.168.10.116)
# This script clears cached credentials and active SMB sessions that may be causing
# "The password is invalid" errors when connecting to \\192.168.10.201\SharedMeshDrive
#
# Run this script as Administrator on the PC that cannot connect

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "SMB Credential and Session Cleanup Tool" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click the script and select 'Run as Administrator'" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Running as Administrator - OK" -ForegroundColor Green
Write-Host ""

# Step 1: Show current SMB sessions
Write-Host "Step 1: Current SMB Sessions" -ForegroundColor Yellow
Write-Host "----------------------------" -ForegroundColor Yellow
try {
    $sessions = net use
    if ($sessions) {
        Write-Host $sessions
    } else {
        Write-Host "No active SMB sessions found" -ForegroundColor Gray
    }
} catch {
    Write-Host "Could not query SMB sessions: $_" -ForegroundColor Red
}
Write-Host ""

# Step 2: Delete all SMB sessions
Write-Host "Step 2: Deleting ALL SMB Sessions" -ForegroundColor Yellow
Write-Host "---------------------------------" -ForegroundColor Yellow
try {
    $result = net use * /delete /yes 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ All SMB sessions deleted successfully" -ForegroundColor Green
    } else {
        Write-Host "Note: $result" -ForegroundColor Gray
    }
} catch {
    Write-Host "Could not delete SMB sessions: $_" -ForegroundColor Red
}
Write-Host ""

# Step 3: Show current cached credentials
Write-Host "Step 3: Current Cached Credentials" -ForegroundColor Yellow
Write-Host "----------------------------------" -ForegroundColor Yellow
try {
    $creds = cmdkey /list
    Write-Host $creds
} catch {
    Write-Host "Could not query credentials: $_" -ForegroundColor Red
}
Write-Host ""

# Step 4: Delete credentials for 192.168.10.201
Write-Host "Step 4: Deleting Credentials for 192.168.10.201" -ForegroundColor Yellow
Write-Host "-----------------------------------------------" -ForegroundColor Yellow
$deletedCount = 0

try {
    $credList = cmdkey /list | Out-String
    
    # Look for IP-based credentials
    if ($credList -match "Target:.*192\.168\.10\.201") {
        $credMatches = [regex]::Matches($credList, "Target:\s*([^\r\n]*192\.168\.10\.201[^\r\n]*)")
        foreach ($match in $credMatches) {
            $target = $match.Groups[1].Value.Trim()
            Write-Host "Deleting: $target" -ForegroundColor Cyan
            cmdkey /delete:$target 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $deletedCount++
                Write-Host "  ✓ Deleted" -ForegroundColor Green
            } else {
                Write-Host "  ✗ Failed to delete" -ForegroundColor Red
            }
        }
    }
    
    # Look for hostname-based credentials (KIT1-1 is the host machine)
    if ($credList -match "Target:.*KIT1-1") {
        $credMatches = [regex]::Matches($credList, "Target:\s*([^\r\n]*KIT1-1[^\r\n]*)")
        foreach ($match in $credMatches) {
            $target = $match.Groups[1].Value.Trim()
            Write-Host "Deleting: $target" -ForegroundColor Cyan
            cmdkey /delete:$target 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $deletedCount++
                Write-Host "  ✓ Deleted" -ForegroundColor Green
            } else {
                Write-Host "  ✗ Failed to delete" -ForegroundColor Red
            }
        }
    }
    
    if ($deletedCount -eq 0) {
        Write-Host "No credentials found for 192.168.10.201 or KIT1-1" -ForegroundColor Gray
    } else {
        Write-Host "✓ Deleted $deletedCount credential(s)" -ForegroundColor Green
    }
} catch {
    Write-Host "Error deleting credentials: $_" -ForegroundColor Red
}
Write-Host ""

# Step 5: Verify network connectivity
Write-Host "Step 5: Verifying Network Connectivity" -ForegroundColor Yellow
Write-Host "--------------------------------------" -ForegroundColor Yellow

Write-Host "Pinging 192.168.10.201..." -ForegroundColor Cyan
try {
    $ping = Test-Connection -ComputerName 192.168.10.201 -Count 2 -Quiet
    if ($ping) {
        Write-Host "✓ Host is reachable via ping" -ForegroundColor Green
    } else {
        Write-Host "✗ Host is NOT reachable via ping" -ForegroundColor Red
        Write-Host "  Check network cable, firewall, or VPN connection" -ForegroundColor Yellow
    }
} catch {
    Write-Host "✗ Ping failed: $_" -ForegroundColor Red
}
Write-Host ""

Write-Host "Testing SMB Port (445)..." -ForegroundColor Cyan
try {
    $portTest = Test-NetConnection -ComputerName 192.168.10.201 -Port 445 -WarningAction SilentlyContinue
    if ($portTest.TcpTestSucceeded) {
        Write-Host "✓ SMB port 445 is open" -ForegroundColor Green
    } else {
        Write-Host "✗ SMB port 445 is CLOSED or blocked" -ForegroundColor Red
        Write-Host "  Check firewall settings on both PCs" -ForegroundColor Yellow
    }
} catch {
    Write-Host "✗ Port test failed: $_" -ForegroundColor Red
}
Write-Host ""

# Step 6: Check Windows Firewall
Write-Host "Step 6: Windows Firewall File Sharing Status" -ForegroundColor Yellow
Write-Host "--------------------------------------------" -ForegroundColor Yellow
try {
    $firewallProfiles = Get-NetFirewallProfile
    foreach ($fwProfile in $firewallProfiles) {
        $status = if ($fwProfile.Enabled) { "ON" } else { "OFF" }
        $color = if ($fwProfile.Enabled) { "Yellow" } else { "Green" }
        Write-Host "$($fwProfile.Name) Profile: Firewall $status" -ForegroundColor $color
    }
    
    # Check if File and Printer Sharing is enabled
    $fileSharingRules = Get-NetFirewallRule | Where-Object { 
        $_.DisplayName -like "*File and Printer Sharing*" -and $_.Enabled -eq $true 
    }
    if ($fileSharingRules) {
        Write-Host "✓ File and Printer Sharing rules are enabled" -ForegroundColor Green
    } else {
        Write-Host "✗ File and Printer Sharing rules are NOT enabled" -ForegroundColor Red
        Write-Host "  Enable in: Control Panel → Windows Firewall → Allow an app" -ForegroundColor Yellow
    }
} catch {
    Write-Host "Could not check firewall status: $_" -ForegroundColor Red
}
Write-Host ""

# Step 7: Summary and next steps
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "CLEANUP COMPLETE" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Open STE_Toolkit on this PC" -ForegroundColor White
Write-Host "2. Go to Settings → Offline/Shared → Manual Connect" -ForegroundColor White
Write-Host "3. Enter:" -ForegroundColor White
Write-Host "   - Host IP: 192.168.10.201" -ForegroundColor Gray
Write-Host "   - Share Name: SharedMeshDrive" -ForegroundColor Gray
Write-Host "   - Username: [username with access to the share]" -ForegroundColor Gray
Write-Host "   - Password: [password]" -ForegroundColor Gray
Write-Host "4. Click 'Test Connection' first" -ForegroundColor White
Write-Host "5. If test passes, click 'Connect & Save'" -ForegroundColor White
Write-Host ""
Write-Host "If you still have issues:" -ForegroundColor Yellow
Write-Host "- Verify the username/password works from File Explorer:" -ForegroundColor White
Write-Host "  Type in address bar: \\192.168.10.201\SharedMeshDrive" -ForegroundColor Gray
Write-Host "- Check share permissions on the host PC (192.168.10.201)" -ForegroundColor White
Write-Host ""

Read-Host "Press Enter to exit"
