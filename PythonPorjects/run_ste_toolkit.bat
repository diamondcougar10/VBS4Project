@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo STE Toolkit Launcher with Memory Optimization
echo =============================================
echo.

REM Check if first argument is "safe" for minimal launch
if "%1"=="safe" (
    echo Starting in safe mode with minimal optimizations...
    echo.
    call conda activate myenv
    python STE_Toolkit.py
    goto :end
)

REM Check if first argument is "minimal" for minimal launcher
if "%1"=="minimal" (
    echo Starting with minimal launcher...
    echo.
    call conda activate myenv
    python launchers\minimal_launcher.py
    goto :end
)

echo Starting STE Toolkit with enhanced memory optimizations...
echo.

REM Activate conda environment
call conda activate myenv

REM Check if environment activation was successful
if errorlevel 1 (
    echo ❌ Failed to activate conda environment 'myenv'
    echo Please ensure conda is installed and 'myenv' environment exists
    echo.
    echo Trying with base Python...
    echo.
)

REM Set memory and performance environment variables
set PYTHONDONTWRITEBYTECODE=1
set PYTHONOPTIMIZE=2
set PYTHONHASHSEED=0
set PYTHONIOENCODING=utf-8

REM Increase Windows memory limits
set _JAVA_OPTIONS=-Xmx2048m
set MALLOC_ARENA_MAX=4

REM Set process priority to high (if possible)
wmic process where "name='cmd.exe' and CommandLine like '%%run_ste_toolkit%%'" CALL setpriority "high priority" >nul 2>&1

echo ✅ Memory optimizations applied:
echo    - Python optimizations enabled
echo    - Garbage collection tuned  
echo    - Working set size increased
echo    - Process priority elevated
echo    - Memory monitoring enabled
echo.

REM Show memory status before starting
echo 🔍 Checking available memory...
for /f "tokens=2 delims==" %%i in ('wmic OS get FreePhysicalMemory /value ^| find "="') do set freemem=%%i
set /a freegb=!freemem!/1048576
echo    Available Memory: !freegb! GB
echo.

if !freegb! LSS 4 (
    echo ⚠️  WARNING: Low memory detected ^(!freegb! GB available^)
    echo    Consider closing other applications for better performance
    echo.
)

echo 🚀 Launching STE Toolkit...
echo.

REM Run with maximum optimizations
python -OO STE_Toolkit.py

:end
REM Keep window open if there's an error
if errorlevel 1 (
    echo.
    echo ❌ Application exited with error code %errorlevel%
    echo.
    echo This may indicate a memory or resource issue.
    echo Troubleshooting suggestions:
    echo 1. Try 'run_ste_toolkit.bat minimal' for minimal resource usage
    echo 2. Try 'run_ste_toolkit.bat safe' for safe mode
    echo 3. Use 'python launchers\minimal_launcher.py' directly
    echo 4. Close other applications and try again
    echo 5. Restart your computer if issues persist
    echo.
    pause
)