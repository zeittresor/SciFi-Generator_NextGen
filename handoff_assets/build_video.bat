@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
title SciFi-Generator - Gesamtpaket bauen

echo ============================================================
echo  SciFi-Generator - illustrierte Audiogeschichte bauen
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python wurde nicht im PATH gefunden.
    echo Installiere Python 3.10 oder neuer und versuche es erneut.
    pause
    exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 if not exist "tools\ffmpeg.exe" (
    echo [ERROR] FFmpeg wurde nicht gefunden.
    echo Installiere FFmpeg oder lege ffmpeg.exe und ffprobe.exe in tools\ ab.
    pause
    exit /b 1
)

echo [INFO] Das Skript verwendet vorhandene images\scene_XX.png-Dateien.
echo [INFO] Fehlende scene_XX.wav-Dateien werden unter Windows per TTS erzeugt.
echo [INFO] Abbruch jederzeit mit Strg+C.
echo.
python build_story_video.py
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
    echo [ERROR] Produktion fehlgeschlagen. Details: production.log
) else (
    echo [OK] scifi_story.mp4 und scifi_story_package.zip wurden erzeugt.
)
pause
exit /b %RC%
