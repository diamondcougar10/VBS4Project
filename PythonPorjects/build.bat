@echo off
REM ============================================================================
REM STE Toolkit Build Script - One-Click Build Pipeline
REM ============================================================================
REM Purpose: Builds PyInstaller dist + Inno Setup installer in one command
REM
REM Edit points:
REM   - APP_NAME: Change to match your app
REM   - ENTRY_SCRIPT: Entry point for PyInstaller
REM   - SPEC_FILE: Path to your .spec file
REM   - ISS_FILE: Path to your Inno Setup script
REM ============================================================================

REM Change to the directory where this script is located
cd /d "%~dp0"

setlocal enabledelayedexpansion

REM --- Configuration ---
set "APP_NAME=STE_Toolkit"
set "ENTRY_SCRIPT=STE_Toolkit.py"
set "SPEC_FILE=STE_Toolkit.spec"
set "ISS_FILE=setup\STE_Toolkit.iss"
set "VENV_DIR=.venv"
set "DIST_DIR=dist"
set "BUILD_DIR=build"
set "RELEASES_DIR=BUILDS"

REM --- Get version ---
echo [1/7] Resolving version...
set "VERSION="

REM Try reading from src\__version__.py
if exist "src\__version__.py" (
    for /f "usebackq tokens=2 delims='" %%a in (`findstr "__version__" src\__version__.py`) do (
        set "VERSION=%%a"
    )
)

REM Fallback to git describe
if "!VERSION!"=="" (
    for /f "delims=" %%a in ('git describe --tags --always 2^>nul') do set "VERSION=%%a"
)

REM Final fallback
if "!VERSION!"=="" set "VERSION=0.0.0"

echo Version: !VERSION!

REM --- Ensure venv exists ---
echo.
echo [2/7] Setting up Python virtual environment...
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Creating new virtual environment...
    py -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        exit /b 1
    )
)

REM --- Activate venv ---
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment
    exit /b 1
)

REM --- Install/update dependencies ---
echo.
echo [3/7] Installing dependencies...
if exist "requirements.txt" (
    python -m pip install --upgrade pip >nul 2>&1
    pip install -r requirements.txt
    if errorlevel 1 (
        echo WARNING: Some dependencies may have failed to install
    )
) else (
    echo WARNING: requirements.txt not found, skipping dependency install
    REM Install minimal required packages
    pip install pyinstaller pillow >nul 2>&1
)

REM --- Clean previous build ---
echo.
echo [4/7] Cleaning previous build artifacts...
if exist "%DIST_DIR%\%APP_NAME%" (
    echo Removing %DIST_DIR%\%APP_NAME%...
    rmdir /s /q "%DIST_DIR%\%APP_NAME%" 2>nul
)
if exist "%BUILD_DIR%\%APP_NAME%" (
    echo Removing %BUILD_DIR%\%APP_NAME%...
    rmdir /s /q "%BUILD_DIR%\%APP_NAME%" 2>nul
)

REM --- Run PyInstaller ---
echo.
echo [5/7] Running PyInstaller...
if exist "%SPEC_FILE%" (
    echo Using spec file: %SPEC_FILE%
    python -m PyInstaller --clean --noconfirm "%SPEC_FILE%"
    if errorlevel 1 (
        echo ERROR: PyInstaller build failed
        pause
        exit /b 1
    )
) else (
    echo ERROR: Spec file not found: %SPEC_FILE%
    pause
    exit /b 1
)

REM --- Verify PyInstaller output ---
if not exist "%DIST_DIR%\%APP_NAME%\%APP_NAME%.exe" (
    echo ERROR: PyInstaller did not produce expected output
    echo Expected: %DIST_DIR%\%APP_NAME%\%APP_NAME%.exe
    exit /b 1
)

echo PyInstaller build successful!

REM --- Find Inno Setup ---
echo.
echo [6/7] Locating Inno Setup...
set "ISCC="
set "ISCC_PATH_1=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
set "ISCC_PATH_2=C:\Program Files\Inno Setup 6\ISCC.exe"

if exist "%ISCC_PATH_1%" set "ISCC=%ISCC_PATH_1%"
if exist "%ISCC_PATH_2%" if "!ISCC!"=="" set "ISCC=%ISCC_PATH_2%"

if "!ISCC!"=="" (
    echo ERROR: Inno Setup 6 not found in standard locations
    echo Please install from: https://jrsoftware.org/isdl.php
    echo.
    echo Looked in:
    echo   - C:\Program Files ^(x86^)\Inno Setup 6\
    echo   - C:\Program Files\Inno Setup 6\
    exit /b 1
)

echo Found: !ISCC!

REM --- Create releases directory ---
if not exist "%RELEASES_DIR%" mkdir "%RELEASES_DIR%"

REM --- Run Inno Setup ---
echo.
echo [7/7] Running Inno Setup (this may take 5-10 minutes)...
echo.
echo IMPORTANT: Please be patient - compression takes time!
echo Started at: %TIME%
echo.

REM Run Inno Setup with direct console output
"!ISCC!" "%ISS_FILE%" /DMyAppVersion=!VERSION! /DSourceDir="%CD%\%DIST_DIR%\%APP_NAME%" /O"%CD%\%RELEASES_DIR%"
set ISCC_EXIT_CODE=!ERRORLEVEL!

echo.
echo Build ended at %TIME% with exit code !ISCC_EXIT_CODE!
echo.

if !ISCC_EXIT_CODE! NEQ 0 (
    echo.
    echo ============================================================================
    echo ERROR: Inno Setup compilation failed with error code !ISCC_EXIT_CODE!
    echo ============================================================================
    echo.
    echo Troubleshooting:
    echo   1. Review the output above for error messages
    echo   2. Verify all source files exist in dist\%APP_NAME%
    echo   3. Ensure BUILDS directory is writable
    echo   4. Try running with administrator privileges
    echo.
    pause
    exit /b 1
)

echo.
echo Inno Setup completed successfully!

REM --- Success ---
echo.
echo ============================================================================
echo BUILD SUCCESSFUL!
echo ============================================================================
echo Version: !VERSION!
echo Installer: %RELEASES_DIR%\STE_Toolkit_Setup.exe
echo Completed at: %TIME%
echo ============================================================================
echo.

REM --- Optional cleanup: remove PyInstaller exe & intermediate folders so only installer remains ---
echo Cleaning intermediate PyInstaller output to retain only final installer...
if exist "%DIST_DIR%\%APP_NAME%\%APP_NAME%.exe" del /q "%DIST_DIR%\%APP_NAME%\%APP_NAME%.exe" >nul 2>&1
REM Remove empty dist app folder if desired
if exist "%DIST_DIR%\%APP_NAME%" rmdir /s /q "%DIST_DIR%\%APP_NAME%" >nul 2>&1
REM Keep build/ for debug unless user wants full cleanup
echo Cleanup complete. Only %RELEASES_DIR%\STE_Toolkit_Setup.exe should remain.

pause

exit /b 0
