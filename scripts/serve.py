"""Single-process container entrypoint; keep the public studio owner protected."""

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import security  # noqa: E402
import uvicorn  # noqa: E402

if __name__ == "__main__":
    security.validate()
    storage = Path(os.environ.get("SELAHFRAME_STORAGE", str(ROOT)))
    folders = [storage, *(storage / name for name in ("data", "output", "temp"))]
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)
    if hasattr(os, "getuid") and os.getuid() == 0:
        for folder in folders:
            os.chown(folder, 10001, 10001)
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        workers=1,
        proxy_headers=False,
    )
