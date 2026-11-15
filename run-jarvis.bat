@echo off
title JARVIS-OS Workshop Daemon
cd /d "%~dp0"
echo ========================================================
echo        J.A.R.V.I.S. - STARK INDUSTRIES WORKSHOP
echo ========================================================
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
echo Starting JARVIS AI Daemon (OAuth + Neural Speech)...
start "" /b "%PYTHON%" -m jarvis.daemon
timeout /t 2 /nobreak >nul
echo Opening Workshop Glass HUD on http://127.0.0.1:8765/ ...
start http://127.0.0.1:8765/
echo.
echo JARVIS is active and standing by.
echo Keep this window open in background.
echo.
echo Headset (Meta Quest 3 over USB)? Run connect-quest.bat in this folder.
echo ========================================================
pause
