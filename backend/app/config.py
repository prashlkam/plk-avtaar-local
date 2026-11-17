"""App configuration from environment variables, with a localhost-only guard."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

ROOT_DIR = Path(__file__).resolve().parents[2]


class ConfigError(ValueError):
    pass


def ensure_local_url(name: str, url: str, allow_lan: bool = False) -> str:
    """Reject any upstream URL that is not on this machine (unless ALLOW_LAN=1)."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigError(f"{name} must be an http(s) URL, got {url!r}")
    if not allow_lan and parsed.hostname not in LOCAL_HOSTS:
        raise ConfigError(
            f"{name}={url!r} is not a localhost URL. This app runs 100% locally; "
            "set ALLOW_LAN=1 to override."
        )
    return url.rstrip("/")


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    ollama_url: str
    voicestudio_url: str
    default_model: str
    host: str
    port: int
    data_dir: Path
    frontend_dir: Path
    allow_lan: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"


def load_settings() -> Settings:
    _load_dotenv(ROOT_DIR / ".env")
    allow_lan = os.environ.get("ALLOW_LAN", "0") == "1"
    host = os.environ.get("HOST", "127.0.0.1")
    if not allow_lan and host not in LOCAL_HOSTS:
        raise ConfigError(f"HOST={host!r} must be a loopback address (set ALLOW_LAN=1 to override)")
    data_dir = Path(os.environ.get("DATA_DIR", ROOT_DIR / "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        ollama_url=ensure_local_url("OLLAMA_URL", os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"), allow_lan),
        voicestudio_url=ensure_local_url(
            "VOICESTUDIO_URL", os.environ.get("VOICESTUDIO_URL", "http://127.0.0.1:3900"), allow_lan
        ),
        default_model=os.environ.get("DEFAULT_MODEL", "gemma4:latest"),
        host=host,
        port=int(os.environ.get("PORT", "8080")),
        data_dir=data_dir,
        frontend_dir=Path(os.environ.get("FRONTEND_DIR", ROOT_DIR / "frontend" / "build")),
        allow_lan=allow_lan,
        extra={
            "tts_model": os.environ.get("DEFAULT_TTS_MODEL", "tts-1"),
            "tts_voice": os.environ.get("DEFAULT_VOICE", "alloy"),
        },
    )


settings = load_settings()
