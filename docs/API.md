# API

Base URL: http://127.0.0.1:8000. GET /api/health reports local component readiness.
The /api/projects compatibility routes remain available alongside /api/v1/projects.

| Method | Route after /api/v1 | Behavior |
|---|---|---|
| GET/POST | /projects | List or create projects |
| GET | /projects/{id} | Metadata, latest job and uploaded-image count |
| POST | /projects/{id}/script:generate | Optional Ollama draft; manual fallback on errors |
| PUT | /projects/{id}/script | Save a new narration version; revoke approval |
| POST | /projects/{id}/script:approve | Approve exact script_version |
| GET | /projects/{id}/scripts | Script and approval history |
| POST | /projects/{id}/images | Multipart image, source_url, license_name |
| GET/PUT | /projects/{id}/scenes | Read/save the ordered scene plan |
| GET | /projects/{id}/scenes/{scene_id}/thumbnail | Ownership-checked 180x320 JPEG preview |
| GET/PUT | /projects/{id}/music | Read/save optional soundtrack settings |
| POST | /projects/{id}/music/tracks | Bounded multipart import; 202 with persistent job_id |
| GET | /projects/{id}/music/tracks/{asset_id}/preview | Ownership-checked WAV with range support |
| POST | /projects/{id}/render | 202 with job_id; body quality=720p or 1080p |
| GET | /jobs/{id} | Stage, status, progress, safe error and timestamps |
| GET | /projects/{id}/exports | Export dimensions, duration and version history |
| GET | /projects/{id}/preview | MP4 with byte-range support |
| GET | /projects/{id}/download | MP4 attachment |
| POST | /projects/{id}/drive:upload | 202 with persistent Drive job_id |
| GET | /projects/{id}/drive | Latest transfer result |

Project creation requires title, reference, scripture, translation, scripture_source,
source_license and context_text. placeholders defaults to false. Approval requires
{"script_version": 1}. A script payload is {"script": "Reviewed narration..."}.

Concurrent duplicate render requests for the same project/quality return the active
job; completed exports are reused when script version, image revision, music revision and quality
match along with the renderer/voice fingerprint. Conflicting jobs return 409. A different script or new image invalidates the
current preview. Rendering and uploads capture immutable versions rather than reading
changing project state. Jobs persist but do not automatically resume after a restart.
Errors return JSON detail; raw subprocess stderr and tokens are not returned.
Image requests require Content-Length and are checked before multipart parsing.

## Scene plan

PUT scenes accepts image_revision plus the complete ordered scenes list. Every item
contains id, enabled, duration_weight (0.25-10) and motion_style (zoom_in, zoom_out or
still). Include every current scene exactly once, with at least one enabled. The
revision prevents stale saves after another client or upload changes the plan.
Unknown scenes, duplicate IDs, invalid values or excluding every scene are rejected.
Scene assets cannot be reassigned through this endpoint; images must belong to the
owning project. An active render or upload blocks changes. A no-op save keeps the
revision and existing preview. A changed plan increments image_revision, retains
script approval, invalidates the current preview and becomes part of the next job's
immutable snapshot. GET returns display metadata and estimated seconds based on
last rendered narration. Each export manifest records actual scene start/end times.

## Optional music

GET music returns music_revision, asset_id, enabled (false by default), gain_db and
track display metadata/preview URLs. PUT accepts those four settings, requires the
current revision and a project-owned asset_id when enabled, and allows gain_db from
-40 to -12 (default -24), measured below narration RMS before additional speech ducking. Stale edits return 409; no-op saves preserve the revision.
Changed settings retain script approval and invalidate the current export. Preview,
download, cache reuse and Drive admission all check the saved music revision.

POST music/tracks takes multipart track, source_url, license_name and
rights_confirmed=true. It accepts WAV/MP3/FLAC, a configurable MAX_MUSIC_MB (25 default),
1–300 seconds, mono/stereo at 8–192 kHz, with a three-track project limit. Content-Length
is required and checked before multipart parsing. Local FFmpeg decodes a forced
format with network protocols disabled and strips metadata. Preview WAVs are
normalized to -18 LUFS / -6 dBTP target, stereo 32 kHz. Originals and both checksums
are retained. Imports are persistent jobs sharing the single global worker slot;
project edits are locked until completion/failure. Successful import selects the new
track with music OFF. Failed or interrupted imports retain the previous settings;
no automatic retry or file deletion occurs.

Each enabled-music export contains music.wav, mixed.wav and source/license/checksum
receipts in export.json. The voice controls a sidechain compressor; music loops and
fades while narration duration remains authoritative. Narration and final mix are
retained separately. These fields record permission supplied by the user; they do
not independently verify license claims or fulfill attribution obligations.


## Cinematic images (AI Horde, optional)

`POST /api/v1/projects/{id}/cinematic` starts a persisted background job. Body:
`source` (verse/narration), `count` (1–4), `direction` (up to 500 chars),
`image_revision`, `script_version`, `consent` (must be true), `replace_plan`
(default false), `render_after` (default false), `quality` (720p/1080p).
The source text is loaded from this project's saved passage/narration. Optimistic
versions and the global job lock prevent edits/renders from overlapping generation.
Automatic rendering requires an already-approved current narration; no script is
created, altered or automatically approved by this endpoint.

`POST /api/v1/projects/{id}/cinematic/cancel` cancels this project's running image
job and restores its prior state. The worker discards late results and requests
remote cancellation. Network operations have their own bounded timeout.

The provider is AI Horde only, with anonymous credentials unless the optional
server-side AI_HORDE_API_KEY is set. No paid fallback exists. Anonymous outputs
are shared for dataset improvement under the provider's rules. Prompts go to
volunteer workers. The explicit consent checkbox covers the selected source and
direction; do not send private material.

Jobs retain prompts and remote IDs. Original returned image bytes, sanitized JPEGs,
checksums, model/seed IDs and provenance.json are saved under the project images
folder. All scenes attach atomically only when the requested batch succeeds;
failure/cancellation retains the previous plan and earlier exports. Replacing a
plan retains original files and the earlier plan in the job snapshot. Restart fails
interrupted jobs explicitly; it never silently resubmits to the remote provider.
The provider may still finish an in-flight request if the app is forcibly stopped.

Drafts use the stable_diffusion model, 512x768 and 20 steps, with provider downgrade
allowed for free admission. Images are cropped to 9:16 by the existing renderer.
Each scene has a 10-minute queue/generation timeout, with explicit cancellation and
no automatic retry. Queue estimates are provider-wide estimates, not a guarantee.
