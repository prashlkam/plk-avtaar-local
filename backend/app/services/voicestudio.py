"""Async client for the local VoiceStudio server (STT/TTS).

API reference (VoiceStudio docs/agentic-voice.md, docs/speech-platform.md):
  GET  /.well-known/voicestudio-speech      discovery
  GET  /v1/audio/voices                     voice list
  POST /v1/audio/speech                     TTS (OpenAI-compatible)
  POST /v1/audio/transcriptions             batch STT (OpenAI-compatible)
  WS   /v1/audio/transcriptions/stream      live STT
"""

from __future__ import annotations

import httpx


class VoiceStudioError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


AUDIO_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "pcm": "audio/pcm",
}


class VoiceStudioClient:
    def __init__(self, base_url: str, api_key: str | None = None):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(10.0, read=None))
        self.base_url = base_url
        self.api_key = api_key

    @property
    def api_key(self) -> str | None:
        return self._api_key

    @api_key.setter
    def api_key(self, key: str | None) -> None:
        """VoiceStudio in a container needs `Authorization: Bearer <key>` even from localhost."""
        self._api_key = key or None
        if self._api_key:
            self._client.headers["Authorization"] = f"Bearer {self._api_key}"
        else:
            self._client.headers.pop("Authorization", None)

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

    async def health(self) -> tuple[int, dict]:
        """GET /health -> (status, json). 503 while starting up; falls back to discovery if absent."""
        r = await self._client.get("/health", timeout=5.0)
        if r.status_code == 404:
            r = await self._client.get("/.well-known/voicestudio-speech", timeout=5.0)
        try:
            body = r.json()
        except ValueError:
            body = {}
        return r.status_code, body if isinstance(body, dict) else {}

    @property
    def base_url(self) -> str:
        return self._base_url

    @base_url.setter
    def base_url(self, url: str) -> None:
        self._base_url = url.rstrip("/")
        self._client.base_url = self._base_url

    async def aclose(self) -> None:
        await self._client.aclose()

    async def discovery(self) -> dict:
        r = await self._client.get("/.well-known/voicestudio-speech", timeout=3.0)
        r.raise_for_status()
        return r.json()

    async def voices(self) -> list[dict]:
        r = await self._client.get("/v1/audio/voices", timeout=5.0)
        r.raise_for_status()
        data = r.json()
        items = data
        if isinstance(data, dict):
            items = data.get("voices") or data.get("data") or []
        out = []
        for v in items:
            if isinstance(v, str):
                out.append({"id": v, "name": v})
                continue
            vid = v.get("voice_id") or v.get("id") or v.get("name")
            if vid:
                out.append({"id": vid, "name": v.get("name") or vid, "language": v.get("language")})
        return out

    @property
    def stream_url(self) -> str:
        """WebSocket URL for live transcription."""
        return self.base_url.replace("http", "ws", 1) + "/v1/audio/transcriptions/stream"

    async def transcribe(
        self, audio: bytes, filename: str, content_type: str, model: str, language: str | None = None
    ) -> dict:
        data = {"model": model}
        if language:
            data["language"] = language
        r = await self._client.post(
            "/v1/audio/transcriptions",
            data=data,
            files={"file": (filename, audio, content_type)},
            timeout=httpx.Timeout(10.0, read=300.0),
        )
        if r.status_code != 200:
            raise VoiceStudioError(r.status_code, f"VoiceStudio STT failed ({r.status_code}): {r.text[:300]}")
        if r.headers.get("content-type", "").startswith("application/json"):
            return r.json()
        return {"text": r.text}

    async def speech(self, payload: dict) -> httpx.Response:
        """Start a TTS request; returns an open streaming response (caller must aclose()).

        Raises VoiceStudioError for non-200 responses.
        """
        req = self._client.build_request("POST", "/v1/audio/speech", json=payload)
        resp = await self._client.send(req, stream=True)
        if resp.status_code != 200:
            body = (await resp.aread()).decode(errors="replace")
            await resp.aclose()
            try:
                import json

                parsed = json.loads(body)
                err = parsed.get("error", parsed)
                body = err.get("message", err) if isinstance(err, dict) else err
                body = body if isinstance(body, str) else json.dumps(body)
            except ValueError:
                pass
            raise VoiceStudioError(resp.status_code, f"VoiceStudio TTS failed ({resp.status_code}): {body[:300]}")
        return resp
