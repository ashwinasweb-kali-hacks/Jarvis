@echo off
title JARVIS-OS - Private Wi-Fi for the Quest
cd /d "%~dp0"

echo.
echo   This creates a private Wi-Fi network (JARVIS-HUD) on this PC so the
echo   Meta Quest can reach the JARVIS daemon without the USB debugging prompt.
echo.
echo   It needs administrator rights, so Windows will ask you to allow it.
echo.

powershell -NoProfile -Command "Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','%~dp0start-hotspot.ps1' -Verb RunAs"

echo.
echo   If nothing happened, right-click this file and choose
echo   "Run as administrator" instead.
echo.
pause
