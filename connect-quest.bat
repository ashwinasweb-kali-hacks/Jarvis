@echo off
setlocal
title JARVIS-OS - Link Meta Quest 3 over USB
cd /d "%~dp0"

set "ADB="
for %%p in (adb.exe) do if not "%%~$PATH:p"=="" set "ADB=%%~$PATH:p"
if not defined ADB if exist "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" set "ADB=%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
if not defined ADB if exist "C:\platform-tools\adb.exe" set "ADB=C:\platform-tools\adb.exe"
if not defined ADB if exist "%LOCALAPPDATA%\Programs\SideQuest\adb.exe" set "ADB=%LOCALAPPDATA%\Programs\SideQuest\adb.exe"
if not defined ADB if exist "%PROGRAMFILES%\SideQuest\adb.exe" set "ADB=%PROGRAMFILES%\SideQuest\adb.exe"

if not defined ADB (
  echo.
  echo   adb was not found on this PC.
  echo   1^) Enable Developer Mode for this PC in the Meta Horizon app.
  echo   2^) Install Android Platform Tools:
  echo      https://developer.android.com/tools/releases/platform-tools
  echo   3^) Plug the Quest in over USB, accept "Allow USB debugging".
  echo   4^) Run this script again.
  echo.
  pause
  exit /b 1
)

echo Using: %ADB%
"%ADB%" start-server >nul 2>nul
echo.
echo Waiting for the headset (up to 5 minutes).
echo   - Put the headset ON.
echo   - Look for the "Allow USB debugging?" prompt and tap ALLOW
echo     (tick "Always allow from this computer" so it stops asking).
echo   - Use a data-capable USB-C cable.
echo.

set "STATE="
set /a TRIES=0
:waitloop
set "STATE="
for /f "skip=1 tokens=1,2" %%a in ('"%ADB%" devices') do if not "%%b"=="" set "STATE=%%b"
if "%STATE%"=="device" goto haveDevice
if "%STATE%"=="unauthorized" (
  if %TRIES% GTR 0 if %TRIES% LSS 3 echo   Still waiting for you to tap ALLOW on the headset...
) else (
  if %TRIES% GTR 0 if %TRIES% LSS 3 echo   No headset yet - plug the cable in...
)
set /a TRIES+=1
if %TRIES% GEQ 150 goto noDevice
ping -n 3 127.0.0.1 >nul 2>nul
goto waitloop

:noDevice
echo.
echo Still no authorised headset.
echo  - Put the headset on and accept the "Allow USB debugging" prompt.
echo  - Developer Mode must be enabled for this PC in the Meta Horizon app.
echo  - Charge-only USB cables do not carry data.
echo.
pause
exit /b 1

:haveDevice
"%ADB%" reverse --remove tcp:8765 >nul 2>nul
"%ADB%" reverse tcp:8765 tcp:8765
if errorlevel 1 (
  echo.
  echo Reverse tunnel failed. Reconnect the USB cable and try again.
  echo.
  pause
  exit /b 1
)

curl -s -o nul --max-time 2 http://127.0.0.1:8765/api/status 2>nul
if errorlevel 1 (
  echo Daemon is not running - starting it in the background...
  if exist "%~dp0.venv\Scripts\python.exe" (
    powershell -NoProfile -Command "Start-Process -FilePath '%~dp0.venv\Scripts\python.exe' -ArgumentList '-m','jarvis.daemon' -WorkingDirectory '%~dp0' -WindowStyle Hidden"
  ) else (
    powershell -NoProfile -Command "Start-Process -FilePath 'python' -ArgumentList '-m','jarvis.daemon' -WorkingDirectory '%~dp0' -WindowStyle Hidden"
  )
  timeout /t 8 /nobreak >nul
)

set "SCHEME=http"
curl -s -o nul --max-time 3 http://127.0.0.1:8765/api/status 2>nul
if errorlevel 1 set "SCHEME=https"

set "URL=%SCHEME%://localhost:8765/"
echo.
echo ========================================================
echo   Headset link ready.
echo.
echo   In the headset: Meta Quest Browser -> %URL%
echo   (or it opens automatically in a moment)
echo.
echo   AR MODE button in the app = Quest 3 passthrough.
echo ========================================================
"%ADB%" shell am start -a android.intent.action.VIEW -d "%URL%" >nul 2>nul
if errorlevel 1 (
  echo Could not launch it automatically. Type the URL above into Meta Quest Browser.
) else (
  echo Launched. Put the headset on and look for the JARVIS HUD.
)
echo.
pause

