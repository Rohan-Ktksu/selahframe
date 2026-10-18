# Windows setup and first-video checklist

Install Python 3.12 from https://www.python.org/downloads/windows/ (the Store aliases
alone are insufficient). From the project folder in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\doctor-windows.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start-windows.ps1
```

Open http://127.0.0.1:8000. Manual scripts and saved projects work without Ollama.
This checkout already has a Python 3.12 virtual environment for API development.
Do not copy that environment to another machine; run setup there.

## Media dependencies

Install FFmpeg including ffprobe using a Windows build linked from
https://ffmpeg.org/download.html. Add its bin folder to PATH and reopen PowerShell.
Confirm `ffmpeg -version` and `ffprobe -version`.

Review the maintained Piper license and the selected voice's model card before
redistributing any package or output that has additional voice conditions:

- https://github.com/OHF-Voice/piper1-gpl
- https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD

Install and inspect the CLI, then download the voice into the ignored voices folder:

```powershell
.\.venv\Scripts\python.exe -m pip install piper-tts
.\.venv\Scripts\python.exe -m piper --help
Push-Location voices
..\.venv\Scripts\python.exe -m piper.download_voices en_US-lessac-medium
Pop-Location
```

These media steps were not executed in this checkpoint. The app supplies narration
on stdin using `-m`, `--data-dir` and `-f`; verify against the installed Piper version.
Optional drafting: install https://ollama.com/download/windows then run
`ollama pull gemma3:1b`. The model download requires disk space and internet.

## First real export (pending)

1. Paste a permitted, verified passage; fill translation/source/license and adjacent context.
2. Explicitly select abstract placeholders, or add licensed images.
3. Write a short manual narration, save, then approve the exact saved revision.
4. Render; inspect errors via Check status. Fix dependencies and retry if necessary.
5. Play the preview and download. Confirm audible voice and no truncation.
6. Inspect the output, substituting the displayed UUID:

```powershell
ffprobe -v error -show_entries stream=codec_name,width,height -show_entries format=duration -of json .\output\PROJECT_UUID\final.mp4
```

Current renderer targets 720x1280 H.264/AAC image slides. Captions, motion and 1080p
are not yet implemented. The export JSON records the AI-voice disclosure and approval.

## Optional Drive

Install https://rclone.org/downloads/. Follow https://rclone.org/drive/ for the current
OAuth and own-client process. Run `rclone config`, create a drive remote named
`bibledrive`, authorize in your browser, then test `rclone lsd bibledrive:`.
Never paste tokens or client secrets into the app, chat or repository.
The upload button copies to Bible-AI-Studio/Projects/UUID and checks file sizes.
Do not edit or render that project while upload is running. Files are retained locally.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use isolated temporary databases and mocked media/Drive tools. They do not
prove a playable export or successful Google authorization.
