# SelahFrame

A private, local scripture video studio for Windows. Paste a verified passage,
write or draft narration, review and approve the exact script version, add licensed
images (or explicitly select abstract placeholders), then render a vertical MP4.

The CPU pipeline now produces 720p or 1080p H.264/AAC video with slow camera motion,
burned captions, a downloadable SRT, and an export manifest containing scripture,
approval and asset provenance. Caption timing is approximate, based on word counts.

```powershell
cd D:\SelahFrame
powershell -ExecutionPolicy Bypass -File .\scripts\start-windows.ps1
```

Open http://127.0.0.1:8000. The tools and voice are installed in this checkout.
For a fresh machine, run setup-windows.ps1 followed by setup-media-windows.ps1.
See [Windows installation](docs/INSTALL_WINDOWS.md), [API](docs/API.md),
[progress](docs/PROGRESS.md), and [third-party sources](docs/THIRD_PARTY.md).

Validation: a real 60.52-second 1080x1920 CPU export completed in 24.33 seconds on
this machine; codecs, duration, pixel format, audio signal and playback range requests
were checked. Sample frames were visually inspected. These timings are observations,
not performance guarantees. A listening review of the narration remains a user check.

Saved script versions, job progress, restart recovery, image provenance and immutable
exports are stored in SQLite. Only one job runs at a time. Interrupted jobs are marked
failed on restart and can be retried. Local exports work without Ollama or Drive.

Ollama remains optional and is not installed in this checkout. Drive uploads require
rclone and your browser OAuth authorization; no real Drive transfer has been tested.
Word alignment remains on the roadmap.
No public hosting or paid AI service is required. No automatic media cleanup occurs.
The source code is MIT; tools, models and supplied media retain their own licenses.

Scene editor: thumbnail previews, ordering, inclusion, relative time weights and
zoom-in/zoom-out/still motion are saved per project. Time weights share the measured
narration duration; shown seconds are estimates from the last narration. Changing
scenes preserves script approval and requires a new render. Excluded images remain
stored locally. The first uploaded image replaces the generated placeholder plan.

Optional music: import a local WAV, MP3 or FLAC with its source/license and permission
confirmation. Preview it, enable it and save a background level before rendering.
The default is narration only. Music loops to the measured narration length, fades
at both ends and is ducked beneath speech. Up to three tracks per project are kept,
along with their originals. Music changes retain script approval and require a new
export. No third-party music is downloaded or included in the source package.

Sage Workspace interface: browse/search saved projects, create a project in the
source dialog, then use Passage, Narration, Scenes, Audio and Export tabs. The
portrait preview stays beside the editor on desktop and stacks below it on phones.
Unsaved changes are shown and protected when switching projects. The interface uses
only local CSS and JavaScript; no frontend build tools or external fonts are required.


Cinematic images: in Scenes, choose the verified passage or saved narration, a scene
count and optional visual direction. Confirm sending that text to AI Horde, then
Generate images. This optional community API is free; no personal key is needed.
Anonymous outputs are shared for dataset improvement. Queue time and model quality
vary. Cancel is available and each image has a 10-minute timeout. Original outputs,
cleaned JPEGs, prompts, seeds, model IDs and checksums stay in the project folder.
You can replace the active scene plan while retaining earlier files. Enable automatic
rendering only after approving the exact narration; it uses the Export tab's quality.
There is no paid fallback. See [provider research](docs/IMAGE_PROVIDERS.md).

Music defaults to 24 dB below measured narration volume, with additional speech
ducking. Older louder settings are lowered once; previous exports remain on disk.
Render again after saving audio edits to hear the new balance.
