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
