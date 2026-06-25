@echo off
rem One-click installer for Windows.
rem Right-click and "Run as administrator" to also configure the firewall
rem and (optionally) auto-start with Windows.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows.ps1" %*
echo.
pause
