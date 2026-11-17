"""Initial setup: install, configure and test everything the app needs.

POST /api/setup/run         start a run (or attach to the one in progress); streams SSE events
GET  /api/setup/stream      re-attach to the current run (SSE)
GET  /api/setup/status      {running, report}
GET  /api/setup/test-audio  the WAV spoken by the last TTS test
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from ..config import settings
from ..setup.runner import SetupManager, SetupRun
from ..setup.steps import build_steps

router = APIRouter(prefix="/api/setup")
manager = SetupManager(settings.data_dir / "setup_report.json", build_steps)


def sse_stream(run: SetupRun) -> StreamingResponse:
    async def gen():
        async for event, data in run.subscribe():
            yield f"event: {event}\ndata: {json.dumps(data)}\n\n"

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/run")
async def run_setup():
    run, _ = manager.start()
    return sse_stream(run)


@router.get("/stream")
async def stream_setup():
    if not manager.current:
        raise HTTPException(404, "No setup run yet")
    return sse_stream(manager.current)


@router.get("/status")
def status() -> dict:
    return {"running": manager.running, "report": manager.last_report()}


@router.get("/test-audio")
def test_audio():
    p = settings.data_dir / "setup" / "tts_test.wav"
    if not p.is_file():
        raise HTTPException(404, "No test audio yet. Run Initial setup first.")
    return FileResponse(p, media_type="audio/wav", headers={"Cache-Control": "no-store"})
