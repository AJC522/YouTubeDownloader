@echo off
rem Video Download Manager - double-click this file to set up and launch.
rem It runs setup.ps1 with the execution policy bypassed for this run only,
rem so no PowerShell configuration is needed.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
if errorlevel 1 (
    echo.
    echo Setup did not finish successfully. See the messages above.
    pause
)
