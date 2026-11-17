"""Speech-to-text.

WS   /ws/stt   -> bidirectional proxy to VoiceStudio's live transcription socket
                  (browser sends WebM/Opus binary frames + {"type":"input_audio.end"};
                  server relays session.started / partial / final frames).
POST /api/stt  -> batch fallback: upload a whole recording, get {"text"} back.
"""

from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState
from websockets.asyncio.client import connect as ws_connect

from ..config import LOCAL_HOSTS, settings
from ..deps import effective_settings, voicestudio
from ..services.voicestudio import VoiceStudioError

router = APIRouter()
log = logging.getLogger("avtaar.stt")

# Query parameters the browser may pass through to VoiceStudio.
PASS_PARAMS = {"pcm", "sr", "language", "model"}
MAX_UPLOAD = 50 * 1024 * 1024


def origin_allowed(origin: str | None) -> bool:
    """WebSockets bypass CORS, so refuse connections from non-local web pages."""
    if not origin:
        return True  # non-browser clients (tests, CLI)
    host = urlparse(origin).hostname
    return settings.allow_lan or host in LOCAL_HOSTS


@router.websocket("/ws/stt")
async def stt_stream(ws: WebSocket):
    if not origin_allowed(ws.headers.get("origin")):
        await ws.close(code=1008, reason="origin not allowed")
        return
    await ws.accept()

    params = {k: v for k, v in ws.query_params.items() if k in PASS_PARAMS}
    lang = effective_settings()["stt_language"]
    if lang and "language" not in params:
        params["language"] = lang
    url = voicestudio.stream_url + (f"?{urlencode(params)}" if params else "")

    try:
        upstream = await ws_connect(
            url, max_size=None, open_timeout=5, ping_interval=20, additional_headers=voicestudio.auth_headers
        )
    except Exception as e:  # noqa: BLE001
        log.warning("live STT upstream unavailable: %s", e)
        await ws.send_text(json.dumps({"type": "error", "code": "upstream_unavailable", "message": str(e)}))
        await ws.close(code=1011)
        return

    async def browser_to_upstream():
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    await upstream.send(msg["bytes"])
                elif msg.get("text") is not None:
                    await upstream.send(msg["text"])
        except WebSocketDisconnect:
            pass

    async def upstream_to_browser():
        async for m in upstream:
            if isinstance(m, bytes):
                await ws.send_bytes(m)
            else:
                await ws.send_text(m)

    tasks = {asyncio.create_task(browser_to_upstream()), asyncio.create_task(upstream_to_browser())}
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            if t.exception() and not isinstance(t.exception(), WebSocketDisconnect):
                log.warning("live STT relay error: %s", t.exception())
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await upstream.close()
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.close()


@router.post("/api/stt")
async def stt_batch(file: UploadFile = File(...), language: str | None = Form(None)) -> dict:
    audio = await file.read(MAX_UPLOAD + 1)
    if len(audio) > MAX_UPLOAD:
        raise HTTPException(413, "Recording too large")
    if not audio:
        raise HTTPException(422, "Empty recording")
    prefs = effective_settings()
    try:
        res = await voicestudio.transcribe(
            audio,
            file.filename or "speech.webm",
            file.content_type or "audio/webm",
            model=prefs["stt_model"],
            language=language or prefs["stt_language"] or None,
        )
    except VoiceStudioError as e:
        raise HTTPException(502 if e.status >= 500 else e.status, str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(503, f"VoiceStudio not reachable: {e or type(e).__name__}") from e
    return {"text": (res.get("text") or "").strip()}
