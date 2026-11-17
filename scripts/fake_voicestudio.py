#!/usr/bin/env python3
"""A tiny stand-in for VoiceStudio, for developing/testing the app without it.

Implements just enough of the documented API:
  GET  /.well-known/voicestudio-speech
  GET  /v1/audio/voices
  POST /v1/audio/speech        -> a soft tone WAV whose length tracks the text length
  POST /v1/audio/transcriptions        -> fixed transcript (batch STT)
  WS   /v1/audio/transcriptions/stream -> session.started, then one more word as a
                                          `partial` per ~N audio frames, then `final`
                                          frames after {"type":"input_audio.end"}
  GET  /_log                   -> the last requests received (for tests)

Env: FAKE_NO_STREAM=1 rejects the live STT socket (to exercise the batch fallback).

    backend/.venv/bin/python scripts/fake_voicestudio.py   # listens on 127.0.0.1:3900

Stop it before starting the real VoiceStudio (same port).
"""

from __future__ import annotations

import io
import json
import math
import os
import struct
import time
import uuid
import wave

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

app = FastAPI()
LOG: list[dict] = []
SR = 24000


def tone_wav(text: str) -> bytes:
    seconds = min(6.0, 0.25 + 0.055 * len(text))
    n = int(SR * seconds)
    freq = 180 + (sum(map(ord, text)) % 120)
    frames = bytearray()
    for i in range(n):
        t = i / SR
        env = min(1.0, t / 0.03, (seconds - t) / 0.05)
        # Syllable-like amplitude wobble so it sounds vaguely speech-paced.
        wobble = 0.55 + 0.45 * math.sin(2 * math.pi * 4.5 * t) ** 2
        v = 0.18 * env * wobble * math.sin(2 * math.pi * freq * t)
        frames += struct.pack("<h", int(v * 32767))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(frames))
    return buf.getvalue()


@app.get("/.well-known/voicestudio-speech")
def discovery():
    return {"schema": "voicestudio.speech.v1", "fake": True, "features": {"native_dictation_control": False}}


@app.get("/health")
def health():
    return {"status": "ok", "device": "cpu", "engine": "fake", "version": "0.0-fake"}


LAST_TTS = {"text": ""}


@app.get("/v1/audio/voices")
def voices():
    return {
        "voices": [
            {"voice_id": "fake-aria", "name": "Aria (fake)", "addressable_by_name": True},
            {"voice_id": "fake-dev", "name": "Dev (fake)", "addressable_by_name": True},
        ]
    }


@app.post("/v1/audio/speech")
async def speech(body: dict):
    LOG.append({"t": time.time(), **body})
    del LOG[:-200]
    LAST_TTS["text"] = body.get("input", "")
    delay = float(os.environ.get("FAKE_TTS_DELAY", "0.3"))
    if delay:
        import asyncio

        await asyncio.sleep(delay)
    return Response(tone_wav(body.get("input", "")), media_type="audio/wav")


TRANSCRIPT = "hello avatar what is the tallest mountain on mars"


@app.post("/v1/audio/transcriptions")
async def transcriptions(request: Request):
    form = await request.form()
    f = form.get("file")
    size = len(await f.read()) if f is not None else 0
    LOG.append({"t": time.time(), "stt_batch": True, "bytes": size, "model": form.get("model"), "language": form.get("language")})
    # Round-trip tests: "recognise" the last thing we were asked to say.
    if os.environ.get("FAKE_ECHO_STT", "1") == "1" and LAST_TTS["text"] and size > 40000:
        return {"text": LAST_TTS["text"]}
    return {"text": TRANSCRIPT.capitalize() + "?"}


@app.websocket("/v1/audio/transcriptions/stream")
async def stream(ws: WebSocket):
    if os.environ.get("FAKE_NO_STREAM") == "1":
        await ws.close(code=1011)
        return
    await ws.accept()
    sid = uuid.uuid4().hex[:8]
    words = TRANSCRIPT.split()
    entry = {"t": time.time(), "stt_stream": True, "frames": 0, "bytes": 0, "query": dict(ws.query_params)}
    LOG.append(entry)
    await ws.send_json({"type": "session.started", "protocol": "voicestudio.speech.v1", "session_id": sid})
    per_word = int(os.environ.get("FAKE_FRAMES_PER_WORD", "2"))
    shown = 0
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                return
            if msg.get("bytes") is not None:
                entry["frames"] += 1
                entry["bytes"] += len(msg["bytes"])
                n = min(len(words), entry["frames"] // per_word)
                if n > shown:
                    shown = n
                    await ws.send_json({"type": "partial", "text": " ".join(words[:shown]), "session_id": sid})
            elif msg.get("text") and json.loads(msg["text"]).get("type") == "input_audio.end":
                text = " ".join(words[: max(shown, 1)]).capitalize()
                await ws.send_json({"type": "final", "final_kind": "utterance", "text": text, "session_id": sid})
                await ws.send_json({"type": "final", "final_kind": "summary", "text": text, "session_id": sid})
                await ws.close()
                return
    except WebSocketDisconnect:
        return


@app.get("/_log")
def log():
    return LOG


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "3900")), log_level="warning")
