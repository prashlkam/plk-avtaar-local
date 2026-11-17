#!/usr/bin/env python3
"""Phase 0 smoke test for VoiceStudio: TTS a sentence, then STT it back.

Uses only the standard library (plus `websockets` if installed, for the live STT test).

    python3 scripts/smoke_tts_stt.py [--voice NAME] [--model ID]

Writes out/hello.wav and prints the transcript + a rough word-match score.
It also records the exact JSON frames from the streaming STT socket so the
contracts in Plan.md §4.2 can be confirmed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import urllib.request
import uuid
from pathlib import Path

BASE = os.environ.get("VOICESTUDIO_URL", "http://127.0.0.1:3900").rstrip("/")
TEXT = "Hello! I am your local avatar. The quick brown fox jumps over the lazy dog."
OUT = Path(__file__).resolve().parent.parent / "data" / "smoke"


def tts(text: str, voice: str, model: str) -> bytes:
    body = json.dumps({"model": model, "voice": voice, "input": text, "response_format": "wav"}).encode()
    req = urllib.request.Request(f"{BASE}/v1/audio/speech", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def stt_batch(wav: bytes) -> dict:
    boundary = uuid.uuid4().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\nwhisper-1\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="hello.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n".encode() + wav + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    req = urllib.request.Request(
        f"{BASE}/v1/audio/transcriptions",
        b"".join(parts),
        {"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


async def stt_stream(wav: bytes) -> list[dict]:
    try:
        import websockets
    except ImportError:
        print("  (skip live STT: pip install websockets)")
        return []
    # WAV -> raw PCM: assume 44-byte header; we ask the server for 16-bit mono PCM at the file's rate.
    import struct

    sr = struct.unpack_from("<I", wav, 24)[0]
    channels = struct.unpack_from("<H", wav, 22)[0]
    pcm = wav[44:]
    if channels != 1:
        print(f"  (skip live STT: expected mono WAV, got {channels} channels)")
        return []
    url = BASE.replace("http", "ws", 1) + f"/v1/audio/transcriptions/stream?pcm=1&sr={sr}"
    frames: list[dict] = []
    async with websockets.connect(url, max_size=None) as ws:
        chunk = sr * 2 // 5  # 200 ms
        for i in range(0, len(pcm), chunk):
            await ws.send(pcm[i : i + chunk])
            await asyncio.sleep(0.05)
        await ws.send(json.dumps({"type": "input_audio.end"}))
        try:
            async for msg in ws:
                f = json.loads(msg)
                frames.append(f)
                if f.get("type") == "final" and f.get("final_kind", "summary") == "summary":
                    break
        except Exception as e:  # noqa: BLE001
            print("  stream ended:", e)
    return frames


def words(s: str) -> list[str]:
    return re.findall(r"[a-z']+", s.lower())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="alloy", help="voice id/name (see GET /v1/audio/voices)")
    ap.add_argument("--model", default="tts-1", help="TTS engine id (OpenAI ids map to the active engine)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    print(f"VoiceStudio: {BASE}")
    print("1) TTS …")
    wav = tts(TEXT, args.voice, args.model)
    (OUT / "hello.wav").write_bytes(wav)
    print(f"   wrote {OUT / 'hello.wav'} ({len(wav)} bytes)")

    print("2) Batch STT …")
    res = stt_batch(wav)
    text = res.get("text", "")
    expected, got = set(words(TEXT)), set(words(text))
    print(f"   transcript: {text!r}")
    print(f"   word match: {len(expected & got)}/{len(expected)}")

    print("3) Live STT (WebSocket) …")
    frames = asyncio.run(stt_stream(wav))
    for f in frames:
        print("   ", json.dumps(f)[:200])
    (OUT / "stream_frames.json").write_text(json.dumps(frames, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
