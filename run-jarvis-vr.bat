@echo off
setlocal
title JARVIS-OS Workshop Daemon (HTTPS / Quest AR-VR)
cd /d "%~dp0"
set JARVIS_TLS=1
rem HTTPS runs on 8766 so it never fights the plain-HTTP daemon on 8765.
rem (On Windows two sockets can bind the same port, which silently mixes schemes.)
set JARVIS_DAEMON_PORT=8766
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

for /f "delims=" %%i in ('powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Dhcp,Manual -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '169.254*' -and $_.IPAddress -ne '127.0.0.1' } | Select-Object -First 1).IPAddress"') do set "LANIP=%%i"
if "%LANIP%"=="" set "LANIP=<this-pc-ip>"

echo ========================================================
echo    J.A.R.V.I.S. - HTTPS MODE (META QUEST AR / VR)
echo ========================================================
echo Starting JARVIS daemon with a local self-signed certificate.
echo In the headset the certificate warning appears ONCE:
echo   Advanced  ^>  Proceed to ^<ip^>
echo After that the page is a secure context and WebXR + mic work.
echo.
echo Headset URL:  https://%LANIP%:8766/
echo Desktop URL:  https://127.0.0.1:8766/
echo.
echo USB instead? Run run-jarvis.bat + connect-quest.bat for a warning-free link.
echo.
where adb >nul 2>nul
if not errorlevel 1 (
  adb reverse tcp:8765 tcp:8765 >nul 2>nul
  if not errorlevel 1 echo ADB reverse is on: in the headset you can also use http://localhost:8765/ ^(no warning, but USB required^).
)
echo ========================================================
start "" /b "%PYTHON%" -m jarvis.daemon
timeout /t 3 /nobreak >nul
start https://127.0.0.1:8766/
echo Keep this window open. Ctrl+C or close it to stop the daemon.
echo ========================================================
pause
