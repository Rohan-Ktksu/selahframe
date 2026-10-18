# Windows installation

The active checkout is D:\SelahFrame, with its own .venv, tools and voices.
Python 3.12 is recommended. All rendering uses the CPU; no CUDA is required.

## Fresh checkout

Install Python 3.12 from https://www.python.org/downloads/windows/ and run:

```powershell
cd D:\SelahFrame
powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\setup-media-windows.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\doctor-windows.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start-windows.ps1
```

Media setup downloads Piper and the en_US-ljspeech-medium voice, and a portable
FFmpeg essentials build with ffprobe. The FFmpeg ZIP is checked against its published
SHA-256. Tools stay under the project drive; no system PATH change is required.
Use -SkipFFmpeg or -SkipVoice when supplying your own reviewed installation.
If .env sets an older voice, update PIPER_MODEL=en_US-ljspeech-medium.
The default was changed after reviewing the Lessac dataset's research license.
See THIRD_PARTY.md. Existing custom environment settings are preserved.

## First project

1. Open http://127.0.0.1:8000. Paste the exact permitted passage, its translation,
   source URL, license and adjacent context. The app records your verification;
   it does not independently certify scripture or permissions.
2. Choose the abstract placeholder pack explicitly, or upload images with a source
   and license/ownership statement. Images are decoded, re-encoded and limited to
   12 MB by default, 20 million pixels, and 24 uploaded images per project.
3. Write narration manually, save and approve the saved version. Editing revokes
   approval. Aim for roughly 110-135 words; output duration follows the actual voice.
4. Select 720p for faster drafts or 1080p for a full-HD export. Watch the job stages.
5. Watch/download the MP4. Review narration, interpretation, picture rights and
   approximate caption timing before distribution. Voice narration is AI-generated.

The app stores data/projects.sqlite3, output/PROJECT/exports/JOB and temp/JOB.
Exports contain MP4, WAV, SRT, ASS, selected images and export.json. Scratch stays
local until you explicitly archive and remove it; the app never deletes originals.
MAX_RENDER_DISK_GB caps retained scratch plus the current export; MAX_UPLOAD_MB caps
image payloads. Free disk space is checked. At most one render/upload job runs.
A process lock prevents two app servers from claiming the same checkout.

## Tests and real rendering

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
# Stop the web server before running a developer smoke test:
.\.venv\Scripts\python.exe scripts\smoke-render.py --quality 1080p --full
```

The smoke script approves only its fixed technical demonstration narration and
creates a visible demo project. It uses the verified public-domain text at
https://ebible.org/eng-web/PSA023.htm. It must not be used to approve user drafts.

## Optional drafting and Drive

Install Ollama from https://ollama.com/download/windows, then run
`ollama pull gemma3:1b`. The app can continue with manually entered narration.

Install rclone from https://rclone.org/downloads/. Follow https://rclone.org/drive/
for current browser OAuth and own-client instructions. Run `rclone config`, create a
Drive remote named bibledrive, authorize in your browser, then test
`rclone lsd bibledrive:`. Never put credentials in this checkout or in chat.

The upload button queues a job for the selected export at
bibledrive:Bible-AI-Studio/Projects/UUID. Copy is followed by a one-way size check;
status verified-size means names and sizes matched, not a checksum assertion.
Edits and rendering are blocked during upload. Failures preserve local files.
Google authorization and a real Drive transfer remain untested on this machine.

## Troubleshooting

- Missing media tools: run doctor-windows.ps1 and setup-media-windows.ps1.
- Wrong voice: check PIPER_MODEL and PIPER_DATA_DIR in .env.
- Scratch budget: archive old output/scratch, then manually remove only the scratch
  you have safely archived, or increase MAX_RENDER_DISK_GB. Keep original images.
- Interrupted job: restart, review the displayed error and explicitly retry.
- Already running: use the existing server or stop it before starting another.
- External host/origin rejected: open the exact localhost URL on port 8000.
