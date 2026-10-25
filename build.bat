@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*
if errorlevel 1 (
    echo Build failed. See the error above.
    pause
    exit /b 1
)
echo The application is in the dist folder.
pause
