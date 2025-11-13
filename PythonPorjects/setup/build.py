#!/usr/bin/env python3
"""
STE Toolkit Build Script - Python Build Orchestrator
=====================================================
Purpose: Builds PyInstaller dist + Inno Setup installer using Python

Edit points:
  - APP_NAME: Change to match your app
  - ENTRY_SCRIPT: Entry point for PyInstaller
  - SPEC_FILE: Path to your .spec file
  - ISS_FILE: Path to your Inno Setup script
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ============================================================================
# Configuration
# ============================================================================
APP_NAME = "STE_Toolkit"
ENTRY_SCRIPT = "STE_Toolkit.py"
SPEC_FILE = "STE_Toolkit.spec"
ISS_FILE = "setup/STE_Toolkit.iss"
VENV_DIR = ".venv"
DIST_DIR = "dist"
BUILD_DIR = "build"
RELEASES_DIR = "releases"

# ============================================================================
# Helper Functions
# ============================================================================

def print_step(step_num, total, message):
    """Print a formatted step message."""
    print(f"\n[{step_num}/{total}] {message}...")
    print("-" * 80)

def run_command(cmd, cwd=None, check=True):
    """Run a command and return the result."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            shell=True,
            check=check,
            capture_output=True,
            text=True
        )
        return result
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Command failed with exit code {e.returncode}")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        raise

def get_version():
    """Get version from src/__version__.py, git, or default to 0.0.0."""
    version = None
    
    # Try src/__version__.py
    version_file = Path("src/__version__.py")
    if version_file.exists():
        content = version_file.read_text()
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            version = match.group(1)
            print(f"  Found in src/__version__.py: {version}")
            return version
    
    # Try git describe
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True,
            text=True,
            check=True
        )
        version = result.stdout.strip()
        if version:
            print(f"  Found from git: {version}")
            return version
    except Exception:
        pass
    
    # Default
    version = "0.0.0"
    print(f"  Using default: {version}")
    return version

def ensure_venv():
    """Ensure virtual environment exists and return path to Python."""
    venv_path = Path(VENV_DIR)
    python_exe = venv_path / "Scripts" / "python.exe"
    
    if not python_exe.exists():
        print(f"  Creating virtual environment: {VENV_DIR}")
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
    else:
        print(f"  Virtual environment exists: {VENV_DIR}")
    
    return str(python_exe)

def install_dependencies(python_exe):
    """Install dependencies from requirements.txt."""
    requirements_file = Path("requirements.txt")
    
    # Upgrade pip
    print("  Upgrading pip...")
    subprocess.run([python_exe, "-m", "pip", "install", "--upgrade", "pip"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if requirements_file.exists():
        print(f"  Installing from {requirements_file}...")
        try:
            subprocess.run([python_exe, "-m", "pip", "install", "-r", str(requirements_file)],
                          check=True)
        except subprocess.CalledProcessError:
            print("  WARNING: Some dependencies may have failed to install")
    else:
        print(f"  WARNING: {requirements_file} not found")
        print("  Installing minimal dependencies: pyinstaller, pillow")
        subprocess.run([python_exe, "-m", "pip", "install", "pyinstaller", "pillow"],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def clean_build_artifacts():
    """Clean previous build artifacts."""
    dist_app = Path(DIST_DIR) / APP_NAME
    build_app = Path(BUILD_DIR) / APP_NAME
    
    if dist_app.exists():
        print(f"  Removing {dist_app}")
        shutil.rmtree(dist_app, ignore_errors=True)
    
    if build_app.exists():
        print(f"  Removing {build_app}")
        shutil.rmtree(build_app, ignore_errors=True)

def run_pyinstaller(python_exe):
    """Run PyInstaller with the spec file."""
    spec_path = Path(SPEC_FILE)
    
    if not spec_path.exists():
        print(f"  ERROR: Spec file not found: {SPEC_FILE}")
        raise FileNotFoundError(SPEC_FILE)
    
    print(f"  Using spec file: {SPEC_FILE}")
    subprocess.run([python_exe, "-m", "PyInstaller", "--clean", "--noconfirm", str(spec_path)],
                   check=True)
    
    # Verify output
    exe_path = Path(DIST_DIR) / APP_NAME / f"{APP_NAME}.exe"
    if not exe_path.exists():
        print(f"  ERROR: PyInstaller did not produce expected output")
        print(f"  Expected: {exe_path}")
        raise FileNotFoundError(exe_path)
    
    print("  PyInstaller build successful!")

def find_inno_setup():
    """Find Inno Setup compiler."""
    locations = [
        Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
        Path("C:/Program Files/Inno Setup 6/ISCC.exe"),
    ]
    
    for loc in locations:
        if loc.exists():
            print(f"  Found: {loc}")
            return str(loc)
    
    print("  ERROR: Inno Setup 6 not found in standard locations")
    print("  Please install from: https://jrsoftware.org/isdl.php")
    print("\n  Looked in:")
    for loc in locations:
        print(f"    - {loc.parent}")
    raise FileNotFoundError("ISCC.exe")

def run_inno_setup(iscc_path, version):
    """Run Inno Setup to create installer."""
    iss_path = Path(ISS_FILE)
    
    if not iss_path.exists():
        print(f"  ERROR: Inno Setup script not found: {ISS_FILE}")
        raise FileNotFoundError(ISS_FILE)
    
    # Create releases directory
    releases_path = Path(RELEASES_DIR)
    releases_path.mkdir(exist_ok=True)
    
    # Build command
    source_dir = (Path.cwd() / DIST_DIR / APP_NAME).absolute()
    output_dir = (Path.cwd() / RELEASES_DIR).absolute()
    
    cmd = [
        iscc_path,
        str(iss_path),
        f"/DMyAppVersion={version}",
        f'/DSourceDir={source_dir}',
        f'/O{output_dir}'
    ]
    
    print(f"  Compiling installer...")
    subprocess.run(cmd, check=True)
    
    print("  Inno Setup compilation successful!")

# ============================================================================
# Main Build Process
# ============================================================================

def main():
    """Main build orchestration."""
    try:
        print("=" * 80)
        print("STE TOOLKIT BUILD PIPELINE")
        print("=" * 80)
        
        # Step 1: Get version
        print_step(1, 7, "Resolving version")
        version = get_version()
        
        # Step 2: Setup venv
        print_step(2, 7, "Setting up Python virtual environment")
        python_exe = ensure_venv()
        
        # Step 3: Install dependencies
        print_step(3, 7, "Installing dependencies")
        install_dependencies(python_exe)
        
        # Step 4: Clean artifacts
        print_step(4, 7, "Cleaning previous build artifacts")
        clean_build_artifacts()
        
        # Step 5: Run PyInstaller
        print_step(5, 7, "Running PyInstaller")
        run_pyinstaller(python_exe)
        
        # Step 6: Find Inno Setup
        print_step(6, 7, "Locating Inno Setup")
        iscc_path = find_inno_setup()
        
        # Step 7: Run Inno Setup
        print_step(7, 7, "Running Inno Setup")
        run_inno_setup(iscc_path, version)
        
        # Success!
        print("\n" + "=" * 80)
        print("BUILD SUCCESSFUL!")
        print("=" * 80)
        print(f"Version: {version}")
        print(f"Installer: {RELEASES_DIR}/STE_Toolkit_Setup.exe")
        print("=" * 80)
        print()
        
        return 0
        
    except Exception as e:
        print("\n" + "=" * 80)
        print("BUILD FAILED!")
        print("=" * 80)
        print(f"Error: {e}")
        print("=" * 80)
        return 1

if __name__ == "__main__":
    sys.exit(main())
