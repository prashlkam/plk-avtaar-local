"""FastAPI gateway: proxies the local Ollama + VoiceStudio and serves the UI."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .deps import ollama, voicestudio
from .routes import avatar, chat, chats, health, setup, stt, tts
from .routes.stt import origin_allowed

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# Everything must come from this origin: blocks any accidental external call in the browser.
CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await ollama.aclose()
    await voicestudio.aclose()


app = FastAPI(title="Avtaar gateway", lifespan=lifespan)


UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # Block cross-site requests: another website open in the browser must not be able to
    # drive this app (e.g. start Initial setup, delete chats). Browsers always send Origin
    # on cross-origin POSTs; same-origin and non-browser clients are unaffected.
    if request.method in UNSAFE_METHODS and not origin_allowed(request.headers.get("origin")):
        return JSONResponse({"detail": "Cross-site request blocked"}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


app.include_router(health.router)
app.include_router(chats.router)
app.include_router(chat.router)
app.include_router(tts.router)
app.include_router(stt.router)
app.include_router(avatar.router)
app.include_router(setup.router)


@app.get("/api/{path:path}", include_in_schema=False)
async def api_404(path: str):
    return JSONResponse({"detail": "Not found"}, status_code=404)


# Serve the built SvelteKit app (single-page; unknown paths fall back to index.html).
if settings.frontend_dir.is_dir():
    index = settings.frontend_dir / "index.html"
    app.mount("/_app", StaticFiles(directory=settings.frontend_dir / "_app"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        candidate = (settings.frontend_dir / path).resolve()
        if path and candidate.is_file() and settings.frontend_dir.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)
else:

    @app.get("/", include_in_schema=False)
    async def no_ui():
        return JSONResponse(
            {"detail": "UI not built. Run `make build` (or use `make dev` and open http://127.0.0.1:5173)."}
        )


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
