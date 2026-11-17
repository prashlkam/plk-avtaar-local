from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..deps import db, effective_settings, ollama

router = APIRouter(prefix="/api")


class ChatCreate(BaseModel):
    title: str | None = None
    model: str | None = None


class ChatUpdate(BaseModel):
    title: str | None = None
    model: str | None = None


class SettingsUpdate(BaseModel):
    default_model: str | None = None
    system_prompt: str | None = None
    temperature: float | None = None
    tts_model: str | None = None
    tts_voice: str | None = None
    tts_speed: float | None = None
    stt_language: str | None = None
    stt_model: str | None = None
    auto_send: bool | None = None
    # Push-to-talk ends by itself after this much silence (0 = off).
    auto_stop_ms: int | None = None


class WarmupRequest(BaseModel):
    model: str | None = None


@router.post("/warmup")
async def warmup(req: WarmupRequest) -> dict:
    """Load the model into memory now so the first reply isn't slowed by loading."""
    model = req.model or effective_settings()["default_model"]
    try:
        load_ms = await ollama.warmup(model)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"Could not load {model}: {e}") from e
    return {"ok": True, "model": model, "load_ms": load_ms}


@router.get("/models")
async def models() -> dict:
    try:
        items = await ollama.list_models()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"Ollama not reachable: {e}") from e
    return {"models": items, "default": effective_settings()["default_model"]}


@router.get("/chats")
def list_chats() -> list[dict]:
    return db.list_chats()


@router.post("/chats")
def create_chat(body: ChatCreate) -> dict:
    return db.create_chat(body.title or "New chat", body.model)


@router.get("/chats/{chat_id}")
def get_chat(chat_id: str) -> dict:
    chat = db.get_chat(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    return chat


@router.patch("/chats/{chat_id}")
def update_chat(chat_id: str, body: ChatUpdate) -> dict:
    if not db.get_chat(chat_id):
        raise HTTPException(404, "Chat not found")
    db.update_chat(chat_id, title=body.title, model=body.model)
    return db.get_chat(chat_id)


@router.delete("/chats/{chat_id}")
def delete_chat(chat_id: str) -> dict:
    if not db.delete_chat(chat_id):
        raise HTTPException(404, "Chat not found")
    return {"ok": True}


@router.get("/settings")
def get_settings() -> dict:
    s = effective_settings()
    return {
        **s,
        "temperature": float(s["temperature"]),
        "tts_speed": float(s["tts_speed"]),
        "auto_send": s["auto_send"] == "1",
        "auto_stop_ms": int(s["auto_stop_ms"]),
    }


@router.put("/settings")
def put_settings(body: SettingsUpdate) -> dict:
    values = {
        k: ("1" if v else "0") if isinstance(v, bool) else str(v).strip()
        for k, v in body.model_dump().items()
        if v is not None
    }
    if "temperature" in values and not 0 <= float(values["temperature"]) <= 2:
        raise HTTPException(422, "temperature must be between 0 and 2")
    if "tts_speed" in values and not 0.25 <= float(values["tts_speed"]) <= 4:
        raise HTTPException(422, "tts_speed must be between 0.25 and 4")
    if "auto_stop_ms" in values and not (values["auto_stop_ms"] == "0" or 500 <= int(values["auto_stop_ms"]) <= 10000):
        raise HTTPException(422, "auto_stop_ms must be 0 (off) or between 500 and 10000")
    db.set_settings(values)
    return get_settings()
