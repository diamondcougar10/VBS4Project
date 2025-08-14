@echo off
setlocal
REM %~dp0 is the BAT folder; PS script sits next to it.
powershell -ExecutionPolicy Bypass -File "%~dp0RealityMeshProcess.ps1" "%~1"
endlocal
exit /b %errorlevel%

