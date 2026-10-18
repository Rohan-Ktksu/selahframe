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
job; completed exports are reused when script version, image revision and quality
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
