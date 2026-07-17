@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist "version.txt" (
  echo [ERROR] version.txt was not found.
  pause
  exit /b 1
)
set /p "VERSION="<"version.txt"
for /F "delims=" %%E in ('echo prompt $E^| cmd') do set "ESC=%%E"
echo %ESC%[96mSciFi-Generator %VERSION% - Wheelhouse Builder%ESC%[0m
if not exist ".venv\Scripts\python.exe" (
  echo %ESC%[91m[ERROR] Run install_windows.bat first.%ESC%[0m
  pause
  exit /b 1
)
if not exist wheelhouse mkdir wheelhouse
".venv\Scripts\python.exe" -m pip download --dest wheelhouse -r requirements.txt
if errorlevel 1 (
  echo %ESC%[91m[ERROR] Wheelhouse build failed.%ESC%[0m
  pause
  exit /b 1
)
echo %ESC%[92m[OK] Offline wheels are in wheelhouse.%ESC%[0m
pause
