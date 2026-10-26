@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*
if errorlevel 1 (
    echo Build failed. See the error above.
    pause
    exit /b 1
)
echo Single-file and folder distributions are in the selected output folder, dist by default.
pause
