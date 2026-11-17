"""Text-to-speech proxy: POST /api/tts streams audio from VoiceStudio; GET /api/voices lists voices."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from ..deps import effective_settings, voicestudio
from ..services.voicestudio import AUDIO_TYPES, VoiceStudioError

router = APIRouter(prefix="/api")


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice: str | None = None
    model: str | None = None
    speed: float | None = Field(default=None, ge=0.25, le=4.0)
    format: str = "wav"


@router.post("/tts")
async def tts(req: TTSRequest):
    if req.format not in AUDIO_TYPES:
        raise HTTPException(422, f"format must be one of {sorted(AUDIO_TYPES)}")
    prefs = effective_settings()
    payload = {
        "model": req.model or prefs["tts_model"],
        "voice": req.voice or prefs["tts_voice"],
        "input": req.text,
        "speed": req.speed or float(prefs["tts_speed"]),
        "response_format": req.format,
    }
    try:
        resp = await voicestudio.speech(payload)
    except VoiceStudioError as e:
        raise HTTPException(502 if e.status >= 500 else e.status, str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(503, f"VoiceStudio not reachable: {e or type(e).__name__}") from e

    return StreamingResponse(
        resp.aiter_bytes(),
        media_type=resp.headers.get("content-type", AUDIO_TYPES[req.format]),
        headers={"Cache-Control": "no-store"},
        background=BackgroundTask(resp.aclose),
    )


@router.get("/voices")
async def voices() -> dict:
    try:
        items = await voicestudio.voices()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"VoiceStudio not reachable: {e or type(e).__name__}") from e
    return {"voices": items, "current": effective_settings()["tts_voice"]}
