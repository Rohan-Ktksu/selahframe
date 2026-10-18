"""Real FFmpeg ducking calibration and optional live API music export regression.

Start the local server, then run: python scripts/smoke-music.py --render
Only fixed technical fixture narration is approved by this developer test.
"""

import argparse
import array
import json
import math
import sys
import time
import wave
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import media  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"


def make_wave(path, seconds, signal, rate=32000):
    samples = array.array(
        "h", (round(32767 * signal(i / rate)) for i in range(round(seconds * rate)))
    )
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(samples.tobytes())


def read_wave(path):
    with wave.open(str(path), "rb") as audio:
        rate, channels = audio.getframerate(), audio.getnchannels()
        samples = array.array("h", audio.readframes(audio.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    return rate, samples[::channels]


def component(samples, rate, start, end, frequency):
    values = samples[round(start * rate) : round(end * rate)]
    # Orthogonal tone projection separates the voice and background fixture signals.
    real = sum(v * math.cos(2 * math.pi * frequency * i / rate) for i, v in enumerate(values))
    imag = sum(v * math.sin(2 * math.pi * frequency * i / rate) for i, v in enumerate(values))
    return 2 * math.hypot(real, imag) / len(values) / 32767


def calibrate(folder):
    voice, track, mix = (folder / name for name in ("voice.wav", "tone.wav", "mix.wav"))
    make_wave(
        voice,
        8,
        lambda t: 0.4 * math.sin(2 * math.pi * 1000 * t) if 1 <= t < 3 or 5 <= t < 7 else 0,
    )
    make_wave(track, 2, lambda t: 0.2 * math.sin(2 * math.pi * 220 * t))
    media.mix_music(voice, track, mix, 8, -12, 10 * 1024**2)
    rate, samples = read_wave(mix)
    quiet = component(samples, rate, 4.2, 4.7, 220)
    under_voice = component(samples, rate, 2, 2.5, 220)
    reduction = 20 * math.log10(quiet / under_voice)
    voice_level = component(samples, rate, 2, 2.5, 1000)
    peak = max(abs(v) for v in samples) / 32767
    assert reduction >= 6, ("Ducking too weak", reduction)
    assert abs(voice_level - 0.4) < 0.01, ("Voice level changed", voice_level)
    assert peak < 0.86, ("Mix clipped", peak)
    assert abs(len(samples) / rate - 8) < 0.01
    return {
        "ducking_reduction_db": round(reduction, 2),
        "voice_amplitude": round(voice_level, 4),
        "peak_dbfs": round(20 * math.log10(peak), 2),
        "duration_seconds": len(samples) / rate,
    }


def check_import_formats(folder):
    source = folder / "tone.wav"
    durations = {}
    for suffix in (".wav", ".mp3", ".flac"):
        track = source
        if suffix != ".wav":
            track = folder / ("tone" + suffix)
            media.run(
                [
                    media.executable("ffmpeg"),
                    "-v",
                    "error",
                    "-nostdin",
                    "-y",
                    "-i",
                    str(source),
                    str(track),
                ]
            )
        normalized = folder / (suffix[1:] + "-normalized.wav")
        durations[suffix] = media.normalize_music(track, normalized, 40 * 1024**2)
        assert abs(durations[suffix] - 2000) <= 100
    broken = folder / "broken.wav"
    broken.write_bytes(b"This is not an audio file")
    try:
        media.normalize_music(broken, folder / "broken-normalized.wav", 40 * 1024**2)
    except media.MediaError:
        pass
    else:
        raise AssertionError("Malformed audio was accepted")
    return durations


def request(method, route, **kwargs):
    response = requests.request(method, BASE + route, timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()


def wait_job(job_id):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        job = request("GET", "/jobs/" + job_id)
        if job["status"] == "failed":
            raise RuntimeError(job["error"])
        if job["status"] == "complete":
            return job
        time.sleep(0.5)
    raise RuntimeError("Timed out waiting for the local music job")


def live_render(folder):
    project = request(
        "POST",
        "/projects",
        json={
            "title": "Music mix - original test chord",
            "reference": "Psalm 23:1",
            "scripture": "Yahweh is my shepherd; I shall lack nothing.",
            "translation": "World English Bible Classic",
            "scripture_source": "https://ebible.org/eng-web/PSA023.htm",
            "source_license": "Public domain",
            "context_text": "Verse 2: He makes me lie down in green pastures. He leads me beside still waters.",
            "placeholders": True,
        },
    )
    pid = project["id"]
    route = "/projects/" + pid
    script = request(
        "PUT",
        route + "/script",
        json={
            "script": "This is a background music test. The quiet original chord should continue beneath this locally generated voice. "
            "The music fades at both ends and drops during speech. Please review the balance in the video preview."
        },
    )
    request("POST", route + "/script:approve", json={"script_version": script["script_version"]})
    chord = folder / "original-test-chord.wav"
    make_wave(
        chord,
        4,
        lambda t: 0.12 * sum(math.sin(2 * math.pi * f * t) for f in (220, 261.6256, 329.6276)),
    )
    with chord.open("rb") as handle:
        job = request(
            "POST",
            route + "/music/tracks",
            files={"track": (chord.name, handle, "audio/wav")},
            data={
                "source_url": "SelahFrame developer-generated A minor sine chord",
                "license_name": "Original mathematical audio test fixture; project-owned",
                "rights_confirmed": "true",
            },
        )
    wait_job(job["job_id"])
    plan = request("GET", route + "/music")
    assert not plan["enabled"]
    baseline_job = request("POST", route + "/render", json={"quality": "720p"})
    wait_job(baseline_job["job_id"])
    baseline = ROOT / "output" / pid / "exports" / baseline_job["job_id"]
    assert json.loads((baseline / "export.json").read_text(encoding="utf-8"))["music"] is None
    request(
        "PUT",
        route + "/music",
        json={
            "music_revision": plan["music_revision"],
            "asset_id": plan["asset_id"],
            "enabled": True,
            "gain_db": -18,
        },
    )
    started = time.monotonic()
    job = request("POST", route + "/render", json={"quality": "720p"})
    wait_job(job["job_id"])
    elapsed = time.monotonic() - started
    assert job["job_id"] != baseline_job["job_id"]
    export = ROOT / "output" / pid / "exports" / job["job_id"]
    manifest = json.loads((export / "export.json").read_text(encoding="utf-8"))
    assert manifest["music"]["id"] == plan["asset_id"] and manifest["music"]["gain_db"] == -18
    assert "local_path" not in manifest["music"]
    for name, checksum in manifest["asset_checksums"].items():
        assert media.digest(export / name) == checksum
    assert (baseline / "final.mp4").is_file()
    decoded = folder / "export-aac.wav"
    media.run(
        [
            media.executable("ffmpeg"),
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(export / "final.mp4"),
            "-vn",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(decoded),
        ]
    )
    rate, audio = read_wave(decoded)
    peak = max(abs(v) for v in audio) / 32767
    assert peak < 0.99, ("AAC audio reached clipping", peak)
    preview = requests.get(
        BASE + route + "/music/tracks/" + plan["asset_id"] + "/preview",
        headers={"Range": "bytes=0-1023"},
        timeout=10,
    )
    assert preview.status_code == 206 and len(preview.content) == 1024
    cached = request("POST", route + "/render", json={"quality": "720p"})
    assert cached["job_id"] == job["job_id"] and cached["status"] == "complete"
    return {
        "project_id": pid,
        "job_id": job["job_id"],
        "duration_ms": manifest["duration_ms"],
        "render_seconds": round(elapsed, 2),
        "aac_peak_dbfs": round(20 * math.log10(peak), 2),
        "url": "http://127.0.0.1:8000/?project=" + pid + "#musicEditor",
        "file": str(export / "final.mp4"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    folder = ROOT / "temp" / ("music-smoke-" + str(time.time_ns()))
    folder.mkdir(parents=True)
    result = {"calibration": calibrate(folder), "format_duration_ms": check_import_formats(folder)}
    if args.render:
        result["live_render"] = live_render(folder)
    (ROOT / "temp" / "music-smoke.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
