"""Live scene-editor regression. Start the local server before running this script."""

import io
import json
import sys
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import media  # noqa: E402 - project root bootstrap for direct script execution

BASE = "http://127.0.0.1:8000/api/v1"


def request(method, route, **kwargs):
    response = requests.request(method, BASE + route, timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()


def main():
    project = request(
        "POST",
        "/projects",
        json={
            "title": "Scene editor - uploaded image order test",
            "reference": "Psalm 23:1",
            "scripture": "Yahweh is my shepherd; I shall lack nothing.",
            "translation": "World English Bible Classic",
            "scripture_source": "https://ebible.org/eng-web/PSA023.htm",
            "source_license": "Public domain",
            "context_text": "Verse 2: He makes me lie down in green pastures. He leads me beside still waters.",
            "placeholders": False,
        },
    )
    pid = project["id"]
    route = "/projects/" + pid
    narration = (
        "This is a scene editor test. The blue image should appear first and stay twice as long as the red image. "
        "The green image is excluded. The pictures are labeled technical test cards, and the voice is generated locally."
    )
    script = request("PUT", route + "/script", json={"script": narration})
    # Only this fixed, reviewed technical fixture is approved by the developer test.
    request("POST", route + "/script:approve", json={"script_version": script["script_version"]})
    originals = []
    for name, color in [("RED", "#da3025"), ("BLUE", "#1a4ae5"), ("GREEN", "#348045")]:
        image = Image.new("RGB", (720, 1280), color)
        draw = ImageDraw.Draw(image)
        draw.text(
            (360, 500),
            name + " TEST CARD",
            anchor="mm",
            font=ImageFont.load_default(size=36),
            fill="white",
        )
        data = io.BytesIO()
        image.save(data, "PNG")
        uploaded = request(
            "POST",
            route + "/images",
            files={"image": (name + ".png", data.getvalue(), "image/png")},
            data={
                "source_url": "App-generated " + name + " test card",
                "license_name": "Original geometric test fixture; project-owned",
            },
        )
        originals.append(ROOT / "output" / pid / "images" / uploaded["filename"])
    current = request("GET", route + "/scenes")
    scenes = [
        {key: scene[key] for key in ("id", "enabled", "duration_weight", "motion_style")}
        for scene in current["scenes"]
    ]
    scenes[0], scenes[1] = scenes[1], scenes[0]
    scenes[0].update(duration_weight=2, motion_style="still")
    scenes[1].update(duration_weight=1, motion_style="zoom_out")
    scenes[2]["enabled"] = False
    request(
        "PUT",
        route + "/scenes",
        json={"image_revision": current["image_revision"], "scenes": scenes},
    )
    start = time.monotonic()
    job = request("POST", route + "/render", json={"quality": "720p"})
    job_id = job["job_id"]
    for _ in range(180):
        status = request("GET", "/jobs/" + job_id)
        if status["status"] in {"complete", "failed"}:
            break
        time.sleep(1)
    if status["status"] != "complete":
        raise RuntimeError(status.get("error") or "Render did not complete")
    folder = ROOT / "output" / pid / "exports" / job_id
    manifest = json.loads((folder / "export.json").read_text(encoding="utf-8"))
    timeline = manifest["scene_timeline"]
    assert len(timeline) == 2
    assert timeline[0]["scene_id"] == scenes[0]["id"] and timeline[1]["scene_id"] == scenes[1]["id"]
    lengths = [item["end_ms"] - item["start_ms"] for item in timeline]
    assert abs(lengths[0] - 2 * lengths[1]) <= 120
    assert all(path.exists() for path in originals), "Excluded originals must be preserved"
    assert manifest["images"][0]["source_url"] == "App-generated BLUE test card"
    assert manifest["images"][1]["source_url"] == "App-generated RED test card"
    for label, seconds, channel in [
        ("first", 1, 2),
        ("last", timeline[-1]["end_ms"] / 1000 - 1, 0),
    ]:
        frame = ROOT / "temp" / f"scene-{label}.png"
        media.run(
            [
                media.executable("ffmpeg"),
                "-y",
                "-ss",
                str(seconds),
                "-i",
                str(folder / "final.mp4"),
                "-frames:v",
                "1",
                str(frame),
            ]
        )
        with Image.open(frame) as sample:
            pixel = sample.getpixel((20, 20))
            assert pixel[channel] > 180 and max(pixel[i] for i in range(3) if i != channel) < 120, (
                label,
                pixel,
            )
    summary = {
        "project_id": pid,
        "job_id": job_id,
        "elapsed_seconds": round(time.monotonic() - start, 2),
        "scene_lengths_ms": lengths,
        "verified_order": ["BLUE", "RED"],
        "excluded_original_preserved": True,
        "video": str(folder / "final.mp4"),
    }
    (ROOT / "temp" / "scene-upload-test.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
