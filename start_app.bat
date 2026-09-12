@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run install_windows.bat first.
  pause
  exit /b 1
)
if not exist "logs" mkdir "logs" >nul 2>nul
".venv\Scripts\python.exe" launcher.py
if errorlevel 1 (
  echo.
  echo [ERROR] SciFi-Generator could not be started.
  echo [INFO] Diagnostic log: "%CD%\logs\startup_error.log"
  pause
  exit /b 1
)
