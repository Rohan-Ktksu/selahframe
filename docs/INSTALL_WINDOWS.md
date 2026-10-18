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
4. Arrange scenes using the thumbnail editor. Move scenes up/down, include/exclude
   them, set time weights and choose zoom in, zoom out or still. A weight of 2 gets
   roughly twice the screen time of 1. Save the plan. Seconds shown use the last
   narration as an estimate; the actual render follows the new narration duration.
5. Select 720p for faster drafts or 1080p for a full-HD export. Watch the job stages.
6. Watch/download the MP4. Review narration, interpretation, picture rights and
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

## Scene-editor regression

With the server running, execute:

```powershell
.\.venv\Scripts\python.exe scripts\smoke-scenes.py
```

This creates labeled geometric test cards, uploads them with provenance, reorders
blue before red, gives blue twice the time, excludes green, renders and decodes frames
to check their actual color/order. It verifies that excluded originals remain intact.
The technical test narration is explicitly approved by this developer script.
It never approves user drafts or uploads anything to an external service.

## Optional music and regression

In section 4, import a local WAV, MP3 or FLAC, record the source/license and confirm
permission. Preview the imported track, enable it, choose a background level and
save. Render again to apply changes. Imports always start with music off. Short
tracks loop to fit the voice; fades and speech ducking are automatic. All original
tracks are retained. MAX_MUSIC_MB defaults to 25; the limit is also shown by the UI.
No music provider, extra package or account is required.

With local media tools installed, run the measured audio check:

```powershell
.\.venv\Scripts\python.exe scripts\smoke-music.py
```

With the server running, append --render to also create an explicitly reviewed
technical demo and verify narration-only and music-enabled exports, media receipts,
HTTP ranges and cache reuse. The script generates its own audio fixture; it does not
approve user drafts or obtain music from an external service. A human should listen
to the final preview for subjective balance and voice quality.
