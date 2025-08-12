@echo off
setlocal
if "%~1"=="" (
  echo ERROR: missing settings file path
  exit /b 2
)
set "SETTINGS_FILE=%~1"
echo Using settings: %SETTINGS_FILE%
REM Use the directory of this batch file to locate the PowerShell script
powershell -executionpolicy bypass -File "%~dp0RealityMeshProcess.ps1" "%SETTINGS_FILE%"
exit /b %errorlevel%

