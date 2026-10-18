import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import uuid
import io
import warnings
import importlib.util
from pathlib import Path
from contextlib import contextmanager

import requests
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
Image.MAX_IMAGE_PIXELS = 20_000_000
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "12")) * 1024 * 1024
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
DB = DATA / "projects.sqlite3"
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)
PIPER_DATA_DIR = ROOT / "voices"
PIPER_DATA_DIR.mkdir(exist_ok=True)

app = FastAPI(title="SelahFrame", version="0.1.0")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])


@app.middleware("http")
async def local_origin_guard(request, call_next):
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
            "script_version": "INTEGER NOT NULL DEFAULT 0",
            "approved_version": "INTEGER",
            "translation": "TEXT NOT NULL DEFAULT ''",
            "scripture_source": "TEXT NOT NULL DEFAULT ''",
            "source_license": "TEXT NOT NULL DEFAULT ''",
            "context_text": "TEXT NOT NULL DEFAULT ''",
            "placeholders": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if name not in columns:
                c.execute(f"ALTER TABLE projects ADD COLUMN {name} {definition}")
        c.execute("UPDATE projects SET status='failed', error='App stopped during render. Retry the approved script.' WHERE status='rendering'")
initialize()


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
    return dict(row)


def update_project(project_id, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with connection() as c:
        c.execute(f"UPDATE projects SET {cols} WHERE id=?",
                  [*fields.values(), project_id])


@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "app" / "static" / "index.html").read_text(encoding="utf8")


@app.get("/api/health")
def health():
    return {"ok": True, "mode": "local-only", "components": {
        name: bool(shutil.which(name)) for name in ("ffmpeg", "ffprobe", "ollama", "rclone")
    }, "piper": importlib.util.find_spec("piper") is not None}


@app.post("/api/projects")
def create_project(payload: NewProject):
    pid = str(uuid.uuid4())
    with connection() as c:
        c.execute(
            "INSERT INTO projects (id, reference, scripture, title, translation, scripture_source, source_license, context_text, placeholders) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, payload.reference, payload.scripture, payload.title, payload.translation,
             payload.scripture_source, payload.source_license, payload.context_text, payload.placeholders)
        )
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
Adjacent context supplied by the reviewer: {project['context_text']}
The verified scripture text is:
{project["scripture"]}
Return only narration text."""
    try:
        response = requests.post(
            os.getenv("OLLAMA_URL", "http://127.0.0.1:11434") + "/api/generate",
            json={"model": os.getenv("OLLAMA_MODEL", "gemma3:1b"),
                  "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.4, "num_predict": 300}},
            timeout=300
        )
        response.raise_for_status()
        narration = response.json()["response"].strip()
        if not narration:
            raise ValueError("AI returned empty narration")
    except (requests.RequestException, ValueError, KeyError) as exc:
        raise HTTPException(503, "Ollama unavailable or invalid response. Start Ollama or write narration manually.") from exc
    save_script(pid, EditedScript(script=narration).script)
    return load_project(pid)


@app.put("/api/projects/{pid}/script")
def edit_script(pid: str, payload: EditedScript):
    load_project(pid)
    save_script(pid, payload.script)
    return load_project(pid)


def save_script(pid, text):
    with connection() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT status FROM projects WHERE id=?", (pid,)).fetchone()
        if row[0] == "rendering":
            raise HTTPException(409, "Wait for the current render before editing")
        c.execute("UPDATE projects SET script=?, script_version=script_version+1, approved_version=NULL, status='review', error='', drive_status='' WHERE id=?", (text, pid))


@app.post("/api/projects/{pid}/approve")
def approve(pid: str, payload: Approval):
    project = load_project(pid)
    if len(project["script"].strip()) < 10:
        raise HTTPException(400, "Generate or write narration first")
    with connection() as c:
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT status FROM projects WHERE id=?", (pid,)).fetchone()[0] == "rendering":
            raise HTTPException(409, "Render in progress")
        if c.execute("SELECT script_version FROM projects WHERE id=?", (pid,)).fetchone()[0] != payload.script_version:
            raise HTTPException(409, "Script changed. Reload and review the latest version")
        c.execute("UPDATE projects SET approved_version=script_version, status='approved' WHERE id=?", (pid,))
    return load_project(pid)


@app.post("/api/projects/{pid}/images")
async def upload_image(pid: str, image: UploadFile = File(...)):
    if load_project(pid)["status"] == "rendering":
        raise HTTPException(409, "Wait for the render before adding images")
    ext = Path(image.filename or "").suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(400, "Only JPG, PNG and WebP allowed")
    data = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Maximum image size is 12 MB")
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
    return {"filename": path.name, "count": len(list(path.parent.glob("*")))}


def run(cmd, timeout=600, input_text=None):
    result = subprocess.run(cmd, capture_output=True, text=True,
                            input=input_text, encoding="utf-8", timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"{Path(cmd[0]).name} failed (exit {result.returncode}). Check installation, inputs and available disk space.")


def placeholder_images(pid, count=6):
    folder = OUTPUT / pid / "images"
    if list(folder.iterdir()):
        return
    palettes = [
        ((24, 40, 58), (203, 142, 84)), ((41, 29, 46), (184, 131, 107)),
        ((35, 45, 41), (181, 149, 100)), ((29, 40, 61), (156, 127, 88)),
        ((48, 38, 34), (192, 143, 91)), ((28, 48, 59), (190, 157, 111))
    ]
    for i in range(count):
        a, b = palettes[i % len(palettes)]
        im = Image.new("RGB", (720, 1280))
        px = im.load()
        for y in range(1280):
            f = y / 1279
            col = tuple(int(a[k] * (1 - f) + b[k] * f) for k in range(3))
            for x in range(720):
                px[x, y] = col
        draw = ImageDraw.Draw(im)
        draw.ellipse((240, 270, 480, 510), fill=(223, 181, 112))
        draw.text((40, 1120), "Replace with your licensed cinematic scene", fill="white")
        im.save(folder / f"placeholder_{i+1:02}.jpg", quality=90)


def render_worker(pid: str):
    try:
        project = load_project(pid)
        missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
        if importlib.util.find_spec("piper") is None:
            missing.append("piper-tts")
        if missing:
            update_project(pid, status="failed", error="Missing dependencies: " + ", ".join(missing) + ". See docs/INSTALL_WINDOWS.md, then retry.")
            return
        folder = OUTPUT / pid
        folder.mkdir(parents=True, exist_ok=True)
        voice = folder / "narration.wav"
        cmd = [
            sys.executable, "-m", "piper",
            "-m", os.getenv("PIPER_MODEL", "en_US-lessac-medium"),
            "--data-dir", os.getenv("PIPER_DATA_DIR", str(PIPER_DATA_DIR)),
            "-f", str(voice)
        ]
        run(cmd, timeout=300, input_text=project["script"])
        if not voice.exists():
            raise RuntimeError("Piper did not produce narration.wav")
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(voice)],
            capture_output=True, text=True, check=True, timeout=30
        )
        duration = float(probe.stdout.strip())
        if duration <= 0:
            raise RuntimeError("Invalid narration duration")
        if project["placeholders"]:
            placeholder_images(pid)
        imgs = sorted((folder / "images").glob("*"))
        imgs = [p for p in imgs if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
        if not imgs:
            raise RuntimeError("No usable images found")
        # Each image has equal duration; duration comes from generated voiceover.
        seconds_per_image = duration / len(imgs)
        clips = []
        for idx, img in enumerate(imgs):
            clip = folder / f"clip_{idx:02}.mp4"
            run(["ffmpeg", "-y", "-loop", "1", "-framerate", "25",
                 "-i", str(img), "-t", f"{seconds_per_image:.4f}",
                 "-vf", "scale=720:1280:force_original_aspect_ratio=increase,"
                        "crop=720:1280,format=yuv420p",
                 "-c:v", "libx264", "-preset", "ultrafast",
                 "-crf", "25", "-r", "25", str(clip)], timeout=600)
            clips.append(clip)
        concat = folder / "concat.txt"
        concat.write_text(
            "".join("file '{}'\n".format(str(c).replace("\\", "/").replace("'", "'\\''"))
                    for c in clips), encoding="utf8"
        )
        video = folder / "final.mp4"
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(concat), "-i", str(voice),
             "-map", "0:v:0", "-map", "1:a:0",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
             "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", "-shortest", str(video)], timeout=900)
        (folder / "script.txt").write_text(project["script"], encoding="utf8")
        (folder / "export.json").write_text(json.dumps({
            "script_version": project["approved_version"],
            "narration": project["script"], "scripture": project["scripture"],
            "translation": project["translation"], "source": project["scripture_source"],
            "license": project["source_license"], "disclosure": "AI-generated voice narration",
            "placeholder_pack_selected": bool(project["placeholders"]),
        }, indent=2), encoding="utf8")
        update_project(pid, status="complete")
    except Exception as exc:
        update_project(pid, status="failed", error=f"Render failed ({type(exc).__name__}). Run scripts/doctor-windows.ps1, check voice model and images, then retry.")


@app.post("/api/projects/{pid}/render")
def render(pid: str):
    project = load_project(pid)
    with connection() as c:
        c.execute("BEGIN IMMEDIATE")
        project = dict(c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone())
        if project["status"] == "rendering":
            return {"status": "rendering", "id": pid}
        if project["approved_version"] != project["script_version"] or not project["approved_version"]:
            raise HTTPException(409, "Approve the current script before rendering")
        if c.execute("SELECT 1 FROM projects WHERE status='rendering'").fetchone():
            raise HTTPException(409, "Another project is rendering. Try again when it finishes.")
        if not project["placeholders"] and not any((OUTPUT / pid / "images").glob("*.jpg")):
            raise HTTPException(409, "Upload licensed images or create a project with the labeled placeholder pack")
        c.execute("UPDATE projects SET status='rendering', error='' WHERE id=?", (pid,))
    threading.Thread(target=render_worker, args=(pid,), daemon=True).start()
    return {"status": "rendering", "id": pid}


@app.get("/api/projects/{pid}/download")
def download(pid: str):
    if load_project(pid)["status"] != "complete":
        raise HTTPException(409, "Render the approved version first")
    path = OUTPUT / pid / "final.mp4"
    if not path.exists():
        raise HTTPException(404, "Video is not ready")
    return FileResponse(path, filename=f"bible-{pid}.mp4", media_type="video/mp4")


@app.get("/api/projects/{pid}/preview")
def preview(pid: str):
    if load_project(pid)["status"] != "complete":
        raise HTTPException(409, "Render the approved version first")
    path = OUTPUT / pid / "final.mp4"
    if not path.is_file():
        raise HTTPException(404, "Video is not ready")
    return FileResponse(path, media_type="video/mp4")


@app.post("/api/projects/{pid}/upload-drive")
def upload_drive(pid: str):
    if load_project(pid)["status"] != "complete":
        raise HTTPException(409, "Render the approved version first")
    folder = OUTPUT / pid
    if not (folder / "final.mp4").exists():
        raise HTTPException(409, "Render video before uploading")
    remote = os.getenv("RCLONE_REMOTE", "bibledrive")
    dest = "Bible-AI-Studio/Projects"
    if not re.fullmatch(r"[A-Za-z0-9_-]+", remote):
        raise HTTPException(400, "Invalid rclone remote name")
    try:
        run(["rclone", "copy", str(folder),
             f"{remote}:{dest}/{pid}", "--exclude", "clip_*.mp4",
             "--exclude", "concat.txt", "--progress"], timeout=900)
        run(["rclone", "check", str(folder), f"{remote}:{dest}/{pid}",
             "--one-way", "--size-only", "--exclude", "clip_*.mp4",
             "--exclude", "concat.txt"], timeout=900)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        update_project(pid, drive_status="failed")
        raise HTTPException(503, "Drive upload or verification failed. Check rclone configuration and retry; local files were retained.") from exc
    update_project(pid, drive_status="verified-size")
    return {"status": "verified-size", "path": f"{dest}/{pid}"}
