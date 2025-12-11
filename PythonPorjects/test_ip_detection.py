"""Test IP detection and host configuration"""
import subprocess
import os

NO_WINDOW_FLAG = 0x08000000

# Test 1: IP Detection with Ethernet preference
print("=" * 60)
print("TEST 1: IP Detection (Prefers Ethernet over WiFi)")
print("=" * 60)

ps_cmd = (
    "$eth = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
    "Where-Object { $_.IPAddress -notmatch '^169\\.254\\.' -and $_.IPAddress -ne '127.0.0.1' -and $_.PrefixOrigin -in @('Dhcp','Manual') } | "
    "ForEach-Object { $iface = Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue; "
    "[PSCustomObject]@{ IP=$_.IPAddress; Name=$iface.Name; IsEthernet=($iface.Name -match 'Ethernet|LAN|Wired') } } | "
    "Sort-Object @{Expression={$_.IsEthernet}; Descending=$true}, @{Expression={$_.IP}} | "
    "Select-Object -First 1; "
    "if ($eth) { Write-Host \"Detected IP: $($eth.IP)\"; Write-Host \"Interface: $($eth.Name)\"; Write-Host \"Is Ethernet: $($eth.IsEthernet)\" }"
)

result = subprocess.run(
    ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
    capture_output=True,
    text=True,
    timeout=5
)

print(result.stdout)
if result.stderr:
    print("Errors:", result.stderr)

# Test 2: Check if D:\SharedMeshDrive exists
print("\n" + "=" * 60)
print("TEST 2: Shared Drive Check")
print("=" * 60)

shared_drive = r"D:\SharedMeshDrive"
if os.path.isdir(shared_drive):
    print(f"✓ Shared drive exists: {shared_drive}")
    
    # Check for beacon file
    beacon_path = os.path.join(shared_drive, "HostInfo.ini")
    if os.path.isfile(beacon_path):
        print(f"✓ Beacon file exists: {beacon_path}")
        with open(beacon_path, 'r') as f:
            print("\nBeacon content:")
            print(f.read())
    else:
        print(f"✗ Beacon file NOT found: {beacon_path}")
else:
    print(f"✗ Shared drive NOT found: {shared_drive}")

# Test 3: Check current SMB share
print("\n" + "=" * 60)
print("TEST 3: SMB Share Check")
print("=" * 60)

ps_share = "Get-SmbShare -Name 'SharedMeshDrive' -ErrorAction SilentlyContinue | Select-Object Name, Path, Description | Format-List"
result = subprocess.run(
    ["powershell.exe", "-NoProfile", "-Command", ps_share],
    capture_output=True,
    text=True,
    timeout=5
)

if result.stdout.strip():
    print("Current SMB Share:")
    print(result.stdout)
else:
    print("✗ SMB Share 'SharedMeshDrive' not found")

# Test 4: Check config.ini
print("\n" + "=" * 60)
print("TEST 4: Config.ini Check")
print("=" * 60)

config_path = "config.ini"
if os.path.isfile(config_path):
    print(f"✓ Config file: {config_path}")
    import configparser
    config = configparser.ConfigParser()
    config.read(config_path)
    
    if 'Offline' in config:
        print("\n[Offline] section:")
        print(f"  host_ip: '{config['Offline'].get('host_ip', '')}'")
        print(f"  host_name: '{config['Offline'].get('host_name', '')}'")
        print(f"  local_data_root: '{config['Offline'].get('local_data_root', '')}'")
        print(f"  share_name: '{config['Offline'].get('share_name', '')}'")
    
    if 'Fusers' in config:
        print("\n[Fusers] section:")
        print(f"  shared_working_unc: '{config['Fusers'].get('shared_working_unc', '')}'")
else:
    print(f"✗ Config file not found: {config_path}")

print("\n" + "=" * 60)
print("Test Complete")
print("=" * 60)
