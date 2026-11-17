"""Custom avatar images.

GET    /api/avatar            -> {"idle": url, "talking": url, "custom": {...}}
POST   /api/avatar/{kind}     -> upload an image for `idle` (static) or `talking` (animated GIF etc.)
DELETE /api/avatar/{kind}     -> revert to the built-in placeholder
GET    /avatars/{kind}        -> serve the uploaded image
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..config import settings

router = APIRouter()

Kind = Literal["idle", "talking"]
DEFAULTS = {"idle": "/avatar/idle.png", "talking": "/avatar/talking.gif"}
MAX_BYTES = 8 * 1024 * 1024
EXT_BY_TYPE = {"png": ".png", "jpeg": ".jpg", "gif": ".gif", "webp": ".webp"}
MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}


def avatar_dir() -> Path:
    d = settings.data_dir / "avatars"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sniff(data: bytes) -> str | None:
    """Identify the image type from its bytes (never trust the upload's content-type)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def current_file(kind: str) -> Path | None:
    for ext in MEDIA:
        p = avatar_dir() / f"{kind}{ext}"
        if p.is_file():
            return p
    return None


def state() -> dict:
    out: dict = {"custom": {}}
    for kind, default in DEFAULTS.items():
        p = current_file(kind)
        out["custom"][kind] = p is not None
        out[kind] = f"/avatars/{kind}?v={int(p.stat().st_mtime_ns // 1_000_000)}" if p else default
    return out


@router.get("/api/avatar")
def get_avatar() -> dict:
    return state()


@router.post("/api/avatar/{kind}")
async def upload_avatar(kind: Kind, file: UploadFile = File(...)) -> dict:
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image too large (max 8 MB)")
    kind_type = sniff(data)
    if not kind_type:
        raise HTTPException(415, "Use a PNG, JPEG, GIF or WebP image")
    for ext in MEDIA:
        (avatar_dir() / f"{kind}{ext}").unlink(missing_ok=True)
    (avatar_dir() / f"{kind}{EXT_BY_TYPE[kind_type]}").write_bytes(data)
    return state()


@router.delete("/api/avatar/{kind}")
def reset_avatar(kind: Kind) -> dict:
    for ext in MEDIA:
        (avatar_dir() / f"{kind}{ext}").unlink(missing_ok=True)
    return state()


@router.get("/avatars/{kind}", include_in_schema=False)
def serve_avatar(kind: Kind):
    p = current_file(kind)
    if not p:
        raise HTTPException(404, "No custom avatar")
    return FileResponse(p, media_type=MEDIA[p.suffix], headers={"Cache-Control": "no-cache"})
