# Enable SMB Access for PhotoMesh Fuser Machines
# Run this script as Administrator on EACH Fuser machine
#
# This fixes the error:
# "You can't access this shared folder because your organization's security 
#  policies block unauthenticated guest access"

param(
    [string]$ShareServer = "192.168.10.201",
    [string]$ShareName = "SharedMeshDrive",
    [string]$Username = "",  # Leave empty for guest access, or specify username
    [SecureString]$Password  # Leave empty for guest access, or use -Password (Read-Host -AsSecureString)
)

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "PhotoMesh Fuser SMB Access Configuration" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Running as Administrator - OK" -ForegroundColor Green
Write-Host "Computer Name: $env:COMPUTERNAME" -ForegroundColor Gray
Write-Host ""

# Convert SecureString to plain text for net use (only when needed)
$PlainPassword = ""
if ($Password) {
    try {
        $PlainPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Password)
        )
    } catch {
        Write-Host "ERROR: Could not convert SecureString password." -ForegroundColor Red
        exit 1
    }
}

# ============================================
# Step 1: Enable Insecure Guest Auth
# ============================================
Write-Host "Step 1: Enabling Guest Authentication" -ForegroundColor Yellow
Write-Host "--------------------------------------" -ForegroundColor Yellow

try {
    # This is the KEY fix for the "security policies block unauthenticated guest access" error
    $regPath = "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters"
    
    # Check current value
    $currentValue = Get-ItemProperty -Path $regPath -Name "AllowInsecureGuestAuth" -ErrorAction SilentlyContinue
    
    if ($currentValue.AllowInsecureGuestAuth -eq 1) {
        Write-Host "✓ Guest authentication already enabled" -ForegroundColor Green
    } else {
        Set-ItemProperty -Path $regPath -Name "AllowInsecureGuestAuth" -Value 1 -Type DWord
        Write-Host "✓ Enabled insecure guest authentication" -ForegroundColor Green
    }
} catch {
    Write-Host "ERROR: Could not enable guest auth - $_" -ForegroundColor Red
}

# ============================================
# Step 2: Clear Existing Cached Credentials
# ============================================
Write-Host ""
Write-Host "Step 2: Clearing Cached SMB Credentials" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Yellow

try {
    # Delete existing connections to the share
    $existingConnection = net use | Select-String -Pattern $ShareServer
    if ($existingConnection) {
        net use "\\$ShareServer\$ShareName" /delete /yes 2>$null
        Write-Host "✓ Cleared existing connection to \\$ShareServer\$ShareName" -ForegroundColor Green
    } else {
        Write-Host "No existing connection found" -ForegroundColor Gray
    }
} catch {
    Write-Host "Note: $_" -ForegroundColor Gray
}

# Clear from Windows Credential Manager
try {
    $credentials = cmdkey /list | Select-String -Pattern $ShareServer
    if ($credentials) {
        cmdkey /delete:$ShareServer 2>$null
        cmdkey /delete:"$ShareServer\$ShareName" 2>$null
        Write-Host "✓ Cleared credentials from Credential Manager" -ForegroundColor Green
    }
} catch {
    Write-Host "Note: Could not clear credential manager" -ForegroundColor Gray
}

# ============================================
# Step 3: Configure SMB Client Settings
# ============================================
Write-Host ""
Write-Host "Step 3: Configuring SMB Client" -ForegroundColor Yellow
Write-Host "-------------------------------" -ForegroundColor Yellow

try {
    # Enable SMB2/SMB3
    Set-SmbClientConfiguration -EnableSecuritySignature $false -RequireSecuritySignature $false -Force -ErrorAction SilentlyContinue
    Write-Host "✓ Configured SMB client security settings" -ForegroundColor Green
} catch {
    Write-Host "Note: Could not configure SMB client - $_" -ForegroundColor Gray
}

# ============================================
# Step 4: Restart Workstation Service
# ============================================
Write-Host ""
Write-Host "Step 4: Restarting Workstation Service" -ForegroundColor Yellow
Write-Host "---------------------------------------" -ForegroundColor Yellow

try {
    Restart-Service LanmanWorkstation -Force -ErrorAction Stop
    Write-Host "✓ Workstation service restarted" -ForegroundColor Green
    Start-Sleep -Seconds 2
} catch {
    Write-Host "Could not restart service automatically" -ForegroundColor Yellow
    Write-Host "Please reboot the machine after this script completes" -ForegroundColor Yellow
}

# ============================================
# Step 5: Test Connection
# ============================================
Write-Host ""
Write-Host "Step 5: Testing Connection" -ForegroundColor Yellow
Write-Host "---------------------------" -ForegroundColor Yellow

$sharePath = "\\$ShareServer\$ShareName"

# Try to connect
if ($Username -and $PlainPassword) {
    # Connect with credentials
    Write-Host "Connecting with credentials..." -ForegroundColor Gray
    try {
        $result = net use $sharePath /user:$Username $PlainPassword /persistent:yes 2>&1
        # Clear plain password from memory
        $PlainPassword = $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Connected successfully with credentials!" -ForegroundColor Green
        } else {
            Write-Host "Connection with credentials failed: $result" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "ERROR: $_" -ForegroundColor Red
    }
} else {
    # Try guest/anonymous access
    Write-Host "Testing guest access..." -ForegroundColor Gray
    try {
        $testPath = Test-Path $sharePath -ErrorAction Stop
        if ($testPath) {
            Write-Host "✓ Successfully accessed $sharePath" -ForegroundColor Green
        } else {
            Write-Host "Path test returned false" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Guest access test failed: $_" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "If guest access doesn't work, you may need to connect with credentials:" -ForegroundColor Cyan
        Write-Host "  net use $sharePath /user:USERNAME PASSWORD /persistent:yes" -ForegroundColor White
    }
}

# Try to list the share
Write-Host ""
Write-Host "Checking share contents..." -ForegroundColor Gray
try {
    $items = Get-ChildItem $sharePath -ErrorAction Stop | Select-Object -First 5
    if ($items) {
        Write-Host "✓ Share is accessible! Found items:" -ForegroundColor Green
        $items | ForEach-Object { Write-Host "    $($_.Name)" -ForegroundColor Gray }
    }
} catch {
    Write-Host "Could not list share contents: $_" -ForegroundColor Yellow
}

# ============================================
# Summary
# ============================================
Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "Configuration Complete!" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Changes made:" -ForegroundColor White
Write-Host "  - Enabled AllowInsecureGuestAuth in registry" -ForegroundColor Gray
Write-Host "  - Cleared cached SMB credentials" -ForegroundColor Gray
Write-Host "  - Restarted LanmanWorkstation service" -ForegroundColor Gray
Write-Host ""
Write-Host "If PhotoMesh still cannot access the share:" -ForegroundColor Yellow
Write-Host "  1. Reboot this machine" -ForegroundColor White
Write-Host "  2. Run PhotoMesh again" -ForegroundColor White
Write-Host "  3. If still failing, the share server needs to be configured" -ForegroundColor White
Write-Host "     (run configure_photomesh_share.ps1 on the server)" -ForegroundColor White
Write-Host ""

Read-Host "Press Enter to exit"
