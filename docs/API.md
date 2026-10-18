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
