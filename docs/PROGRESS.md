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
