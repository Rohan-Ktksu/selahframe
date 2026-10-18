# Architecture

Browser -> FastAPI on 127.0.0.1:8000 -> SQLite WAL -> approved script snapshot ->
Piper WAV -> measured duration -> image clips with zoom/pan -> captioned H.264/AAC
MP4 -> ffprobe validation -> immutable export -> optional rclone copy and size check.

app/main.py owns API validation, migrations, script history, assets, jobs and exports.
app/media.py owns portable tool discovery, CPU rendering, captions and media checks.
Scripts and assets have provenance; each render records the exact approved version.

SQLite immediate transactions serialize job admission. A per-checkout file lock
permits one server process, and one render/upload may be active globally. A duplicate
request returns the existing job. Startup marks interrupted work failed for explicit
retry. There is no Redis, Celery, cloud GPU or automatic paid fallback.

Generated filenames and relative concat/caption paths avoid Windows path escaping.
Each job has its own scratch and export directories. Paths read from SQLite are
checked under the owning project. Image mutations are rejected while a job is active.
Uploaded images are decoded and re-encoded before entering the media pipeline.

Caption cues use word-count-weighted estimates, with an explicit portrait ASS canvas
for burn-in. SRT is retained for editing. This is not forced or word alignment.

Remaining work: editable scene records/durations, music licensing/mixing, structured
model drafts, retry leases/cancellation, thumbnails, backup/verified-cleanup UX,
and real OAuth integration validation. Public hosting requires a separate security
and authentication design.
