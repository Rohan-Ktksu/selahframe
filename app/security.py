"""Optional single-owner authentication for an HTTPS deployment."""

import base64
import binascii
import os
import secrets
from urllib.parse import urlsplit


def public_origin():
    value = (
        (
            os.getenv("SELAHFRAME_PUBLIC_URL")
            or (
                os.getenv("RENDER_EXTERNAL_URL", "")
                if os.getenv("SELAHFRAME_ONLINE") == "1"
                else ""
            )
        )
        .strip()
        .rstrip("/")
    )
    if not value:
        return ""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("SELAHFRAME_PUBLIC_URL must be an HTTPS origin without a path.")
    return value


def validate():
    origin = public_origin()
    if os.getenv("SELAHFRAME_ONLINE") == "1" and not origin:
        raise RuntimeError("Set SELAHFRAME_PUBLIC_URL before starting an online deployment.")
    if origin:
        password = os.getenv("SELAHFRAME_PASSWORD", "")
        username = os.getenv("SELAHFRAME_USER", "owner")
        if len(password) < 24 or any(ord(c) < 32 for c in password):
            raise RuntimeError(
                "Set a SELAHFRAME_PASSWORD of at least 24 characters before deploying."
            )
        if not username or ":" in username or any(ord(c) < 32 for c in username):
            raise RuntimeError("Set a valid SELAHFRAME_USER.")


def authorized(header):
    try:
        scheme, token = header.split(" ", 1)
        if scheme.lower() != "basic" or len(token) > 4096:
            return False
        username, password = base64.b64decode(token, validate=True).decode("utf-8").split(":", 1)
    except (ValueError, UnicodeError, binascii.Error):
        return False
    user_ok = secrets.compare_digest(
        username.encode(), os.getenv("SELAHFRAME_USER", "owner").encode()
    )
    password_ok = secrets.compare_digest(
        password.encode(), os.getenv("SELAHFRAME_PASSWORD", "").encode()
    )
    return user_ok and password_ok
