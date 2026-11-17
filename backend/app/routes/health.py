from __future__ import annotations

import asyncio

from fastapi import APIRouter

from ..config import settings
from ..deps import ollama, voicestudio

router = APIRouter()


@router.get("/api/health")
async def health() -> dict:
    async def check_ollama():
        try:
            return {"ok": True, "url": settings.ollama_url, "version": await ollama.version()}
        except Exception as e:  # noqa: BLE001 - report any failure to the UI
            return {
                "ok": False,
                "url": settings.ollama_url,
                "error": str(e) or type(e).__name__,
                "hint": "Start Ollama: systemctl start ollama  (or: ollama serve)",
            }

    async def check_voicestudio():
        try:
            info = await voicestudio.discovery()
            return {"ok": True, "url": settings.voicestudio_url, "protocol": info.get("schema") or info.get("protocol")}
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False,
                "url": settings.voicestudio_url,
                "error": str(e) or type(e).__name__,
                "hint": "Install/start VoiceStudio on port 3900 (voice features are disabled until then)",
            }

    o, v = await asyncio.gather(check_ollama(), check_voicestudio())
    return {"ok": o["ok"], "ollama": o, "voicestudio": v}
