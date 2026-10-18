import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import uuid
import warnings
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Literal

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from PIL import Image, ImageOps
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import media

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
Image.MAX_IMAGE_PIXELS = 20_000_000
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "12")) * 1024 * 1024
MAX_MUSIC_BYTES = int(os.getenv("MAX_MUSIC_MB", "25")) * 1024 * 1024
BUSY_STATUSES = {"rendering", "uploading", "importing_music"}
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
DB = DATA / "projects.sqlite3"
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)
PIPER_DATA_DIR = ROOT / "voices"
PIPER_DATA_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(application):
    # Only one process may own jobs in this checkout. Importing this module has no DB side effects.
    handle = (DATA / "server.lock").open("a+b")
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError(
            "SelahFrame is already running from this folder. Use the existing server."
        )
    try:
        initialize()
        yield
    finally:
        handle.close()


app = FastAPI(title="SelahFrame", version="0.4.0", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])


@app.middleware("http")
async def local_origin_guard(request, call_next):
    if request.method == "POST" and request.url.path.endswith(("/images", "/music/tracks")):
        is_music = request.url.path.endswith("/music/tracks")
        cap = MAX_MUSIC_BYTES if is_music else MAX_UPLOAD_BYTES
        length = request.headers.get("content-length", "")
        if not length.isdecimal():
            return JSONResponse({"detail": "An upload requires Content-Length"}, status_code=411)
        if int(length) > cap + 1024 * 1024:
            return JSONResponse(
                {"detail": "Upload exceeds the request size limit"},
                status_code=413,
            )
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and origin not in {"http://127.0.0.1:8000", "http://localhost:8000"}:
            return JSONResponse({"detail": "Cross-origin changes are not allowed"}, status_code=403)
    return await call_next(request)


@contextmanager
def connection():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("PRAGMA foreign_keys=ON")
    try:
        with c:
            yield c
    finally:
        c.close()


def initialize():
    with connection() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, reference TEXT NOT NULL, scripture TEXT NOT NULL,
            title TEXT NOT NULL, script TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            error TEXT NOT NULL DEFAULT '',
            drive_status TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        columns = {r[1] for r in c.execute("PRAGMA table_info(projects)")}
        for name, definition in {
            "image_revision": "INTEGER NOT NULL DEFAULT 0",
            "script_version": "INTEGER NOT NULL DEFAULT 0",
            "approved_version": "INTEGER",
            "translation": "TEXT NOT NULL DEFAULT ''",
            "scripture_source": "TEXT NOT NULL DEFAULT ''",
            "source_license": "TEXT NOT NULL DEFAULT ''",
            "context_text": "TEXT NOT NULL DEFAULT ''",
            "placeholders": "INTEGER NOT NULL DEFAULT 0",
            "music_asset_id": "TEXT",
            "music_enabled": "INTEGER NOT NULL DEFAULT 0",
            "music_gain_db": "REAL NOT NULL DEFAULT -18",
            "music_revision": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if name not in columns:
                c.execute(f"ALTER TABLE projects ADD COLUMN {name} {definition}")
        c.executescript("""
            CREATE TABLE IF NOT EXISTS scripts (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                version INTEGER NOT NULL, narration_text TEXT NOT NULL, approved_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(project_id, version));
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                stage TEXT NOT NULL, status TEXT NOT NULL, progress INTEGER DEFAULT 0,
                attempts INTEGER DEFAULT 1, error TEXT DEFAULT '', snapshot_json TEXT NOT NULL,
                started_at TEXT DEFAULT CURRENT_TIMESTAMP, finished_at TEXT);
            CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs(status, started_at);
            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                type TEXT NOT NULL, local_path TEXT NOT NULL, source_url TEXT NOT NULL,
                license_name TEXT NOT NULL, checksum TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS exports (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                job_id TEXT NOT NULL REFERENCES jobs(id), script_version INTEGER NOT NULL,
                image_revision INTEGER NOT NULL, quality TEXT NOT NULL, file_path TEXT NOT NULL,
                width INTEGER NOT NULL, height INTEGER NOT NULL, duration_ms INTEGER NOT NULL,
                checksum TEXT NOT NULL, drive_status TEXT DEFAULT '', drive_path TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE INDEX IF NOT EXISTS exports_project_idx ON exports(project_id, created_at);
        """)
        export_columns = {r[1] for r in c.execute("PRAGMA table_info(exports)")}
        if "pipeline_signature" not in export_columns:
            c.execute("ALTER TABLE exports ADD COLUMN pipeline_signature TEXT NOT NULL DEFAULT ''")
        if "music_revision" not in export_columns:
            c.execute("ALTER TABLE exports ADD COLUMN music_revision INTEGER NOT NULL DEFAULT 0")
        c.executescript("""
            CREATE TABLE IF NOT EXISTS music_tracks (
                asset_id TEXT PRIMARY KEY REFERENCES assets(id),
                original_path TEXT NOT NULL, original_checksum TEXT NOT NULL,
                uploaded_name TEXT NOT NULL, duration_ms INTEGER NOT NULL,
                rights_confirmed INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS scenes (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                idx INTEGER NOT NULL, image_asset_id TEXT REFERENCES assets(id),
                placeholder_index INTEGER, duration_weight REAL NOT NULL DEFAULT 1,
                motion_style TEXT NOT NULL DEFAULT 'zoom_in', enabled INTEGER NOT NULL DEFAULT 1,
                UNIQUE(project_id, idx));
            CREATE INDEX IF NOT EXISTS scenes_project_idx ON scenes(project_id, idx);
        """)
        for row in c.execute("SELECT id, placeholders FROM projects").fetchall():
            ensure_scenes(c, row["id"], bool(row["placeholders"]))
        c.execute("PRAGMA user_version=4")
        for row in c.execute(
            "SELECT project_id, snapshot_json FROM jobs WHERE status IN ('queued', 'running')"
        ).fetchall():
            previous = json.loads(row["snapshot_json"]).get("previous_status", "approved")
            c.execute(
                "UPDATE projects SET status=?, error='Music import interrupted. Retry the upload.' WHERE id=? AND status='importing_music'",
                (previous, row["project_id"]),
            )
        c.execute("UPDATE projects SET script_version=1 WHERE script_version=0 AND script<>''")
        c.execute(
            "INSERT OR IGNORE INTO scripts (id, project_id, version, narration_text, approved_at) SELECT id, id, script_version, script, CASE WHEN approved_version=script_version THEN CURRENT_TIMESTAMP ELSE NULL END FROM projects WHERE script<>''"
        )
        c.execute(
            "UPDATE jobs SET status='failed', error='App stopped during this job. Retry explicitly.', finished_at=CURRENT_TIMESTAMP WHERE status IN ('queued', 'running')"
        )
        c.execute(
            "UPDATE projects SET status='complete', drive_status='failed' WHERE status='uploading'"
        )
        c.execute(
            "UPDATE projects SET status='failed', error='App stopped during render. Retry the approved script.' WHERE status='rendering'"
        )


def ensure_scenes(c, pid, placeholders):
    if c.execute("SELECT 1 FROM scenes WHERE project_id=?", (pid,)).fetchone():
        return
    images = c.execute(
        "SELECT id FROM assets WHERE project_id=? AND type='image' ORDER BY rowid", (pid,)
    ).fetchall()
    if images:
        rows = [
            (str(uuid.uuid4()), pid, idx, image["id"], None) for idx, image in enumerate(images)
        ]
    elif placeholders:
        rows = [(str(uuid.uuid4()), pid, idx, None, idx) for idx in range(6)]
    else:
        rows = []
    c.executemany(
        "INSERT INTO scenes (id, project_id, idx, image_asset_id, placeholder_index) VALUES (?, ?, ?, ?, ?)",
        rows,
    )


def scene_rows(c, pid):
    return [
        dict(row)
        for row in c.execute(
            "SELECT s.*, a.local_path, a.source_url, a.license_name, a.checksum FROM scenes s LEFT JOIN assets a ON a.id=s.image_asset_id WHERE s.project_id=? ORDER BY s.idx",
            (pid,),
        )
    ]


def mark_visual_edit(c, pid):
    c.execute(
        "UPDATE projects SET image_revision=image_revision+1, status=CASE WHEN approved_version=script_version THEN 'approved' ELSE 'review' END, drive_status='', error='' WHERE id=?",
        (pid,),
    )


class SceneEdit(BaseModel):
    model_config = {"extra": "forbid"}
    id: str = Field(min_length=1, max_length=36)
    enabled: bool = True
    duration_weight: float = Field(ge=0.25, le=10, allow_inf_nan=False)
    motion_style: Literal["zoom_in", "zoom_out", "still"] = "zoom_in"


class ScenePlan(BaseModel):
    model_config = {"extra": "forbid"}
    image_revision: int = Field(ge=0)
    scenes: list[SceneEdit] = Field(min_length=1, max_length=24)


class MusicSettings(BaseModel):
    model_config = {"extra": "forbid"}
    music_revision: int = Field(ge=0)
    asset_id: str | None = Field(default=None, min_length=1, max_length=36)
    enabled: bool = False
    gain_db: float = Field(default=-18, ge=-30, le=-6, allow_inf_nan=False)


class NewProject(BaseModel):
    reference: str = Field(min_length=3, max_length=120)
    scripture: str = Field(min_length=1, max_length=10000)
    title: str = Field(min_length=1, max_length=120)
    translation: str = Field(min_length=1, max_length=120)
    scripture_source: str = Field(min_length=1, max_length=1000)
    source_license: str = Field(min_length=1, max_length=500)
    context_text: str = Field(min_length=1, max_length=10000)
    placeholders: bool = False


class EditedScript(BaseModel):
    script: str = Field(min_length=10, max_length=10000)


class RenderSettings(BaseModel):
    quality: Literal["720p", "1080p"] = "720p"


class Approval(BaseModel):
    script_version: int = Field(ge=1)


def load_project(project_id):
    try:
        if str(uuid.UUID(project_id)) != project_id:
            raise ValueError()
    except ValueError:
        raise HTTPException(404, "Project not found")
    with connection() as c:
        row = c.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Project not found")
    project = dict(row)
    with connection() as c:
        job = c.execute(
            "SELECT id, stage, status, progress, error FROM jobs WHERE project_id=? ORDER BY rowid DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        project["job"] = dict(job) if job else None
        project["image_count"] = c.execute(
            "SELECT COUNT(*) FROM assets WHERE project_id=? AND type='image'",
            (project_id,),
        ).fetchone()[0]
    return project


def update_project(project_id, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with connection() as c:
        c.execute(f"UPDATE projects SET {cols} WHERE id=?", [*fields.values(), project_id])


@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "app" / "static" / "index.html").read_text(encoding="utf8")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "mode": "local-only",
        "components": {
            **media.readiness(),
            "ollama": bool(shutil.which("ollama")),
            "rclone": bool(shutil.which("rclone")),
        },
        "caption_timing": "approximate",
        "max_concurrent_jobs": 1,
        "max_music_mb": MAX_MUSIC_BYTES // (1024 * 1024),
    }


@app.post("/api/projects")
def create_project(payload: NewProject):
    pid = str(uuid.uuid4())
    with connection() as c:
        c.execute(
            "INSERT INTO projects (id, reference, scripture, title, translation, scripture_source, source_license, context_text, placeholders) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                pid,
                payload.reference,
                payload.scripture,
                payload.title,
                payload.translation,
                payload.scripture_source,
                payload.source_license,
                payload.context_text,
                payload.placeholders,
            ),
        )
        ensure_scenes(c, pid, payload.placeholders)
    (OUTPUT / pid / "images").mkdir(parents=True, exist_ok=True)
    return load_project(pid)


@app.get("/api/projects")
def projects():
    with connection() as c:
        rows = c.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    return load_project(pid)


@app.post("/api/projects/{pid}/generate-script")
def generate_script(pid: str):
    project = load_project(pid)
    prompt = f"""You are a thoughtful Christian Bible storytelling writer.
Use ONLY the supplied verified Bible passage as a direct scripture quotation.
Do not invent quotes or claim uncertain historical details as certain.
Write ~110-135 spoken words suitable for ~60 seconds.
Start with a relatable modern-life hook, explain the meaning in its context,
give one everyday analogy and conclude with a gentle encouragement.
Use clear conversational English and no markdown, no scene directions.
The passage reference is {project["reference"]}.
Adjacent context supplied by the reviewer: {project["context_text"]}
The verified scripture text is:
{project["scripture"]}
Return only narration text."""
    try:
        response = requests.post(
            os.getenv("OLLAMA_URL", "http://127.0.0.1:11434") + "/api/generate",
            json={
                "model": os.getenv("OLLAMA_MODEL", "gemma3:1b"),
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.4, "num_predict": 300},
            },
            timeout=300,
        )
        response.raise_for_status()
        raw = response.json()["response"]
        if not isinstance(raw, str):
            raise ValueError("Invalid narration type")
        narration = EditedScript(script=raw.strip()).script
        if not narration:
            raise ValueError("AI returned empty narration")
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            503,
            "Ollama unavailable or invalid response. Start Ollama or write narration manually.",
        ) from exc
    save_script(pid, narration, expected_version=project["script_version"])
    return load_project(pid)


@app.put("/api/projects/{pid}/script")
def edit_script(pid: str, payload: EditedScript):
    load_project(pid)
    save_script(pid, payload.script)
    return load_project(pid)


def save_script(pid, text, expected_version=None):
    with connection() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT status, script_version FROM projects WHERE id=?", (pid,)).fetchone()
        if expected_version is not None and row["script_version"] != expected_version:
            raise HTTPException(
                409,
                "The script changed while drafting. Review your saved edits before generating again.",
            )
        if row[0] in BUSY_STATUSES:
            raise HTTPException(409, "Wait for the active job before editing")
        c.execute(
            "UPDATE projects SET script=?, script_version=script_version+1, approved_version=NULL, status='review', error='', drive_status='' WHERE id=?",
            (text, pid),
        )
        c.execute(
            "INSERT INTO scripts (id, project_id, version, narration_text) SELECT ?, id, script_version, script FROM projects WHERE id=?",
            (str(uuid.uuid4()), pid),
        )


@app.post("/api/projects/{pid}/approve")
def approve(pid: str, payload: Approval):
    project = load_project(pid)
    if len(project["script"].strip()) < 10:
        raise HTTPException(400, "Generate or write narration first")
    with connection() as c:
        c.execute("BEGIN IMMEDIATE")
        if (
            c.execute("SELECT status FROM projects WHERE id=?", (pid,)).fetchone()[0]
            in BUSY_STATUSES
        ):
            raise HTTPException(409, "Render in progress")
        if (
            c.execute("SELECT script_version FROM projects WHERE id=?", (pid,)).fetchone()[0]
            != payload.script_version
        ):
            raise HTTPException(409, "Script changed. Reload and review the latest version")
        c.execute(
            "UPDATE projects SET approved_version=script_version, status='approved' WHERE id=?",
            (pid,),
        )
        c.execute(
            "UPDATE scripts SET approved_at=CURRENT_TIMESTAMP WHERE project_id=? AND version=?",
            (pid, payload.script_version),
        )
    return load_project(pid)


@app.post("/api/projects/{pid}/images")
async def upload_image(
    pid: str,
    image: UploadFile = File(...),
    source_url: str = Form(..., min_length=1, max_length=1000),
    license_name: str = Form(..., min_length=1, max_length=500),
):
    if load_project(pid)["status"] in BUSY_STATUSES:
        raise HTTPException(409, "Wait for the render before adding images")
    ext = Path(image.filename or "").suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(400, "Only JPG, PNG and WebP allowed")
    data = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Maximum image size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    path = OUTPUT / pid / "images" / (str(uuid.uuid4()) + ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as img:
                if img.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Unsupported image")
                img.load()
                # Re-encode to remove trailing payloads and metadata.
                path = path.with_suffix(".jpg")
                img.convert("RGB").save(path, "JPEG", quality=92)
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(400, "Invalid image file") from exc
    with connection() as c:
        c.execute("BEGIN IMMEDIATE")
        state = c.execute("SELECT status FROM projects WHERE id=?", (pid,)).fetchone()[0]
        count = c.execute(
            "SELECT COUNT(*) FROM assets WHERE project_id=? AND type='image'", (pid,)
        ).fetchone()[0]
        if state in BUSY_STATUSES or count >= 24:
            path.unlink(missing_ok=True)
            raise HTTPException(409, "Project is busy or has reached the 24-image limit")
        asset_id = str(uuid.uuid4())
        c.execute(
            "INSERT INTO assets (id, project_id, type, local_path, source_url, license_name, checksum) VALUES (?, ?, 'image', ?, ?, ?, ?)",
            (
                asset_id,
                pid,
                str(path),
                source_url,
                license_name,
                media.digest(path),
            ),
        )
        # The first photo replaces the generated pack; original files/exports are retained.
        if not c.execute(
            "SELECT 1 FROM scenes WHERE project_id=? AND image_asset_id IS NOT NULL", (pid,)
        ).fetchone():
            c.execute("DELETE FROM scenes WHERE project_id=?", (pid,))
        idx = c.execute(
            "SELECT COALESCE(MAX(idx), -1)+1 FROM scenes WHERE project_id=?", (pid,)
        ).fetchone()[0]
        c.execute(
            "INSERT INTO scenes (id, project_id, idx, image_asset_id) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), pid, idx, asset_id),
        )
        mark_visual_edit(c, pid)
    return {"filename": path.name, "count": count + 1, "asset_id": asset_id}


@app.get("/api/projects/{pid}/scenes")
def get_scenes(pid: str):
    project = load_project(pid)
    with connection() as c:
        rows = scene_rows(c, pid)
        previous = c.execute(
            "SELECT duration_ms FROM exports WHERE project_id=? ORDER BY rowid DESC LIMIT 1", (pid,)
        ).fetchone()
    duration = previous[0] if previous else None
    total = sum(row["duration_weight"] for row in rows if row["enabled"])
    scenes = []
    for row in rows:
        share = row["duration_weight"] / total if row["enabled"] and total else 0
        scenes.append(
            {
                "id": row["id"],
                "image_asset_id": row["image_asset_id"],
                "enabled": bool(row["enabled"]),
                "duration_weight": row["duration_weight"],
                "motion_style": row["motion_style"],
                "placeholder": row["image_asset_id"] is None,
                "share": share,
                "estimated_seconds": round(duration * share / 1000, 2) if duration else None,
                "source_url": row["source_url"] or "SelahFrame abstract placeholder pack",
                "license_name": row["license_name"] or "Project-generated geometric illustration",
                "thumbnail_url": f"/api/v1/projects/{pid}/scenes/{row['id']}/thumbnail",
            }
        )
    return {
        "image_revision": project["image_revision"],
        "narration_duration_ms": duration,
        "scenes": scenes,
    }


@app.put("/api/projects/{pid}/scenes")
def save_scenes(pid: str, payload: ScenePlan):
    load_project(pid)
    with connection() as c:
        c.execute("BEGIN IMMEDIATE")
        project = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if project["status"] in BUSY_STATUSES:
            raise HTTPException(409, "Wait for the active job before editing scenes")
        if payload.image_revision != project["image_revision"]:
            raise HTTPException(
                409, "The scene plan changed. Reload the saved scenes and try again."
            )
        rows = scene_rows(c, pid)
        ids = [item.id for item in payload.scenes]
        if len(ids) != len(set(ids)) or set(ids) != {row["id"] for row in rows}:
            raise HTTPException(
                422, "Include every scene exactly once; images must belong to this project"
            )
        if not any(item.enabled for item in payload.scenes):
            raise HTTPException(422, "Keep at least one scene included in the video")
        current = [
            (r["id"], bool(r["enabled"]), r["duration_weight"], r["motion_style"]) for r in rows
        ]
        revised = [(r.id, r.enabled, r.duration_weight, r.motion_style) for r in payload.scenes]
        if current != revised:
            # Temporarily use negative positions to avoid UNIQUE collisions during reorder.
            c.execute("UPDATE scenes SET idx=-(idx+1) WHERE project_id=?", (pid,))
            for idx, item in enumerate(payload.scenes):
                c.execute(
                    "UPDATE scenes SET idx=?, enabled=?, duration_weight=?, motion_style=? WHERE project_id=? AND id=?",
                    (idx, item.enabled, item.duration_weight, item.motion_style, pid, item.id),
                )
            mark_visual_edit(c, pid)
    return get_scenes(pid)


_thumbnail_lock = threading.Lock()


@app.get("/api/projects/{pid}/scenes/{scene_id}/thumbnail")
def scene_thumbnail(pid: str, scene_id: str):
    load_project(pid)
    with connection() as c:
        row = c.execute(
            "SELECT s.*, a.local_path, a.checksum FROM scenes s LEFT JOIN assets a ON a.id=s.image_asset_id WHERE s.project_id=? AND s.id=?",
            (pid, scene_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Scene not found")
    folder = OUTPUT / pid
    with _thumbnail_lock:
        if row["image_asset_id"]:
            original = Path(row["local_path"]).resolve()
            try:
                original.relative_to((folder / "images").resolve())
            except ValueError:
                raise HTTPException(404, "Invalid image path")
            key = row["checksum"]
        else:
            if row["placeholder_index"] not in range(6):
                raise HTTPException(404, "Invalid placeholder")
            pack_folder = folder / "placeholders"
            original = pack_folder / f"placeholder_{row['placeholder_index'] + 1:02}.jpg"
            if not original.is_file():
                media.placeholder_pack(pack_folder)
            key = "placeholder-v1-" + str(row["placeholder_index"])
        thumbnail = folder / "thumbnails" / (key + ".jpg")
        if not thumbnail.is_file():
            thumbnail.parent.mkdir(exist_ok=True)
            try:
                with Image.open(original) as image:
                    image = ImageOps.fit(image.convert("RGB"), (180, 320))
                    temporary = thumbnail.with_suffix(".tmp")
                    image.save(temporary, "JPEG", quality=85)
                    temporary.replace(thumbnail)
            except (OSError, ValueError):
                raise HTTPException(404, "Image is missing or unreadable. Upload it again.")
    return FileResponse(thumbnail, media_type="image/jpeg")


def run(cmd, timeout=600, input_text=None):
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        input=input_text,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"{Path(cmd[0]).name} failed (exit {result.returncode}). Check installation, inputs and available disk space."
        )


def music_rows(c, pid):
    return [
        dict(row)
        for row in c.execute(
            "SELECT a.*, t.uploaded_name, t.duration_ms, t.original_checksum FROM assets a JOIN music_tracks t ON t.asset_id=a.id WHERE a.project_id=? AND a.type='music' ORDER BY a.rowid",
            (pid,),
        )
    ]


def music_path(pid, row):
    path = Path(row["local_path"]).resolve()
    try:
        path.relative_to((OUTPUT / pid / "music").resolve())
    except ValueError:
        raise media.MediaError("Invalid music asset path. Import the track again.")
    if not path.is_file():
        raise media.MediaError("The music file is missing. Restore it or import another track.")
    return path


@app.get("/api/projects/{pid}/music")
def get_music(pid: str):
    project = load_project(pid)
    with connection() as c:
        tracks = music_rows(c, pid)
    return {
        "music_revision": project["music_revision"],
        "asset_id": project["music_asset_id"],
        "enabled": bool(project["music_enabled"]),
        "gain_db": project["music_gain_db"],
        "tracks": [
            {
                "id": row["id"],
                "name": row["uploaded_name"],
                "duration_ms": row["duration_ms"],
                "source_url": row["source_url"],
                "license_name": row["license_name"],
                "preview_url": f"/api/projects/{pid}/music/tracks/{row['id']}/preview",
            }
            for row in tracks
        ],
    }


@app.put("/api/projects/{pid}/music")
def save_music(pid: str, payload: MusicSettings):
    load_project(pid)
    with connection() as c:
        c.execute("BEGIN IMMEDIATE")
        project = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if project["status"] in BUSY_STATUSES:
            raise HTTPException(409, "Wait for the active job before changing music")
        if payload.music_revision != project["music_revision"]:
            raise HTTPException(409, "Music settings changed. Reload them and retry.")
        tracks = music_rows(c, pid)
        if payload.asset_id and not any(row["id"] == payload.asset_id for row in tracks):
            raise HTTPException(400, "Select a music track from this project")
        if payload.enabled and not payload.asset_id:
            raise HTTPException(400, "Import and select a track before enabling music")
        if (
            project["music_asset_id"],
            bool(project["music_enabled"]),
            project["music_gain_db"],
        ) != (payload.asset_id, payload.enabled, payload.gain_db):
            c.execute(
                "UPDATE projects SET music_asset_id=?, music_enabled=?, music_gain_db=?, music_revision=music_revision+1, status=CASE WHEN approved_version=script_version THEN 'approved' ELSE 'review' END, error='', drive_status='' WHERE id=?",
                (payload.asset_id, int(payload.enabled), payload.gain_db, pid),
            )
    return get_music(pid)


@app.get("/api/projects/{pid}/music/tracks/{asset_id}/preview")
def preview_music(pid: str, asset_id: str):
    load_project(pid)
    with connection() as c:
        row = next((row for row in music_rows(c, pid) if row["id"] == asset_id), None)
    if not row:
        raise HTTPException(404, "Music track not found")
    try:
        path = music_path(pid, row)
    except media.MediaError as exc:
        raise HTTPException(404, str(exc))
    return FileResponse(path, media_type="audio/wav")


def fail_music_import(pid, job_id, previous_status, error):
    with connection() as c:
        c.execute(
            "UPDATE jobs SET status='failed', error=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
            (error, job_id),
        )
        c.execute(
            "UPDATE projects SET status=?, error=? WHERE id=? AND status='importing_music'",
            (previous_status, error, pid),
        )


def music_import_worker(pid, job_id, source, snapshot):
    try:
        normalized = source.parent / "normalized.wav"
        budget = media.disk_guard(
            OUTPUT.parent / "temp", reserve=40 * 1024**2, extra_folder=source.parent.parent
        )
        duration_ms = media.normalize_music(source, normalized, budget)
        media.disk_guard(OUTPUT.parent / "temp", extra_folder=source.parent.parent)
        asset_id = str(uuid.uuid4())
        with connection() as c:
            c.execute(
                "INSERT INTO assets (id, project_id, type, local_path, source_url, license_name, checksum) VALUES (?, ?, 'music', ?, ?, ?, ?)",
                (
                    asset_id,
                    pid,
                    str(normalized),
                    snapshot["source_url"],
                    snapshot["license_name"],
                    media.digest(normalized),
                ),
            )
            c.execute(
                "INSERT INTO music_tracks (asset_id, original_path, original_checksum, uploaded_name, duration_ms) VALUES (?, ?, ?, ?, ?)",
                (
                    asset_id,
                    str(source),
                    media.digest(source),
                    snapshot["uploaded_name"],
                    duration_ms,
                ),
            )
            # Importing never enables an unpreviewed track or revokes narration approval.
            c.execute(
                "UPDATE projects SET music_asset_id=?, music_enabled=0, music_revision=music_revision+1, status=CASE WHEN approved_version=script_version THEN 'approved' ELSE 'review' END, error='', drive_status='' WHERE id=?",
                (asset_id, pid),
            )
            c.execute(
                "UPDATE jobs SET status='complete', stage='complete', progress=100, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (job_id,),
            )
    except Exception as exc:
        message = (
            str(exc)
            if isinstance(exc, media.MediaError)
            else "Music import failed. Choose a valid WAV, MP3 or FLAC file and retry."
        )
        fail_music_import(pid, job_id, snapshot["previous_status"], message)


@app.post("/api/projects/{pid}/music/tracks", status_code=202)
async def import_music(
    pid: str,
    track: UploadFile = File(...),
    source_url: str = Form(..., min_length=1, max_length=1000),
    license_name: str = Form(..., min_length=1, max_length=500),
    rights_confirmed: bool = Form(False),
):
    load_project(pid)
    if not rights_confirmed or not source_url.strip() or not license_name.strip():
        raise HTTPException(
            400, "Record the source/license and confirm permission to use this music"
        )
    suffix = Path(track.filename or "").suffix.lower()
    if suffix not in media.MUSIC_FORMATS:
        raise HTTPException(400, "Choose a WAV, MP3 or FLAC file")
    if not media.executable("ffmpeg") or not media.executable("ffprobe"):
        raise HTTPException(503, "Install local FFmpeg tools before importing music")
    data = await track.read(MAX_MUSIC_BYTES + 1)
    if not data or len(data) > MAX_MUSIC_BYTES:
        raise HTTPException(
            413, f"Choose a nonempty file up to {MAX_MUSIC_BYTES // (1024 * 1024)} MB"
        )
    with connection() as c:
        c.execute("BEGIN IMMEDIATE")
        project = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if (
            project["status"] in BUSY_STATUSES
            or c.execute("SELECT 1 FROM jobs WHERE status IN ('queued', 'running')").fetchone()
        ):
            raise HTTPException(409, "Another job is active. Wait for it to finish.")
        if len(music_rows(c, pid)) >= 3:
            raise HTTPException(
                409, "This project already has three music tracks; choose one of them"
            )
        job_id = str(uuid.uuid4())
        snapshot = {
            "previous_status": project["status"],
            "source_url": source_url.strip(),
            "license_name": license_name.strip(),
            "uploaded_name": Path(track.filename).name[:160],
        }
        c.execute(
            "INSERT INTO jobs (id, project_id, stage, status, snapshot_json) VALUES (?, ?, 'music-import', 'running', ?)",
            (job_id, pid, json.dumps(snapshot)),
        )
        c.execute("UPDATE projects SET status='importing_music', error='' WHERE id=?", (pid,))
    try:
        folder = OUTPUT / pid / "music" / job_id
        media.disk_guard(
            OUTPUT.parent / "temp", reserve=len(data) + 40 * 1024**2, extra_folder=folder.parent
        )
        folder.mkdir(parents=True)
        source = folder / ("original" + suffix)
        source.write_bytes(data)
        start_worker(music_import_worker, (pid, job_id, source, snapshot))
    except (OSError, RuntimeError) as exc:
        message = (
            str(exc)
            if isinstance(exc, media.MediaError)
            else "Cannot start music import. Check disk space and restart the app."
        )
        fail_music_import(pid, job_id, snapshot["previous_status"], message)
        raise HTTPException(503, message)
    return {"id": pid, "job_id": job_id, "status": "running"}


def start_worker(target, args):
    threading.Thread(target=target, args=args, daemon=True).start()


def progress_job(job_id, stage, progress):
    with connection() as c:
        c.execute(
            "UPDATE jobs SET stage=?, progress=? WHERE id=? AND status='running'",
            (stage, progress, job_id),
        )


def render_worker(pid: str, job_id: str):
    try:
        with connection() as c:
            job = c.execute("SELECT snapshot_json FROM jobs WHERE id=?", (job_id,)).fetchone()
        snapshot = json.loads(job[0])
        folder = OUTPUT / pid / "exports" / job_id
        image_paths = [Path(item["local_path"]) for item in snapshot["images"]]
        for path in image_paths:
            path.resolve().relative_to((OUTPUT / pid / "images").resolve())
            if not path.is_file():
                raise media.MediaError(
                    "A selected image is missing. Restore it or upload another image."
                )
        if snapshot.get("music"):
            path = music_path(pid, snapshot["music"])
            if media.digest(path) != snapshot["music"]["checksum"]:
                raise media.MediaError(
                    "The selected music changed on disk. Import it again before rendering."
                )
        info = media.render(
            snapshot,
            image_paths,
            folder,
            ROOT / "temp" / job_id,
            lambda stage, pct: progress_job(job_id, stage, pct),
        )
        provenance = []
        for idx, path in enumerate(sorted((folder / "images").glob("*.jpg"))):
            source = (
                snapshot["scenes"][idx]
                if snapshot["scenes"][idx]["image_asset_id"]
                else {
                    "source_url": "SelahFrame abstract placeholder pack",
                    "license_name": "Project-generated geometric illustration; no third-party image",
                }
            )
            provenance.append(
                {
                    "file": "images/" + path.name,
                    "source_url": source["source_url"],
                    "license_name": source["license_name"],
                    "checksum": media.digest(path),
                }
            )
        export_manifest = {
            **snapshot,
            **info,
            "images": provenance,
            "music": (
                {
                    key: snapshot["music"][key]
                    for key in (
                        "id",
                        "uploaded_name",
                        "source_url",
                        "license_name",
                        "checksum",
                        "original_checksum",
                        "duration_ms",
                    )
                }
                | {
                    "file": "music.wav",
                    "mix_file": "mixed.wav",
                    "gain_db": snapshot["music_gain_db"],
                    "ducking": "voice sidechain, threshold 0.025, ratio 8, attack 15ms, release 350ms",
                }
            )
            if snapshot.get("music")
            else None,
            "disclosure": "AI-generated voice narration",
            "voice_source": media.VOICE_SOURCE
            if info["voice"].startswith("en_US-ljspeech-")
            else os.getenv("PIPER_SOURCE", "User-configured voice"),
            "voice_license": "MIT model repository; public-domain LJ Speech dataset"
            if info["voice"].startswith("en_US-ljspeech-")
            else os.getenv("PIPER_LICENSE", "User must verify"),
            "placeholder_pack_used": any(
                not scene["image_asset_id"] for scene in snapshot["scenes"]
            ),
            "file_path": "final.mp4",
            "scenes": [
                {
                    key: scene[key]
                    for key in (
                        "id",
                        "image_asset_id",
                        "placeholder_index",
                        "duration_weight",
                        "motion_style",
                    )
                }
                for scene in snapshot["scenes"]
            ],
        }
        generated_assets = [
            (
                "voice",
                folder / "narration.wav",
                export_manifest["voice_source"],
                export_manifest["voice_license"],
            ),
            (
                "subtitle",
                folder / "captions.srt",
                "Approved narration; approximate timing",
                "Project-generated captions",
            ),
            (
                "subtitle",
                folder / "captions.ass",
                "Approved narration; approximate timing",
                "Project-generated captions",
            ),
            (
                "video",
                folder / "final.mp4",
                "Local Piper/FFmpeg render",
                "Uses the licenses listed in this manifest",
            ),
        ]
        if snapshot.get("music"):
            generated_assets.extend(
                [
                    (
                        "music-export",
                        folder / "music.wav",
                        snapshot["music"]["source_url"],
                        snapshot["music"]["license_name"],
                    ),
                    (
                        "audio-mix",
                        folder / "mixed.wav",
                        "Local narration and licensed music mix",
                        "Uses the voice and music licenses listed in this manifest",
                    ),
                ]
            )
        export_manifest["asset_checksums"] = {
            path.name: media.digest(path) for _, path, _, _ in generated_assets
        }
        (folder / "export.json").write_text(json.dumps(export_manifest, indent=2), encoding="utf-8")
        with connection() as c:
            for kind, path, source, license_name in generated_assets:
                c.execute(
                    "INSERT INTO assets (id, project_id, type, local_path, source_url, license_name, checksum) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(uuid.uuid4()),
                        pid,
                        kind,
                        str(path),
                        source,
                        license_name,
                        media.digest(path),
                    ),
                )
            c.execute(
                "INSERT INTO exports (id, project_id, job_id, script_version, image_revision, quality, file_path, width, height, duration_ms, checksum, pipeline_signature, music_revision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    pid,
                    job_id,
                    snapshot["approved_version"],
                    snapshot["image_revision"],
                    snapshot["quality"],
                    info["file_path"],
                    info["width"],
                    info["height"],
                    info["duration_ms"],
                    info["sha256"],
                    snapshot["pipeline_signature"],
                    snapshot["music_revision"],
                ),
            )
            c.execute(
                "UPDATE jobs SET status='complete', stage='complete', progress=100, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (job_id,),
            )
            c.execute(
                "UPDATE projects SET status='complete', error='', drive_status='' WHERE id=?",
                (pid,),
            )
    except Exception as exc:
        message = (
            str(exc)
            if isinstance(exc, media.MediaError)
            else "Render failed. Check your voice model, image files and available disk space, then retry."
        )
        with connection() as c:
            c.execute(
                "UPDATE jobs SET status='failed', error=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (message, job_id),
            )
            c.execute(
                "UPDATE projects SET status='failed', error=? WHERE id=?",
                (message, pid),
            )


@app.post("/api/projects/{pid}/render", status_code=202)
def render(pid: str, payload: RenderSettings | None = None):
    load_project(pid)
    quality = (payload or RenderSettings()).quality
    pipeline_signature = media.pipeline_signature()
    with connection() as c:
        c.execute("BEGIN IMMEDIATE")
        project = dict(c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone())
        active = c.execute("SELECT * FROM jobs WHERE status IN ('queued', 'running')").fetchone()
        if active:
            if (
                active["project_id"] == pid
                and active["stage"] != "drive"
                and json.loads(active["snapshot_json"]).get("quality") == quality
            ):
                return {"status": active["status"], "id": pid, "job_id": active["id"]}
            raise HTTPException(409, "Another job is active. Wait for it to finish and retry.")
        if (
            project["approved_version"] != project["script_version"]
            or not project["approved_version"]
        ):
            raise HTTPException(409, "Approve the current script before rendering")
        previous = c.execute(
            "SELECT * FROM exports WHERE project_id=? AND script_version=? AND image_revision=? AND quality=? AND pipeline_signature=? AND music_revision=? ORDER BY rowid DESC LIMIT 1",
            (
                pid,
                project["script_version"],
                project["image_revision"],
                quality,
                pipeline_signature,
                project["music_revision"],
            ),
        ).fetchone()
        if previous and Path(previous["file_path"]).is_file():
            c.execute("UPDATE projects SET status='complete', error='' WHERE id=?", (pid,))
            return {"status": "complete", "id": pid, "job_id": previous["job_id"]}
        project["scenes"] = [row for row in scene_rows(c, pid) if row["enabled"]]
        project["images"] = [
            {
                key: row[key]
                for key in (
                    "image_asset_id",
                    "local_path",
                    "source_url",
                    "license_name",
                    "checksum",
                )
            }
            for row in project["scenes"]
            if row["image_asset_id"]
        ]
        if not project["scenes"]:
            raise HTTPException(
                409, "Upload images or choose placeholders; keep at least one scene included"
            )
        project["music"] = None
        if project["music_enabled"]:
            project["music"] = next(
                (row for row in music_rows(c, pid) if row["id"] == project["music_asset_id"]), None
            )
            if not project["music"]:
                raise HTTPException(
                    409, "The selected music is missing. Import or disable it before rendering."
                )
        project["quality"] = quality
        project["pipeline_signature"] = pipeline_signature
        job_id = str(uuid.uuid4())
        c.execute(
            "INSERT INTO jobs (id, project_id, stage, status, snapshot_json) VALUES (?, ?, 'preflight', 'running', ?)",
            (job_id, pid, json.dumps(project)),
        )
        c.execute("UPDATE projects SET status='rendering', error='' WHERE id=?", (pid,))
    try:
        start_worker(render_worker, (pid, job_id))
    except RuntimeError:
        with connection() as c:
            c.execute(
                "UPDATE jobs SET status='failed', error='Cannot start worker. Restart app.', finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (job_id,),
            )
            c.execute(
                "UPDATE projects SET status='failed', error='Cannot start worker. Restart app.' WHERE id=?",
                (pid,),
            )
        raise HTTPException(503, "Cannot start worker. Restart app.")
    return {"status": "running", "id": pid, "job_id": job_id}


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str):
    with connection() as c:
        job = c.execute(
            "SELECT id, project_id, stage, status, progress, attempts, error, started_at, finished_at FROM jobs WHERE id=?",
            (job_id,),
        ).fetchone()
    if not job:
        raise HTTPException(404, "Job not found")
    return dict(job)


@app.get("/api/projects/{pid}/scripts")
def script_history(pid: str):
    load_project(pid)
    with connection() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT version, narration_text, approved_at, created_at FROM scripts WHERE project_id=? ORDER BY version DESC",
                (pid,),
            )
        ]


@app.get("/api/projects/{pid}/exports")
def export_history(pid: str):
    load_project(pid)
    with connection() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT id, script_version, quality, width, height, duration_ms, drive_status, created_at FROM exports WHERE project_id=? ORDER BY rowid DESC",
                (pid,),
            )
        ]


def current_export(pid):
    project = load_project(pid)
    if (
        project["status"] not in {"complete", "uploading"}
        or project["approved_version"] != project["script_version"]
    ):
        raise HTTPException(409, "Render the approved version first")
    with connection() as c:
        row = c.execute(
            "SELECT * FROM exports WHERE project_id=? AND script_version=? AND image_revision=? AND music_revision=? ORDER BY rowid DESC LIMIT 1",
            (
                pid,
                project["approved_version"],
                project["image_revision"],
                project["music_revision"],
            ),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Video is not ready")
    export = dict(row)
    path = Path(export["file_path"]).resolve()
    try:
        path.relative_to((OUTPUT / pid).resolve())
    except ValueError:
        raise HTTPException(409, "Invalid export path")
    if not path.is_file():
        raise HTTPException(404, "Export file is missing. Retry rendering.")
    return export


@app.get("/api/projects/{pid}/download")
def download(pid: str):
    export = current_export(pid)
    return FileResponse(
        export["file_path"], filename=f"selahframe-{pid}.mp4", media_type="video/mp4"
    )


@app.get("/api/projects/{pid}/preview")
def preview(pid: str):
    return FileResponse(current_export(pid)["file_path"], media_type="video/mp4")


def drive_worker(pid, job_id, export):
    folder = Path(export["file_path"]).parent
    remote = os.getenv("RCLONE_REMOTE", "bibledrive")
    dest = f"{remote}:Bible-AI-Studio/Projects/{pid}"
    try:
        run(["rclone", "copy", str(folder), dest, "--retries", "2"], timeout=900)
        progress_job(job_id, "drive-verify", 75)
        run(
            ["rclone", "check", str(folder), dest, "--one-way", "--size-only"],
            timeout=900,
        )
        with connection() as c:
            c.execute(
                "UPDATE exports SET drive_status='verified-size', drive_path=? WHERE id=?",
                (dest, export["id"]),
            )
            c.execute(
                "UPDATE projects SET status='complete', drive_status='verified-size', error='' WHERE id=?",
                (pid,),
            )
            c.execute(
                "UPDATE jobs SET status='complete', stage='complete', progress=100, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (job_id,),
            )
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        error = "Drive upload or verification failed. Check rclone and authorize bibledrive, then retry. All local files were retained."
        with connection() as c:
            c.execute("UPDATE exports SET drive_status='failed' WHERE id=?", (export["id"],))
            c.execute(
                "UPDATE projects SET status='complete', drive_status='failed', error=? WHERE id=?",
                (error, pid),
            )
            c.execute(
                "UPDATE jobs SET status='failed', error=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (error, job_id),
            )


@app.post("/api/projects/{pid}/upload-drive", status_code=202)
def upload_drive(pid: str):
    export = current_export(pid)
    remote = os.getenv("RCLONE_REMOTE", "bibledrive")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", remote):
        raise HTTPException(400, "Invalid rclone remote name")
    with connection() as c:
        c.execute("BEGIN IMMEDIATE")
        active = c.execute("SELECT * FROM jobs WHERE status IN ('queued', 'running')").fetchone()
        if active:
            if active["project_id"] == pid and active["stage"].startswith("drive"):
                return {"job_id": active["id"], "status": active["status"]}
            raise HTTPException(409, "Another job is active")
        # Recheck after acquiring the mutation lock.
        current = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if (
            current["approved_version"] != export["script_version"]
            or current["image_revision"] != export["image_revision"]
            or current["music_revision"] != export["music_revision"]
        ):
            raise HTTPException(409, "Project changed. Render the current version first.")
        job_id = str(uuid.uuid4())
        c.execute(
            "INSERT INTO jobs (id, project_id, stage, status, snapshot_json) VALUES (?, ?, 'drive', 'running', ?)",
            (job_id, pid, json.dumps({"export_id": export["id"]})),
        )
        c.execute(
            "UPDATE projects SET status='uploading', drive_status='uploading', error='' WHERE id=?",
            (pid,),
        )
    try:
        start_worker(drive_worker, (pid, job_id, export))
    except RuntimeError:
        with connection() as c:
            c.execute(
                "UPDATE jobs SET status='failed', error='Cannot start worker. Restart app.', finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (job_id,),
            )
            c.execute(
                "UPDATE projects SET status='complete', drive_status='failed', error='Cannot start worker. Restart app.' WHERE id=?",
                (pid,),
            )
        raise HTTPException(503, "Cannot start worker. Restart app.")
    return {"job_id": job_id, "status": "running"}


@app.get("/api/projects/{pid}/drive")
def drive_status(pid: str):
    project = load_project(pid)
    with connection() as c:
        export = c.execute(
            "SELECT drive_path, drive_status FROM exports WHERE project_id=? ORDER BY rowid DESC LIMIT 1",
            (pid,),
        ).fetchone()
    return {
        "status": project["drive_status"],
        "export": dict(export) if export else None,
    }


# Versioned API, with legacy dashboard routes retained during migration.
for route in list(app.routes):
    path = getattr(route, "path", "")
    if path.startswith("/api/projects"):
        new_path = path.replace("/api/projects", "/api/v1/projects", 1)
        new_path = (
            new_path.replace("/generate-script", "/script:generate")
            .replace("/approve", "/script:approve")
            .replace("/upload-drive", "/drive:upload")
        )
        app.add_api_route(
            new_path,
            route.endpoint,
            methods=list(route.methods),
            status_code=route.status_code,
        )
