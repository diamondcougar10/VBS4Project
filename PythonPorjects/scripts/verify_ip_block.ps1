# Verify IP Block Status for 192.168.1.193
# Run this script to check if the old host IP is blocked

Write-Host "`n=== IP Block Verification for 192.168.1.193 ===" -ForegroundColor Cyan

# Check firewall rules
Write-Host "`n1. Checking Firewall Rules..." -ForegroundColor Yellow
$rules = Get-NetFirewallRule -DisplayName "*192.168.1.193*" -ErrorAction SilentlyContinue
if ($rules) {
    $rules | Select-Object DisplayName, Enabled, Direction, Action | Format-Table -AutoSize
    Write-Host "✓ Firewall rules are active" -ForegroundColor Green
} else {
    Write-Host "✗ No firewall rules found for 192.168.1.193" -ForegroundColor Red
    Write-Host "  Run this to create them (as Admin):" -ForegroundColor Yellow
    Write-Host '  New-NetFirewallRule -DisplayName "Block Old Host IP 192.168.1.193" -Direction Outbound -RemoteAddress 192.168.1.193 -Action Block -Enabled True'
    Write-Host '  New-NetFirewallRule -DisplayName "Block Old Host IP 192.168.1.193 (Inbound)" -Direction Inbound -RemoteAddress 192.168.1.193 -Action Block -Enabled True'
}

# Check if IP is reachable (should fail if blocked)
Write-Host "`n2. Testing Connection (should fail if blocked)..." -ForegroundColor Yellow
$ping = Test-Connection -ComputerName 192.168.1.193 -Count 1 -Quiet -ErrorAction SilentlyContinue
if ($ping) {
    Write-Host "⚠ WARNING: IP 192.168.1.193 is still reachable!" -ForegroundColor Red
    Write-Host "  Firewall rules may not be active or configured correctly." -ForegroundColor Yellow
} else {
    Write-Host "✓ IP 192.168.1.193 is blocked (not reachable)" -ForegroundColor Green
}

# Check SMB connections
Write-Host "`n3. Checking SMB Connections..." -ForegroundColor Yellow
$smbConn = net use | Select-String "192.168.1.193"
if ($smbConn) {
    Write-Host "✗ Active SMB connection found:" -ForegroundColor Red
    $smbConn
    Write-Host "  Run: net use \\192.168.1.193 /delete /yes" -ForegroundColor Yellow
} else {
    Write-Host "✓ No SMB connections to 192.168.1.193" -ForegroundColor Green
}

# Check current toolkit config
Write-Host "`n4. Checking Toolkit Configuration..." -ForegroundColor Yellow
$configPath = "C:\Program Files\STE Toolkit\config.ini"
if (Test-Path $configPath) {
    $hostIpLine = Get-Content $configPath | Select-String "^host_ip\s*=" | Select-Object -First 1
    if ($hostIpLine) {
        Write-Host "  Current Host IP: $($hostIpLine.Line)" -ForegroundColor Cyan
        if ($hostIpLine.Line -match "192\.168\.1\.193") {
            Write-Host "  ✗ WARNING: Config still references 192.168.1.193!" -ForegroundColor Red
        } else {
            Write-Host "  ✓ Config does not reference 192.168.1.193" -ForegroundColor Green
        }
    }
} else {
    Write-Host "  Config not found at $configPath" -ForegroundColor Yellow
}

Write-Host "`n=== Verification Complete ===" -ForegroundColor Cyan
Write-Host ""
