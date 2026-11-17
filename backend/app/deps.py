"""Shared singletons (created in main.lifespan)."""

from __future__ import annotations

import os

from . import secrets_store
from .config import settings
from .db import DB
from .services.ollama import OllamaClient
from .services.voicestudio import VoiceStudioClient

db = DB(settings.db_path)
ollama = OllamaClient(settings.ollama_url)
voicestudio = VoiceStudioClient(
    settings.voicestudio_url,
    api_key=os.environ.get("VOICESTUDIO_API_KEY") or secrets_store.get("voicestudio_api_key"),
)


def effective_settings() -> dict:
    """User settings from the DB, falling back to env defaults."""
    stored = db.get_settings()
    return {
        "default_model": stored.get("default_model", settings.default_model),
        "system_prompt": stored.get(
            "system_prompt",
            "You are Avtaar, a friendly, helpful AI companion running fully on the user's own computer. "
            "Keep answers concise and conversational, since they are also spoken aloud.",
        ),
        "temperature": stored.get("temperature", "0.7"),
        # VoiceStudio maps OpenAI ids ("tts-1", "alloy") to the active engine / its default voice.
        "tts_model": stored.get("tts_model", settings.extra.get("tts_model", "tts-1")),
        "tts_voice": stored.get("tts_voice", settings.extra.get("tts_voice", "alloy")),
        "tts_speed": stored.get("tts_speed", "1.0"),
        # Speech-to-text: "" = auto-detect language; "whisper-1" maps to VoiceStudio's active ASR engine.
        "stt_language": stored.get("stt_language", ""),
        "stt_model": stored.get("stt_model", "whisper-1"),
        "auto_send": stored.get("auto_send", "1"),
        "auto_stop_ms": stored.get("auto_stop_ms", "1500"),
    }
