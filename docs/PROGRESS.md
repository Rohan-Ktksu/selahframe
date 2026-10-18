# Optional music milestone — 2026-10-19

Active checkout: D:\SelahFrame. The user controls GitHub pushes.

- Added optional local music imports, preview, track selection, saved volume and
  enable/disable controls. Imported tracks start OFF; narration-only remains default.
- Required source/license and explicit permission confirmation. WAV/MP3/FLAC imports
  have request, byte, duration, channel, sample-rate, count and scratch/disk bounds.
  Format-forced FFmpeg decoding disables network protocols and strips metadata.
- Added persistent music-import jobs sharing the global render/Drive lock. Edits are
  blocked during import. Failure, worker-start failure and restart restore prior
  project state/settings. Originals, earlier exports and failed staging are retained.
- Schema version 4 adds soundtrack settings/revisions and original/normalized music
  receipts. Music edits keep exact narration approval; previews, downloads, cached
  renders and Drive admission require the current soundtrack revision.
- Renderer loops/trims the normalized track to measured narration, fades the ends,
  ducks beneath speech and limits peaks without auto-gain. Export folders contain
  narration.wav, music.wav, mixed.wav and checksum/source/license receipts. Disabled
  exports record music=null and retain their original narration-only audio path.
- Dashboard folds import fields after a track exists. Unsaved narration, scene or
  music edits cannot be archived through the UI without being saved/rendered first.

Executed evidence:

- 51 API/media regression tests passed (8.292 seconds in the feature run), including
  stale settings, foreign assets, no-op saves, competing jobs, failures, restart,
  original retention and changed-on-disk music rejection. TestClient still emits its
  known httpx deprecation warning; it does not fail the suite.
- Actual WAV, MP3 and FLAC fixtures each decoded to 2,000ms; malformed audio failed.
- Deterministic audio calibration: background 20.60dB lower during the speech signal,
  voice amplitude preserved at 0.4000, peak -7.80dBFS, duration exactly 8.000 seconds.
- Live API regression rendered both narration-only and enabled-music 720p exports.
  Music export: 13.36 seconds, 8.75 seconds render time, decoded AAC peak -1.31dBFS.
  HTTP 206 audio ranges, new export ID after enabling, retained baseline, complete
  media checksums and unchanged-export cache reuse all passed.
- Browser tested music toggle/volume/save/reload and preview playback (4s track).
  Browser-triggered 1080x1920 export: 13.24 seconds, H.264/AAC, saved -20dB music,
  soundtrack revision 4, all asset checksums verified, no absolute paths in receipt.
- Ruff lint/format, Python compileall and dashboard JavaScript syntax passed.
- Screenshot: ignored temp/music-editor.png. Demo project:
  1a8665d3-601a-4be3-af63-4817f2859607. Generated test music is an original sine chord;
  no external music was downloaded or bundled. No new runtime dependency was added.

Repeat on Windows with the server running:

```powershell
cd D:\SelahFrame
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe scripts\smoke-music.py --render
```

A subjective listening review is still a user action. Captions remain approximate.
Ollama drafting and real Google Drive OAuth/transfers are not yet integration-tested;
these prior limitations still apply. Structured scene/draft generation, forced word
alignment, cancellation, reviewed cleanup and clean-machine release acceptance remain
pending. Next milestone: structured local draft/scene planning, or user-authorized
Drive setup. No automated cleanup, public publishing or GitHub push was performed.

---

# Scene editor milestone — 2026-10-18

Active checkout: D:\SelahFrame. All changes remain local for the user's GitHub push.

- Added scene thumbnails, ordering, include/exclude, time weights and camera motion.
- Normalized scenes table with stable IDs, repeatable backfill and schema version 3.
- Optimistic revision checks prevent stale saves. Project ownership, active job locks,
  at least one included scene and bounded finite weights are enforced by the API.
- Scene changes retain the exact narration approval and require a new render. No-op
  saves preserve the preview. Excluded images and earlier exports are retained.
- Renderer now obeys saved order/weights/motion and exports a precise scene timeline.
  Each scene receives frames while the sum follows the measured narration duration.
- 39 API/media tests passed (5.672 seconds in the feature run). Ruff and JavaScript
  syntax passed. Existing approval, persistence, job and upload tests remain green.
- Browser tested changing weight, zoom-out, excluding a scene, moving a scene, saving
  and rendering. Reloaded browser showed the persisted settings and live estimates.
- Real browser-triggered 1080p render: 61.56s, five included scenes. Scene lengths
  10.280/20.480/10.280/10.280/10.213s verified, including the saved zoom-out choice.
- Real uploaded-image render: blue then red, 8.400s and 4.185s, completed in 7.45s.
  Decoded frames confirmed their actual color/order; green was excluded and all three
  original images remained. Sources/licenses matched the reordered exported images.
- Repeatable live test: python scripts/smoke-scenes.py (server running).
- Browser screenshot: ignored temp/scene-editor.png. No generated media enters Git.

Next: licensed optional music/ducking or real Drive OAuth/setup. Ollama, music and
Drive integration limitations from the previous checkpoint still apply. Caption
alignment remains approximate, and narration listening review is a user action.

---

# Local video milestone — 2026-10-18

Active development checkout: D:\SelahFrame. The user controls GitHub pushes.

## Delivered

- Installed Piper 1.8.0, a reviewed LJ Speech medium voice and SHA-256-verified
  portable FFmpeg 9.0.2 under the project folder; no paid service or system PATH edit.
- Real CPU 720p and 1080p exports, centered camera movement, readable burned ASS
  captions plus SRT, measured narration duration, H.264/yuv420p/AAC and faststart.
- Immutable exports with exact approved script/image revisions, media checksums,
  source/license manifests and persisted voice/subtitle/video asset records.
- SQLite scripts/jobs/assets/exports tables, versioned API, stage progress,
  duplicate-request reuse, single-job admission and interrupted-job recovery.
- Single-server file lock; imports no longer mutate the database. Drafts cannot
  overwrite newer manual edits. Project edits are blocked during render/Drive jobs.
- Image source/license intake, decoded re-encoding, request/pixel/count limits.
- Background Drive copy/size-check jobs with locks and retained originals.
- Repeatable setup/doctor scripts, offline tests, lint/format CI and current docs.

## Executed evidence

- 27 offline API/media tests passed (3.383 seconds in the final run).
- Real 1080p trial: 1080x1920, 60.36 seconds, 25.23 seconds wall time. H.264,
  yuv420p, AAC and HTTP 206 range playback verified; sample frame visually checked.
- Final 720p trial: 720x1280, 19.28 seconds, 8.09 seconds wall time. Captions visually
  checked; audio mean -18.4 dB and peak -1.4 dB after disabling limiter auto-gain.
- The first frame review exposed oversized three-line captions; fixed by generating
  ASS with an explicit portrait canvas. The original full-range pixel format was
  corrected to limited-range yuv420p and gated by ffprobe.
- Doctor reports all four local media prerequisites ready. Dashboard JavaScript
  syntax checked using Node. A listening review of the voice remains a user action.
- Final live HTTP render: 60.52 seconds at 1080p completed in 24.33 seconds; audio mean -18.9 dB, peak -1.0 dB.
- Live restart recovery, HTTP 206/1024-byte video reads and a rejected second server were verified.
- Renderer/voice fingerprints prevent reuse of exports made before a pipeline change.
- Ruff lint/format, compileall, PowerShell parsing and dashboard JavaScript syntax passed.
- Known development warning: Starlette's TestClient warns that httpx is deprecated;
  requests still pass. No extra test transport dependency has been introduced.

## Remaining

Ollama and rclone are not installed; manual narration is the supported tested path.
Real Ollama generation and Google OAuth/upload have not been tested. Drive requires
user browser authorization. No account login or public content publishing is implied.

Editable scene durations/order, optional licensed music/ducking, word alignment,
structured scene/draft generation, per-scene regeneration, cancellation and a reviewed
archive/cleanup UX remain pending. No original media or scratch is automatically deleted.

The definition of done is not yet fully closed: voice listening review, actual Drive
transfer and a clean-machine guided setup still need to be exercised. The completed
local video pipeline is available for user review now.

---

# Previous checkpoint history

# Implementation checkpoint — 2026-10-18

Source: the supplied Astra master plan and nested bible-ai-studio-mvp.zip.
The workspace initially contained only .git. The original handoff is retained in
ignored .handoff/; its instructions are project guidance, not account authorization.

## Implemented and tested

- Reused FastAPI, SQLite, the existing dashboard and media subprocess pipeline.
- Required passage translation/source/license/context metadata; opt-in placeholders.
- Script revision numbers, exact-version approval, approval revocation on editing.
- Atomic single-render admission and duplicate-request reuse, restart recovery.
- Windows SQLite connection closure, WAL and busy timeout.
- Bounded image reads, decoded format/pixel checks and safe JPEG re-encoding.
- Piper narration supplied on stdin; bounded ffprobe invocation; generic CLI errors.
- Drive destination Bible-AI-Studio/Projects/<uuid>, copy followed by size verification.
- Saved-project list/reopen, preview route/player, export AI-voice disclosure.
- Local host/origin checks, expanded ignore rules, diagnostics and setup guidance.

## Validation

Initial test attempt could not access sandbox temporary directories. An approved
outside-sandbox test run revealed SQLite handles remaining open on Windows.
Fixed with an explicit closing context manager. The first 10 regression tests passed.
Final suite: all 12 tests passed, including cross-origin writes and actionable missing
dependencies (1.286 seconds). TestClient emitted an httpx deprecation warning;
this did not fail the tests. Python compileall passed. Doctor correctly reported
missing media tools/model. Uvicorn started successfully with approved localhost access.

## Remaining; no full-MVP claim

P0 remains open until a real Piper + FFmpeg Windows export is probed and watched.
Missing on PATH: ffmpeg, ffprobe, Ollama and rclone; Piper and its voice are not installed.
Ollama generation, Piper synthesis, video playback and real Drive OAuth/upload are
not integration-tested. No Google/GitHub authorization was requested or performed.

P1 partial: project/script/approval/image workflow works in API tests. Full normalized
scripts/assets/jobs/exports tables, image provenance per asset, durable job IDs,
versioned API, bounded disk enforcement and per-stage progress remain unfinished.
P2: captions, motion, 1080p, licensed music and scene editor remain unimplemented.
P3 partial: synchronous copy + size check exists; durable upload jobs remain pending.
P4 automation and P5 release acceptance remain pending. Run one application process;
do not use multiple workers. Do not mutate a project during a Drive upload until
upload job locking is implemented. No media cleanup is performed.

Next testable milestone: install/review media dependencies, render a short reviewed
manual narration with explicitly selected placeholders, ffprobe and watch the result,
then build captions and durable export/job records before expanding automation.

## Workspace relocation — 2026-10-18

Active development folder: D:\SelahFrame. Git history, local data and source copied
with 92 matching file hashes. Recreated .venv on D: and all 12 regression tests passed
there (1.368 seconds). Original C: copy is retained as a backup.
