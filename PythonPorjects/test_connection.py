"""
Test connection to new host IP 192.168.6.140
"""
import os
import subprocess
import sys

def test_share_connection(host_ip, share_name, working_subdir):
    """Test SMB share connectivity"""
    print(f"\n=== Testing Connection to {host_ip} ===\n")
    
    # Test 1: Basic ping
    print(f"1. Testing network connectivity...")
    result = subprocess.run(
        ["ping", "-n", "2", host_ip],
        capture_output=True,
        text=True,
        timeout=10
    )
    if "TTL=" in result.stdout:
        print(f"   ✓ Ping successful")
    else:
        print(f"   ✗ Ping failed")
        return False
    
    # Test 2: UNC path accessibility
    unc_root = f"\\\\{host_ip}\\{share_name}"
    unc_working = f"{unc_root}\\{working_subdir}"
    
    print(f"\n2. Testing share root access: {unc_root}")
    if os.path.exists(unc_root):
        print(f"   ✓ Share root accessible")
    else:
        print(f"   ✗ Share root not accessible")
        return False
    
    print(f"\n3. Testing working folder: {unc_working}")
    if os.path.exists(unc_working):
        print(f"   ✓ Working folder accessible")
    else:
        print(f"   ✗ Working folder not accessible")
        return False
    
    # Test 3: List contents
    print(f"\n4. Listing share contents...")
    try:
        items = os.listdir(unc_root)
        print(f"   ✓ Found {len(items)} items in share root")
        if items:
            print(f"   First few items: {items[:5]}")
    except Exception as e:
        print(f"   ✗ Failed to list contents: {e}")
        return False
    
    # Test 4: Write test
    test_file = os.path.join(unc_working, "test_connection.tmp")
    print(f"\n5. Testing write access...")
    try:
        with open(test_file, 'w') as f:
            f.write("Connection test successful")
        print(f"   ✓ Write successful")
        os.remove(test_file)
        print(f"   ✓ Cleanup successful")
    except Exception as e:
        print(f"   ✗ Write failed: {e}")
        return False
    
    print(f"\n=== All Tests Passed ✓ ===\n")
    return True

if __name__ == "__main__":
    success = test_share_connection(
        host_ip="192.168.6.140",
        share_name="SharedMeshDrive",
        working_subdir="WorkingFuser"
    )
    sys.exit(0 if success else 1)
