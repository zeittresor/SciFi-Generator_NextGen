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

if not exist "logs" mkdir "logs" >nul 2>nul

 echo %ESC%[96m============================================================%ESC%[0m
 echo %ESC%[96m SciFi-Generator - Installer v%VERSION%%ESC%[0m
 echo %ESC%[96m============================================================%ESC%[0m

 echo %ESC%[93m[1/4] Checking Python...%ESC%[0m
where py >nul 2>nul
if not errorlevel 1 (
  set "PY=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo %ESC%[91m[ERROR] Python 3 was not found in PATH.%ESC%[0m
    echo Install Python 3.10 or newer and enable "Add Python to PATH".
    pause
    exit /b 1
  )
  set "PY=python"
)

%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo %ESC%[91m[ERROR] Python 3.10 or newer is required.%ESC%[0m
  pause
  exit /b 1
)

 echo %ESC%[93m[2/4] Creating or reusing project-local virtual environment...%ESC%[0m
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
) else (
  echo %ESC%[90m[INFO] Existing .venv will be reused.%ESC%[0m
)

 echo %ESC%[93m[3/4] Installing dependencies...%ESC%[0m
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :fail
if exist "wheelhouse\*.whl" (
  echo %ESC%[90m[INFO] Installing from local wheelhouse.%ESC%[0m
  ".venv\Scripts\python.exe" -m pip install --no-index --find-links wheelhouse -r requirements.txt
) else (
  echo %ESC%[90m[INFO] No wheelhouse found; using configured Python package index.%ESC%[0m
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
if errorlevel 1 goto :fail

 echo %ESC%[93m[4/4] Verifying application files...%ESC%[0m
".venv\Scripts\python.exe" "tools\verify_installation.py"
if errorlevel 1 goto :fail

 echo %ESC%[92m[OK] Installation completed successfully.%ESC%[0m
 echo Press N to skip auto-start, or wait 10 seconds.
choice /C YN /N /T 10 /D Y /M "Start application now? [Y/N] "
if errorlevel 2 exit /b 0
start "SciFi-Generator" ".venv\Scripts\pythonw.exe" "%CD%\app.py"
exit /b 0

:fail
 echo %ESC%[91m[ERROR] Installation failed.%ESC%[0m
 echo %ESC%[90m[INFO] Installer version: %VERSION%%ESC%[0m
pause
exit /b 1
