@echo off
title Hugging Face Login
cd /d "%~dp0"
echo ========================================================
echo  Hugging Face Login for Indic Parler-TTS
echo ========================================================
echo.
echo  Before continuing:
echo   1. Open https://huggingface.co/ai4bharat/indic-parler-tts
echo      Log in and click "Agree and access repository".
echo   2. Create a token (type: Read) at
echo      https://huggingface.co/settings/tokens
echo.
echo  Paste the token below when asked (it will be hidden as you type).
echo  Answer "n" if asked about adding it as a git credential.
echo.
call .venv\Scripts\activate.bat
huggingface-cli login
echo.
huggingface-cli whoami
echo.
echo If your username is shown above, login succeeded. Restart the app.
pause
