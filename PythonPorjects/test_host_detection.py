"""Test script to verify Host machine detection logic"""
import configparser
import socket
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Read config
config = configparser.ConfigParser()
config.read('config.ini')

print("=" * 60)
print("HOST DETECTION TEST")
print("=" * 60)
print()

# Method 1: Check local_data_root
local_root = config.get('Offline', 'local_data_root', fallback='').strip()
local_root_exists = os.path.isdir(local_root) if local_root else False
print("Method 1: Local Data Root Check")
print(f"  local_data_root: {local_root if local_root else '(not set)'}")
print(f"  Directory exists: {local_root_exists}")
print(f"  Result: {'✓ IS HOST' if local_root_exists and local_root else '✗ Not Host'}")
print()

# Method 2: Check machine name match
computer_name = socket.gethostname().split('.')[0].upper()
working_folder_host = config.get('Fusers', 'working_folder_host', fallback='').split('.')[0].upper()
names_match = computer_name == working_folder_host if working_folder_host else False
print("Method 2: Machine Name Match")
print(f"  Computer name: {computer_name}")
print(f"  Working folder host: {working_folder_host if working_folder_host else '(not set)'}")
print(f"  Names match: {names_match}")
print(f"  Result: {'✓ IS HOST' if names_match else '✗ Not Host'}")
print()

# Method 3: Check IP match
host_ip = config.get('Offline', 'host_ip', fallback='').strip()
print("Method 3: IP Address Match")
print(f"  Configured host IP: {host_ip if host_ip else '(not set)'}")

# Get this PC's IP (simplified - would use get_primary_ipv4() in real code)
try:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    my_ip = s.getsockname()[0]
    s.close()
    print(f"  This PC's IP: {my_ip}")
    ip_match = my_ip == host_ip if host_ip else False
    print(f"  IPs match: {ip_match}")
    print(f"  Result: {'✓ IS HOST' if ip_match else '✗ Not Host'}")
except Exception as e:
    print(f"  Could not determine IP: {e}")
    ip_match = False
    print(f"  Result: ✗ Not Host (IP check failed)")
print()

# Final determination
is_host = local_root_exists or names_match or ip_match
print("=" * 60)
print(f"FINAL RESULT: {'✓✓✓ THIS PC IS THE HOST ✓✓✓' if is_host else '✗✗✗ THIS PC IS NOT THE HOST ✗✗✗'}")
print("=" * 60)
print()

if is_host:
    print("The System Status box SHOULD be visible on the OneClick panel.")
else:
    print("The System Status box will NOT be visible on the OneClick panel.")
    print()
    print("To make this PC the Host, set one of:")
    print("  1. [Offline] local_data_root = D:\\SharedMeshDrive (and create the folder)")
    print("  2. [Fusers] working_folder_host = " + computer_name)
    print("  3. Ensure [Offline] host_ip matches this PC's actual IP")
