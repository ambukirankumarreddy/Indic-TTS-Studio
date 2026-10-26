# Indic TTS Studio: Installer Build Plan

Target: Windows PCs with an NVIDIA GPU. Single `Setup.exe` (Inno Setup).
Models bundled for fully offline use. No account or API key needed.

## Layout of the installed app

```
<InstallDir>\
  python\            full CPython 3.12 (has tkinter) + site-packages from .venv
  app\               *.py, engines\, ui\, config files
  models\            hf\hub (Parler, VoxCPM2, flan-t5), piper, kokoro, syspin
  generated_audio\   (created per user, in %USERPROFILE%\Documents)
  Launch.bat / IndicTTSStudio.exe shortcut -> python\pythonw.exe app\main.py
```

## Why not PyInstaller
torch + CUDA + parler-tts + sherpa-onnx break or bloat badly when frozen.
Copying a real Python and its site-packages is more reliable.

## Steps
1. Stage: copy base Python 3.12 -> `build\stage\python`, copy `.venv\Lib\site-packages`
   over its `Lib\site-packages` (site-packages are relocatable).
2. Stage app code + models (exclude `.venv`, `__pycache__`, logs, history, test audio).
3. Smoke test the STAGED copy (not the dev venv) with `OFFLINE=1`.
4. Compile `installer.iss` with Inno Setup -> `Setup.exe`.
5. Test install into a clean folder, launch, synthesize offline.

## Known caveats
- Installer size: roughly 10-15 GB (torch CUDA ~4 GB, models ~8 GB).
- Parler-TTS weights are gated on Hugging Face; bundled for personal/team use only.
- Piper voices are CC BY-NC-SA (non-commercial). ElevenLabs removed (needs API key).
- Edge voices need internet; hidden when offline mode is on.
