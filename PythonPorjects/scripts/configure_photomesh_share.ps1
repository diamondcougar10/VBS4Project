# Configure PhotoMesh Shared Drive for Fuser Access
# Run this script as Administrator on the machine hosting the SharedMeshDrive
#
# This script:
# 1. Creates a dedicated PhotoMesh user account (optional)
# 2. Configures share permissions for Everyone with full access
# 3. Sets NTFS permissions
# 4. Enables necessary SMB settings

param(
    [string]$SharePath = "D:\SharedMeshDrive",  # Change to your actual share path
    [string]$ShareName = "SharedMeshDrive",
    [switch]$CreateUser,
    [string]$PhotoMeshUser = "PhotoMeshAccess",
    [Parameter(Mandatory = $false)]
    [System.Security.SecureString]$PhotoMeshPassword  # Will prompt if -CreateUser is used and no password provided
)

# Generate a default password if CreateUser is set but no password provided
$PlainPassword = ""
if ($CreateUser) {
    if ($PhotoMeshPassword) {
        # Only convert to plain text for user creation, do not display or log it
        $PlainPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($PhotoMeshPassword)
        )
    } else {
        # Generate a random password
        $PlainPassword = "PM" + [guid]::NewGuid().ToString().Substring(0, 8) + "!"
        Write-Host "Generated password: $PlainPassword" -ForegroundColor Yellow
    }
}

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "PhotoMesh Share Configuration Tool" -ForegroundColor Cyan
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
Write-Host ""

# ============================================
# OPTION 1: Enable Guest Access (Quick Fix)
# ============================================
Write-Host "Step 1: Configuring SMB Server Settings" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Yellow

# Enable SMB1 and SMB2 (if needed for older clients)
try {
    # Allow guest access on the SERVER side
    Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters" -Name "RestrictNullSessAccess" -Value 0 -ErrorAction SilentlyContinue
    Write-Host "✓ Configured null session access" -ForegroundColor Green
} catch {
    Write-Host "Note: Could not configure null session - $_" -ForegroundColor Yellow
}

# ============================================
# OPTION 2: Create Dedicated User (Recommended)
# ============================================
if ($CreateUser) {
    Write-Host ""
    Write-Host "Step 2: Creating PhotoMesh User Account" -ForegroundColor Yellow
    Write-Host "----------------------------------------" -ForegroundColor Yellow
    
    # Check if user already exists
    $userExists = Get-LocalUser -Name $PhotoMeshUser -ErrorAction SilentlyContinue
    
    if ($userExists) {
        Write-Host "User '$PhotoMeshUser' already exists" -ForegroundColor Gray
    } else {
        try {
            $securePassword = ConvertTo-SecureString $PlainPassword -AsPlainText -Force
            New-LocalUser -Name $PhotoMeshUser -Password $securePassword -PasswordNeverExpires -Description "PhotoMesh Fuser Access Account" -ErrorAction Stop
            Write-Host "✓ Created user: $PhotoMeshUser" -ForegroundColor Green
            
            # Add to Users group
            Add-LocalGroupMember -Group "Users" -Member $PhotoMeshUser -ErrorAction SilentlyContinue
            Write-Host "✓ Added to Users group" -ForegroundColor Green
        } catch {
            Write-Host "ERROR creating user: $_" -ForegroundColor Red
        }
    }
}

# ============================================
# Step 3: Configure Share Permissions
# ============================================
Write-Host ""
Write-Host "Step 3: Configuring Share Permissions" -ForegroundColor Yellow
Write-Host "--------------------------------------" -ForegroundColor Yellow

# Check if share path exists
if (-not (Test-Path $SharePath)) {
    Write-Host "Share path does not exist: $SharePath" -ForegroundColor Red
    Write-Host "Please update the -SharePath parameter to your actual path" -ForegroundColor Yellow
    
    # Try to find existing shares
    Write-Host ""
    Write-Host "Existing shares on this machine:" -ForegroundColor Cyan
    Get-SmbShare | Where-Object { $_.Name -notlike "*$" } | Format-Table Name, Path, Description
    
} else {
    # Remove existing share if present
    $existingShare = Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue
    if ($existingShare) {
        Write-Host "Updating existing share: $ShareName" -ForegroundColor Gray
        Remove-SmbShare -Name $ShareName -Force -ErrorAction SilentlyContinue
    }
    
    # Create new share with full access for Everyone
    try {
        New-SmbShare -Name $ShareName -Path $SharePath -FullAccess "Everyone" -Description "PhotoMesh Working Directory" -ErrorAction Stop
        Write-Host "✓ Created share: \\$env:COMPUTERNAME\$ShareName" -ForegroundColor Green
        Write-Host "  Path: $SharePath" -ForegroundColor Gray
    } catch {
        Write-Host "ERROR creating share: $_" -ForegroundColor Red
    }
    
    # Grant share permissions
    try {
        Grant-SmbShareAccess -Name $ShareName -AccountName "Everyone" -AccessRight Full -Force -ErrorAction Stop
        Write-Host "✓ Granted Full share access to Everyone" -ForegroundColor Green
    } catch {
        Write-Host "Note: $_" -ForegroundColor Yellow
    }
    
    # Set NTFS permissions
    Write-Host ""
    Write-Host "Step 4: Setting NTFS Permissions" -ForegroundColor Yellow
    Write-Host "---------------------------------" -ForegroundColor Yellow
    
    try {
        $acl = Get-Acl $SharePath
        
        # Add Everyone with Full Control
        $everyoneRule = New-Object System.Security.AccessControl.FileSystemAccessRule("Everyone", "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow")
        $acl.SetAccessRule($everyoneRule)
        
        # Add Users group with Full Control
        $usersRule = New-Object System.Security.AccessControl.FileSystemAccessRule("Users", "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow")
        $acl.SetAccessRule($usersRule)
        
        Set-Acl -Path $SharePath -AclObject $acl
        Write-Host "✓ Set NTFS permissions for Everyone and Users" -ForegroundColor Green
    } catch {
        Write-Host "ERROR setting NTFS permissions: $_" -ForegroundColor Red
    }
}

# ============================================
# Step 5: Configure Firewall
# ============================================
Write-Host ""
Write-Host "Step 5: Configuring Firewall" -ForegroundColor Yellow
Write-Host "-----------------------------" -ForegroundColor Yellow

try {
    # Enable File and Printer Sharing
    Set-NetFirewallRule -DisplayGroup "File And Printer Sharing" -Enabled True -Profile Any -ErrorAction SilentlyContinue
    Write-Host "✓ Enabled File and Printer Sharing in firewall" -ForegroundColor Green
} catch {
    Write-Host "Note: Could not configure firewall - $_" -ForegroundColor Yellow
}

# ============================================
# Step 6: Disable Password Protected Sharing (Optional)
# ============================================
Write-Host ""
Write-Host "Step 6: Network Sharing Settings" -ForegroundColor Yellow
Write-Host "---------------------------------" -ForegroundColor Yellow

# This allows access without password (like guest access)
try {
    # Turn off password protected sharing via registry
    $regPath = "HKLM:\SYSTEM\CurrentControlSet\Control\Lsa"
    Set-ItemProperty -Path $regPath -Name "everyoneincludesanonymous" -Value 1 -ErrorAction SilentlyContinue
    Write-Host "✓ Configured anonymous access settings" -ForegroundColor Green
    
    # Also update Network and Sharing Center settings
    $netSharePath = "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters"
    Set-ItemProperty -Path $netSharePath -Name "restrictnullsessaccess" -Value 0 -ErrorAction SilentlyContinue
    Write-Host "✓ Configured null session access" -ForegroundColor Green
} catch {
    Write-Host "Note: $_" -ForegroundColor Yellow
}

# ============================================
# Summary
# ============================================
Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "Configuration Complete!" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Share Details:" -ForegroundColor White
Write-Host "  UNC Path: \\$env:COMPUTERNAME\$ShareName" -ForegroundColor Cyan
Write-Host "  IP Path:  \\$(([System.Net.Dns]::GetHostAddresses($env:COMPUTERNAME) | Where-Object { $_.AddressFamily -eq 'InterNetwork' } | Select-Object -First 1).IPAddressToString)\$ShareName" -ForegroundColor Cyan
Write-Host ""

if ($CreateUser) {
    Write-Host "User Credentials (for Fuser machines):" -ForegroundColor White
    Write-Host "  Username: $PhotoMeshUser" -ForegroundColor Cyan
    Write-Host "  Password: $PlainPassword" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "On each Fuser machine, run:" -ForegroundColor Yellow
    Write-Host "  net use \\$env:COMPUTERNAME\$ShareName /user:$PhotoMeshUser `"$PlainPassword`" /persistent:yes" -ForegroundColor White
    
    # Clear password from memory
    $PlainPassword = $null
}

Write-Host ""
Write-Host "IMPORTANT: You may need to restart the Server service or reboot." -ForegroundColor Yellow
Write-Host "Run: Restart-Service LanmanServer -Force" -ForegroundColor Gray
Write-Host ""

# Offer to restart the service
$restart = Read-Host "Restart LanmanServer service now? (Y/N)"
if ($restart -eq 'Y' -or $restart -eq 'y') {
    try {
        Restart-Service LanmanServer -Force
        Write-Host "✓ LanmanServer service restarted" -ForegroundColor Green
    } catch {
        Write-Host "Could not restart service. Please reboot the machine." -ForegroundColor Yellow
    }
}

Write-Host ""
Read-Host "Press Enter to exit"
