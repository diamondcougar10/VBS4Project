@echo off
setlocal
if "%~1"=="" (
  echo ERROR: missing settings file path
  exit /b 2
)
set "SETTINGS_FILE=%~1"
echo Using settings: %SETTINGS_FILE%
powershell -executionpolicy bypass -File ".\RealityMeshProcess.ps1" "%SETTINGS_FILE%"
exit /b %errorlevel%

