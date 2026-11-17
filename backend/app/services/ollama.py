"""Async client for the local Ollama server."""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        # No read timeout on streaming: local models can be slow to load.
        self._client = httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(10.0, read=None))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def version(self) -> str:
        r = await self._client.get("/api/version", timeout=3.0)
        r.raise_for_status()
        return r.json().get("version", "?")

    async def list_models(self) -> list[dict]:
        r = await self._client.get("/api/tags", timeout=5.0)
        r.raise_for_status()
        models = r.json().get("models", [])
        # Stay 100% local: hide Ollama cloud-hosted models.
        local = [m for m in models if not m.get("name", "").endswith("-cloud") and not m.get("remote_host")]
        return [
            {
                "name": m["name"],
                "size": m.get("size"),
                "parameter_size": (m.get("details") or {}).get("parameter_size"),
                "family": (m.get("details") or {}).get("family"),
            }
            for m in local
        ]

    async def warmup(self, model: str) -> int:
        """Load `model` into memory (a generate call with no prompt). Returns load time in ms."""
        r = await self._client.post(
            "/api/generate",
            json={"model": model, "keep_alive": "30m"},
            timeout=httpx.Timeout(10.0, read=300.0),
        )
        if r.status_code != 200:
            try:
                msg = r.json().get("error", r.text)
            except ValueError:
                msg = r.text
            raise OllamaError(msg)
        return int((r.json().get("load_duration") or 0) / 1e6)

    async def pull(self, model: str, on_progress=None) -> None:
        """Download a model, calling on_progress(status, completed, total) as it goes."""
        async with self._client.stream(
            "POST", "/api/pull", json={"model": model, "stream": True}, timeout=httpx.Timeout(10.0, read=600.0)
        ) as r:
            if r.status_code != 200:
                body = (await r.aread()).decode(errors="replace")
                raise OllamaError(f"pull failed ({r.status_code}): {body[:300]}")
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if "error" in chunk:
                    raise OllamaError(chunk["error"])
                if on_progress:
                    on_progress(chunk.get("status", ""), chunk.get("completed"), chunk.get("total"))

    async def chat_once(self, model: str, prompt: str) -> dict:
        r = await self._client.post(
            "/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "keep_alive": "30m",
                "options": {"temperature": 0, "num_predict": 24},
            },
            timeout=httpx.Timeout(10.0, read=300.0),
        )
        if r.status_code != 200:
            raise OllamaError(f"chat failed ({r.status_code}): {r.text[:300]}")
        return r.json()

    async def chat_stream(
        self, model: str, messages: list[dict], options: dict | None = None
    ) -> AsyncIterator[dict]:
        """Yield Ollama NDJSON chunks for a streaming chat request."""
        payload = {"model": model, "messages": messages, "stream": True, "keep_alive": "30m"}
        if options:
            payload["options"] = options
        async with self._client.stream("POST", "/api/chat", json=payload) as r:
            if r.status_code != 200:
                body = (await r.aread()).decode(errors="replace")
                try:
                    body = json.loads(body).get("error", body)
                except ValueError:
                    pass
                raise OllamaError(f"Ollama returned {r.status_code}: {body}")
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if "error" in chunk:
                    raise OllamaError(chunk["error"])
                yield chunk
