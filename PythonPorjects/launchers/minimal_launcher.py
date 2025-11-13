"""
Minimal STE Toolkit Launcher
Ultra-lightweight launcher to avoid memory issues
"""

import gc
import sys
import os

# Immediate memory optimization
gc.set_threshold(50, 5, 5)
for _ in range(5):
    gc.collect()

# Set minimal environment
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['PYTHONOPTIMIZE'] = '2'

print("🚀 Starting STE Toolkit with minimal resources...")

try:
    # Import and run the main application
    import STE_Toolkit
    print("✅ STE Toolkit launched successfully")
except Exception as e:
    print(f"❌ Launch failed: {e}")
    print("Try running emergency_launcher.bat for troubleshooting")