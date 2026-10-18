# SelahFrame — Windows implementation checkpoint

Local FastAPI/SQLite app for verified Bible passages and human-reviewed narration.
This is a partial implementation of the supplied Astra plan, not a completed video MVP.

The repaired workflow includes passage provenance fields, exact-version approval,
project reopening, bounded image uploads, one active render, export disclosure and
Drive size verification. API behavior is covered by offline regression tests.

Start the existing development environment:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-windows.ps1
```

Open http://127.0.0.1:8000. See [Windows setup](docs/INSTALL_WINDOWS.md),
[current progress and missing features](docs/PROGRESS.md) and [decisions](docs/DECISIONS.md).

Real voice/video export requires FFmpeg, ffprobe, Piper and a reviewed voice model.
They are not installed or end-to-end tested in this checkpoint. Captions, motion,
1080p output and durable queued jobs remain pending. Manual narration works without
Ollama. Drive is optional and requires the user's OAuth authorization.

Run one server process on localhost only. No paid services or cloud rendering.
Project data is stored beside the app. Use a folder with appropriate privacy and backup settings.

Do not commit .env, project data, images, audio, video, voice weights or OAuth files.
The included MIT license covers project code, not third-party tools/models/assets.
