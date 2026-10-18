"""CPU media pipeline. No network downloads occur while rendering."""

import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
VOICE_NAME = "en_US-ljspeech-medium"
VOICE_SOURCE = "https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/ljspeech/medium"


class MediaError(RuntimeError):
    pass


def executable(name):
    configured = os.getenv(name.upper() + "_PATH")
    if configured:
        candidate = Path(configured)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        if candidate.is_file():
            return str(candidate.resolve())
        return None
    found = shutil.which(name)
    if found:
        return found
    # Support portable tools under this project without changing system PATH.
    matches = sorted((ROOT / "tools" / "ffmpeg").glob(f"**/bin/{name}.exe"))
    return str(matches[0]) if matches else None


def pipeline_signature():
    model = voice_model()
    model_stat = (model.stat().st_size, model.stat().st_mtime_ns) if model.is_file() else None
    payload = {"pipeline": digest(Path(__file__)), "voice": str(model), "voice_stat": model_stat}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def voice_model():
    name = os.getenv("PIPER_MODEL", VOICE_NAME)
    folder = Path(os.getenv("PIPER_DATA_DIR", "voices"))
    if not folder.is_absolute():
        folder = ROOT / folder
    path = Path(name)
    if not path.is_absolute():
        path = folder / name
    if path.suffix != ".onnx":
        path = path.with_suffix(".onnx")
    return path.resolve()


def readiness():
    return {
        "ffmpeg": bool(executable("ffmpeg")),
        "ffprobe": bool(executable("ffprobe")),
        "piper": importlib.util.find_spec("piper") is not None,
        "voice_model": voice_model().is_file() and Path(str(voice_model()) + ".json").is_file(),
    }


def run(args, *, cwd=None, input_text=None, timeout=900):
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError("Media tool timed out. Try a shorter script or 720p draft.") from exc
    except OSError as exc:
        raise MediaError("Cannot start a media tool. Run scripts/doctor-windows.ps1.") from exc
    if result.returncode:
        # Never return raw stderr: it may contain private narration or local paths.
        raise MediaError(
            f"{Path(args[0]).stem} failed (exit {result.returncode}). Check the voice model, FFmpeg filters and available disk space."
        )
    return result.stdout


def probe(path):
    return json.loads(
        run(
            [
                executable("ffprobe"),
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            timeout=30,
        )
    )


def folder_bytes(folder):
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) if folder.exists() else 0


def disk_guard(scratch_root, *, reserve=0, extra_folder=None):
    cap = int(float(os.getenv("MAX_RENDER_DISK_GB", "2")) * 1024**3)
    used = folder_bytes(scratch_root) + (folder_bytes(extra_folder) if extra_folder else 0)
    if cap <= 0 or used + reserve > cap:
        raise MediaError(
            "Render scratch budget exceeded. Archive and remove old scratch folders, or increase MAX_RENDER_DISK_GB."
        )
    if shutil.disk_usage(scratch_root.parent).free < reserve + 256 * 1024**2:
        raise MediaError("Insufficient free disk space. Free space on the project drive and retry.")
    return cap - used


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def placeholder_pack(folder, count=6):
    folder.mkdir(parents=True, exist_ok=True)
    colors = [
        (25, 45, 65),
        (52, 35, 60),
        (30, 55, 45),
        (53, 40, 32),
        (28, 40, 66),
        (40, 50, 55),
    ]
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf"
    font = (
        ImageFont.truetype(str(font_path), 27)
        if font_path.is_file()
        else ImageFont.load_default(size=27)
    )
    for idx, base in enumerate(colors[:count]):
        image = Image.new("RGB", (720, 1280))
        draw = ImageDraw.Draw(image)
        for y in range(1280):
            color = tuple(min(255, round(c + 95 * y / 1280)) for c in base)
            draw.line((0, y, 720, y), fill=color)
        draw.ellipse((245, 270, 475, 500), fill=(220, 180, 115))
        draw.text((360, 600), "ABSTRACT PLACEHOLDER", font=font, anchor="mm", fill="white")
        image.save(folder / f"placeholder_{idx + 1:02}.jpg", quality=90)
    return sorted(folder.glob("*.jpg"))


def captions(text, duration):
    """Word-count-weighted timing; deliberately not represented as forced alignment."""
    words = text.split()
    # Short cues plus explicit wrapping keep the display within two 32-character lines.
    groups, group = [], []
    for word in words:
        if len(word) > 32:
            raise MediaError(
                "A narration word exceeds 32 characters. Shorten it for readable captions."
            )
        trial = " ".join(group + [word])
        if group and (len(group) >= 7 or len(textwrap.wrap(trial, 32, break_long_words=False)) > 2):
            groups.append(group)
            group = []
        group.append(word)
    if group:
        groups.append(group)
    total = sum(len(g) for g in groups)
    cues, elapsed = [], 0
    for group in groups:
        start = round(duration * 1000 * elapsed / total)
        elapsed += len(group)
        end = round(duration * 1000 * elapsed / total)
        cues.append(
            (
                start,
                end,
                "\n".join(textwrap.wrap(" ".join(group), 32, break_long_words=False)),
            )
        )
    return cues


def timestamp(ms):
    seconds, millis = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def write_srt(path, text, duration):
    cues = captions(text, duration)
    path.write_text(
        "\n\n".join(
            f"{idx}\n{timestamp(a)} --> {timestamp(b)}\n{body}"
            for idx, (a, b, body) in enumerate(cues, 1)
        )
        + "\n",
        encoding="utf-8",
    )
    return cues


def write_ass(path, text, duration, width, height):
    # Explicit portrait canvas avoids libass's default landscape SRT scaling.
    font_size = round(height * 0.028)
    margin = round(width * 0.065)
    bottom = round(height * 0.18)
    header = (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,Arial,{font_size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,{margin},{margin},{bottom},1\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    rows = []
    for start, end, body in captions(text, duration):
        safe = body.replace("\\", "＼").replace("{", "｛").replace("}", "｝").replace("\n", r"\N")
        a = timestamp(start).replace(",", ".")[:-1]
        b = timestamp(end).replace(",", ".")[:-1]
        rows.append(f"Dialogue: 0,{a},{b},Default,,0,0,0,,{safe}\n")
    path.write_text(header + "".join(rows), encoding="utf-8")


def allocate_scene_frames(total_frames, weights):
    """Keep every included scene visible and distribute all remaining frames by weight."""
    if not weights or total_frames < len(weights):
        raise MediaError("Narration is too short for the included scenes. Include fewer scenes.")
    if any(not math.isfinite(w) or w <= 0 for w in weights):
        raise MediaError("Each included scene needs a finite, positive time weight.")
    remainder = total_frames - len(weights)
    total = math.fsum(weights)
    quotas = [remainder * weight / total for weight in weights]
    counts = [1 + math.floor(quota) for quota in quotas]
    spare = total_frames - sum(counts)
    order = sorted(range(len(weights)), key=lambda idx: (-(quotas[idx] % 1), idx))
    for idx in order[:spare]:
        counts[idx] += 1
    return counts


def scene_filter(width, height, count, motion):
    denominator = max(count - 1, 1)
    zooms = {
        "zoom_in": f"1+0.06*on/{denominator}",
        "zoom_out": f"1.06-0.06*on/{denominator}",
        "still": "1",
    }
    if motion not in zooms:
        raise MediaError("Unknown scene motion. Save the scene plan again.")
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:out_range=tv,crop={width}:{height},"
        f"zoompan=z='{zooms[motion]}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':"
        f"d={count}:s={width}x{height}:fps=25,format=yuv420p,setparams=range=limited"
    )


MUSIC_FORMATS = {".wav": "wav", ".mp3": "mp3", ".flac": "flac"}


def normalize_music(source, destination, max_bytes):
    """Decode a bounded local audio file; never follow playlists or network inputs."""
    if source.suffix.lower() not in MUSIC_FORMATS:
        raise MediaError("Choose a WAV, MP3 or FLAC music file.")
    demuxer = MUSIC_FORMATS[source.suffix.lower()]
    metadata = json.loads(
        run(
            [
                executable("ffprobe"),
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-f",
                demuxer,
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(source),
            ],
            timeout=30,
        )
    )
    audio = [
        stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "audio"
    ]
    duration = float(metadata.get("format", {}).get("duration", 0))
    if (
        len(audio) != 1
        or not 1 <= duration <= 300
        or audio[0].get("channels") not in (1, 2)
        or not 8000 <= int(audio[0].get("sample_rate", 0)) <= 192000
    ):
        raise MediaError("Music must be 1–300 seconds, mono or stereo, at 8–192 kHz.")
    run(
        [
            executable("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-protocol_whitelist",
            "file,pipe",
            "-f",
            demuxer,
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-map_metadata",
            "-1",
            "-af",
            "loudnorm=I=-18:TP=-6:LRA=7",
            "-ar",
            "32000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            "-t",
            "301",
            "-fs",
            str(min(max_bytes, 40 * 1024**2)),
            str(destination),
        ],
        timeout=120,
    )
    actual = float(probe(destination)["format"]["duration"])
    if not 1 <= actual <= 300.1 or abs(actual - duration) > 0.25:
        raise MediaError(
            "Music decoding ended early or exceeds the duration limit. Try a shorter file."
        )
    return round(actual * 1000)


def music_filter(duration, gain_db, voice_channels):
    if not math.isfinite(gain_db) or not -30 <= gain_db <= -6:
        raise MediaError("Music level must be between -30 and -6 dB.")
    if not 0.2 <= duration <= 180 or voice_channels not in (1, 2):
        raise MediaError("Invalid narration audio for music mixing.")
    voice = "pan=stereo|c0=c0|c1=c0," if voice_channels == 1 else ""
    fade = min(1.0, duration / 4)
    return (
        f"[0:a]{voice}aresample=48000,asplit=2[voice][key];"
        f"[1:a]aresample=48000,atrim=duration={duration:.6f},asetpts=PTS-STARTPTS,"
        f"volume={gain_db:.3f}dB,afade=t=in:d={fade:.6f},"
        f"afade=t=out:st={duration - fade:.6f}:d={fade:.6f}[bed];"
        "[bed][key]sidechaincompress=threshold=0.025:ratio=8:attack=15:release=350[ducked];"
        "[voice][ducked]amix=inputs=2:duration=first:normalize=0,"
        "alimiter=limit=0.85:level=false:latency=true[out]"
    )


def mix_music(voice, music, destination, duration, gain_db, max_bytes):
    voice_audio = next(
        stream for stream in probe(voice)["streams"] if stream["codec_type"] == "audio"
    )
    run(
        [
            executable("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(voice),
            "-stream_loop",
            "-1",
            "-i",
            str(music),
            "-filter_complex",
            music_filter(duration, gain_db, voice_audio["channels"]),
            "-filter_complex_threads",
            "1",
            "-map",
            "[out]",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            "-t",
            str(duration),
            "-fs",
            str(max_bytes),
            str(destination),
        ],
        timeout=120,
    )
    if abs(float(probe(destination)["format"]["duration"]) - duration) > 0.1:
        raise MediaError("Music mixing ended early. Check the disk budget and retry.")


def render(snapshot, images, export_folder, scratch, progress):
    missing = [key for key, available in readiness().items() if not available]
    if missing:
        raise MediaError(
            "Missing dependencies: " + ", ".join(missing) + ". Run scripts/setup-media-windows.ps1."
        )
    scratch.mkdir(parents=True, exist_ok=True)
    export_folder.mkdir(parents=True, exist_ok=True)
    disk_guard(scratch.parent, reserve=200 * 1024**2, extra_folder=export_folder)
    width, height = (1080, 1920) if snapshot["quality"] == "1080p" else (720, 1280)
    progress("voice", 10)
    voice = export_folder / "narration.wav"
    run(
        [sys.executable, "-m", "piper", "-m", str(voice_model()), "-f", str(voice)],
        input_text=snapshot["script"],
        timeout=300,
    )
    duration = float(probe(voice)["format"]["duration"])
    if not 0.2 <= duration <= 180:
        raise MediaError(
            "Narration must be between 0.2 and 180 seconds. Shorten the script and approve again."
        )
    soundtrack = voice
    music = snapshot.get("music")
    if music:
        progress("music-mix", 18)
        copy = export_folder / "music.wav"
        shutil.copyfile(music["local_path"], copy)
        soundtrack = export_folder / "mixed.wav"
        mix_music(
            voice,
            copy,
            soundtrack,
            duration,
            snapshot["music_gain_db"],
            disk_guard(scratch.parent, extra_folder=export_folder),
        )
        disk_guard(scratch.parent, extra_folder=export_folder)
    scenes = snapshot.get("scenes")
    if scenes is None:
        # Compatibility for direct callers without a persisted scene plan.
        if images:
            originals = images
        elif snapshot["placeholders"]:
            originals = placeholder_pack(scratch / "placeholders")
        else:
            raise MediaError("Upload licensed images or explicitly choose placeholders.")
        scenes = [
            {"id": None, "image_asset_id": None, "duration_weight": 1, "motion_style": "zoom_in"}
            for _ in originals
        ]
    else:
        if not scenes:
            raise MediaError("Keep at least one scene included in the video.")
        needs_placeholders = any(not scene["image_asset_id"] for scene in scenes)
        if needs_placeholders and not snapshot["placeholders"]:
            raise MediaError("The placeholder pack was not selected for this project.")
        pack = placeholder_pack(scratch / "placeholders") if needs_placeholders else []
        originals = []
        for scene in scenes:
            if scene["image_asset_id"]:
                originals.append(Path(scene["local_path"]))
            else:
                index = scene.get("placeholder_index")
                if index not in range(6):
                    raise MediaError("Invalid placeholder scene. Reload your scene plan.")
                originals.append(pack[index])
    destination = export_folder / "images"
    destination.mkdir(exist_ok=True)
    images = []
    for idx, original in enumerate(originals):
        copy = destination / f"scene_{idx + 1:02}.jpg"
        shutil.copyfile(original, copy)
        images.append(copy)
    disk_guard(scratch.parent, extra_folder=export_folder)
    write_srt(export_folder / "captions.srt", snapshot["script"], duration)
    write_ass(export_folder / "captions.ass", snapshot["script"], duration, width, height)
    frames = math.ceil(duration * 25)
    clips = []
    frame_counts = allocate_scene_frames(frames, [scene["duration_weight"] for scene in scenes])
    timeline = []
    elapsed_frames = 0
    for idx, image in enumerate(images):
        progress("scenes", 20 + round(50 * idx / len(images)))
        count = frame_counts[idx]
        timeline.append(
            {
                "scene_id": scenes[idx]["id"],
                "image_asset_id": scenes[idx]["image_asset_id"],
                "file": "images/" + image.name,
                "motion_style": scenes[idx]["motion_style"],
                "duration_weight": scenes[idx]["duration_weight"],
                "start_ms": round(elapsed_frames * 1000 / 25),
                "end_ms": min(round((elapsed_frames + count) * 1000 / 25), round(duration * 1000)),
            }
        )
        elapsed_frames += count
        clip = scratch / f"clip_{idx:02}.mp4"
        remaining = disk_guard(scratch.parent, extra_folder=export_folder)
        vf = scene_filter(width, height, count, scenes[idx]["motion_style"])
        run(
            [
                executable("ffmpeg"),
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-i",
                str(image),
                "-vf",
                vf,
                "-frames:v",
                str(count),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "24",
                "-color_range",
                "tv",
                "-threads",
                "2",
                "-filter_threads",
                "1",
                "-fs",
                str(remaining),
                str(clip),
            ]
        )
        disk_guard(scratch.parent, extra_folder=export_folder)
        if abs(float(probe(clip)["format"]["duration"]) - count / 25) > 0.1:
            raise MediaError("Scene encoding ended early. Check the scratch disk budget and retry.")
        clips.append(clip)
    manifest = scratch / "concat.txt"
    # Generated relative names avoid Windows drive-colon and apostrophe escaping.
    manifest.write_text("".join(f"file '{clip.name}'\n" for clip in clips), encoding="utf-8")
    progress("captions", 80)
    shutil.copyfile(export_folder / "captions.ass", scratch / "captions.ass")
    final = export_folder / "final.mp4"
    run(
        [
            executable("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-f",
            "concat",
            "-safe",
            "1",
            "-i",
            "concat.txt",
            "-i",
            str(soundtrack),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            "ass=filename=captions.ass",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-color_range",
            "tv",
            "-threads",
            "2",
            "-filter_threads",
            "1",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-af",
            "alimiter=limit=0.85:level=false:latency=true",
            "-t",
            str(duration),
            "-fs",
            str(disk_guard(scratch.parent, extra_folder=export_folder)),
            "-movflags",
            "+faststart",
            str(final),
        ],
        cwd=scratch,
    )
    progress("verify", 95)
    metadata = probe(final)
    video = next((s for s in metadata["streams"] if s["codec_type"] == "video"), {})
    audio = next((s for s in metadata["streams"] if s["codec_type"] == "audio"), {})
    actual = float(metadata["format"]["duration"])
    if (
        video.get("codec_name") != "h264"
        or audio.get("codec_name") != "aac"
        or video.get("pix_fmt") != "yuv420p"
        or (video.get("width"), video.get("height")) != (width, height)
        or abs(actual - duration) > 0.25
    ):
        raise MediaError("Export verification failed. Retry at 720p or check your FFmpeg build.")
    disk_guard(scratch.parent, extra_folder=export_folder)
    return {
        "file_path": str(final),
        "width": width,
        "height": height,
        "duration_ms": round(actual * 1000),
        "sha256": digest(final),
        "caption_timing": "approximate word-count-weighted",
        "voice": voice_model().name,
        "scene_timeline": timeline,
    }
