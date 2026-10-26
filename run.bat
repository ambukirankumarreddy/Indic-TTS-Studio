@echo off
setlocal
title Indic TTS Studio
cd /d "%~dp0"

rem ---- Locate Python: installed layout (python\) first, then dev venv (.venv\) ----
set "PY="
if exist "python\pythonw.exe" set "PY=python\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

if not defined PY (
    echo [!] No Python runtime found. Reinstall Indic TTS Studio.
    echo     Expected .\python\python.exe or .\.venv\Scripts\python.exe
    pause
    exit /b 1
)

rem ---- Optional: run fully offline with  run.bat --offline ----
if /i "%~1"=="--offline" set "OFFLINE=1"

rem App code lives in .\app when installed, or right here in the dev folder.
if exist "app\main.py" ( cd app )

"%PY%" main.py
if errorlevel 1 (
    echo.
    echo [!] Application exited with an error.
    pause
)
endlocal
