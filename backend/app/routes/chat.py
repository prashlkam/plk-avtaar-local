"""POST /api/chat — stream an LLM reply as Server-Sent Events and persist both turns.

SSE events:
  meta   {chat_id, user_message, title}
  token  {t}
  done   {assistant_message, stats}
  error  {message}
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..deps import db, effective_settings, ollama

router = APIRouter(prefix="/api")
log = logging.getLogger("avtaar.chat")


class ChatRequest(BaseModel):
    chat_id: str | None = None
    model: str | None = None
    content: str
    # When set, delete this message and everything after it first (edit / regenerate).
    replace_from: str | None = None
    # Regenerate: do not insert a new user message, reuse the history as-is.
    regenerate: bool = False


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def make_title(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= 48 else text[:47].rstrip() + "…"


@router.post("/chat")
async def chat(req: ChatRequest):
    prefs = effective_settings()
    model = req.model or prefs["default_model"]
    content = req.content.strip()
    if not content and not req.regenerate:
        raise HTTPException(422, "Message is empty")

    chat = db.get_chat(req.chat_id) if req.chat_id else None
    if req.chat_id and not chat:
        raise HTTPException(404, "Chat not found")
    if not chat:
        chat = db.create_chat(make_title(content), model)
        chat["messages"] = []
    elif not chat["messages"]:
        db.update_chat(chat["id"], title=make_title(content))

    chat_id = chat["id"]
    if req.replace_from:
        db.delete_messages_from(chat_id, req.replace_from)
    db.update_chat(chat_id, model=model)

    user_msg = None
    if not req.regenerate:
        user_msg = db.add_message(chat_id, "user", content)

    history = db.get_chat(chat_id)["messages"]
    messages = []
    if prefs["system_prompt"].strip():
        messages.append({"role": "system", "content": prefs["system_prompt"]})
    messages += [{"role": m["role"], "content": m["content"]} for m in history if m["role"] != "system"]
    if not messages or messages[-1]["role"] != "user":
        raise HTTPException(422, "Nothing to respond to")

    options = {"temperature": float(prefs["temperature"])}
    title = db.get_chat(chat_id)["title"]

    async def gen():
        parts: list[str] = []
        stats: dict = {}
        saved = False

        def save() -> dict | None:
            nonlocal saved
            if saved or not parts:
                return None
            saved = True
            return db.add_message(chat_id, "assistant", "".join(parts), model)

        yield sse("meta", {"chat_id": chat_id, "user_message": user_msg, "title": title, "model": model})
        try:
            async for chunk in ollama.chat_stream(model, messages, options):
                piece = (chunk.get("message") or {}).get("content", "")
                if piece:
                    parts.append(piece)
                    yield sse("token", {"t": piece})
                if chunk.get("done"):
                    stats = {
                        k: chunk.get(k)
                        for k in ("total_duration", "load_duration", "eval_count", "eval_duration")
                        if k in chunk
                    }
            msg = save()
            yield sse("done", {"assistant_message": msg, "stats": stats})
        except asyncio.CancelledError:
            # Client pressed Stop / disconnected: keep the partial reply.
            save()
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("chat stream failed")
            msg = save()
            yield sse("error", {"message": str(e) or type(e).__name__, "assistant_message": msg})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
