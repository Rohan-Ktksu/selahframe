"""Bounded AI Horde client. No paid fallback and no arbitrary media downloads."""

import base64
import binascii
import io
import json
import os
import time
import uuid
import warnings

import requests
from PIL import Image, ImageOps

BASE = "https://aihorde.net/api/v2"
MODEL = "stable_diffusion"
MAX_RESPONSE = 18 * 1024**2


class ImageError(RuntimeError):
    pass


class Cancelled(ImageError):
    pass


def anonymous():
    return os.getenv("AI_HORDE_API_KEY", "0000000000").strip() in {"", "0000000000"}


def api(method, path, payload=None):
    headers = {
        "apikey": os.getenv("AI_HORDE_API_KEY", "0000000000").strip() or "0000000000",
        "Client-Agent": "SelahFrame:0.5:github.com/Rohan-Ktksu/selahframe",
    }
    try:
        with requests.request(
            method,
            BASE + path,
            headers=headers,
            json=payload,
            timeout=(10, 45),
            stream=True,
            allow_redirects=False,
        ) as response:
            if response.status_code not in {200, 202}:
                reason = {
                    401: "API key was rejected",
                    403: "request was refused",
                    429: "service is busy or rate limited",
                    503: "service is unavailable",
                }.get(response.status_code, "request could not be accepted")
                raise ImageError(f"AI Horde {reason}. Try again later; no paid fallback was used.")
            data = bytearray()
            for block in response.iter_content(65536):
                data.extend(block)
                if len(data) > MAX_RESPONSE:
                    raise ImageError("AI Horde response exceeded the image size limit.")
            value = json.loads(data)
            if not isinstance(value, dict):
                raise ValueError()
            return value
    except (requests.RequestException, ValueError) as exc:
        raise ImageError(
            "AI Horde could not be reached or returned an invalid response. Retry explicitly; no paid fallback was used."
        ) from exc


def prompts(text, count, direction=""):
    words = text.split()
    if not words:
        raise ImageError("Save narration or enter a verified passage first.")
    angles = [
        "wide establishing composition",
        "medium environmental composition",
        "close detail composition",
        "wide closing composition",
    ]
    result = []
    for index in range(count):
        start, end = len(words) * index // count, len(words) * (index + 1) // count
        focus = " ".join(words[start:end]) or text
        result.append(
            f"Cinematic photorealistic film still, portrait composition, natural light, realistic textures, {angles[index]}, "
            f"visual interpretation of this theme: {text[:1600]}. Scene focus: {focus[:600]}. "
            f"Visual direction: {direction[:500]}. An illustrative interpretation, no depiction of a deity. "
            "Keep the main subject centered for a vertical crop. ### text, letters, subtitles, logo, watermark, collage, distorted anatomy, blurry"
        )
    return result


def request_image(prompt, notify, cancelled, remember, *, timeout=600):
    request_id = None
    completed = False
    try:
        if cancelled():
            raise Cancelled("Image generation cancelled.")
        response = api(
            "POST",
            "/generate/async",
            {
                "prompt": prompt,
                "params": {
                    "width": 512,
                    "height": 768,
                    "steps": 20,
                    "n": 1,
                    "sampler_name": "k_euler",
                    "cfg_scale": 7,
                },
                "models": [MODEL],
                "nsfw": False,
                "censor_nsfw": True,
                "trusted_workers": True,
                "validated_backends": True,
                "r2": False,
                "shared": anonymous(),
                "allow_downgrade": True,
            },
        )
        request_id = str(uuid.UUID(response["id"]))
        remember(request_id)
        deadline = time.monotonic() + timeout
        while True:
            if cancelled():
                raise Cancelled("Image generation cancelled.")
            if time.monotonic() >= deadline:
                raise ImageError(
                    "AI Horde did not finish within 10 minutes for this image. The request was cancelled; retry later or try another provider."
                )
            state = api("GET", "/generate/check/" + request_id)
            if state.get("is_possible") is False and not state.get("processing"):
                raise ImageError(
                    "No eligible AI Horde workers are available for this image. Retry later; no paid fallback was used."
                )
            if state.get("faulted"):
                raise ImageError(
                    "AI Horde could not generate this scene. Try a simpler visual direction."
                )
            notify(
                max(0, min(int(state.get("queue_position", 0)), 100000)),
                max(0, min(int(state.get("wait_time", 0)), 86400)),
            )
            if state.get("done"):
                break
            # Cancellation remains responsive without polling the service more than every 5s.
            for _ in range(10):
                if cancelled():
                    raise Cancelled("Image generation cancelled.")
                time.sleep(0.5)
        result = api("GET", "/generate/status/" + request_id)
        generations = result.get("generations", [])
        if not generations:
            raise ImageError("AI Horde returned no image. Try again later.")
        generation = generations[0]
        if generation.get("censored") or any(
            item.get("type") == "censorship" for item in generation.get("gen_metadata", [])
        ):
            raise ImageError("AI Horde filtered this image. Change the visual direction and retry.")
        try:
            data = base64.b64decode(generation["img"], validate=True)
        except (ValueError, KeyError, binascii.Error) as exc:
            raise ImageError(
                "AI Horde did not return a valid inline image. No remote image URL was followed."
            ) from exc
        if not data or len(data) > 12 * 1024**2:
            raise ImageError("Generated image exceeds the size limit.")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if (
                    image.format not in {"WEBP", "PNG", "JPEG"}
                    or image.width * image.height > 20_000_000
                ):
                    raise ImageError("Generated image has an unsupported format or size.")
                image.load()
                cleaned = io.BytesIO()
                ImageOps.exif_transpose(image).convert("RGB").save(cleaned, "JPEG", quality=92)
        completed = True
        return (
            data,
            cleaned.getvalue(),
            {
                "request_id": request_id,
                "generation_id": str(generation.get("id", ""))[:80],
                "model": str(generation.get("model", MODEL))[:200],
                "seed": str(generation.get("seed", ""))[:80],
            },
        )
    except (
        KeyError,
        ValueError,
        OSError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as exc:
        raise ImageError("AI Horde returned an invalid image or job response.") from exc
    finally:
        if request_id and not completed:
            try:
                api("DELETE", "/generate/status/" + request_id)
            except ImageError:
                pass
