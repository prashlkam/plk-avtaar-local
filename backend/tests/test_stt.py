"""STT tests: the WS proxy runs against the real fake-VoiceStudio server in a thread."""

import json
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import respx
import uvicorn
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import deps
from app.main import app
from app.routes.stt import origin_allowed

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import fake_voicestudio  # noqa: E402

client = TestClient(app)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def fake_vs():
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(fake_voicestudio.app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    t.join(timeout=5)


@pytest.fixture
def vs_url(fake_vs, monkeypatch):
    monkeypatch.setattr(deps.voicestudio, "base_url", fake_vs)
    fake_voicestudio.LOG.clear()
    return fake_vs


def test_ws_proxy_relays_partials_and_finals(vs_url):
    with client.websocket_connect("/ws/stt?language=en&evil=1") as ws:
        assert ws.receive_json()["type"] == "session.started"
        partials = []
        for _ in range(4):
            ws.send_bytes(b"\x1a\x45\xdf\xa3" + b"x" * 100)
        for _ in range(2):
            m = ws.receive_json()
            assert m["type"] == "partial"
            partials.append(m["text"])
        assert partials == ["hello", "hello avatar"]
        ws.send_text(json.dumps({"type": "input_audio.end"}))
        finals = [ws.receive_json(), ws.receive_json()]
        assert [f["final_kind"] for f in finals] == ["utterance", "summary"]
        assert finals[1]["text"] == "Hello avatar"
    entry = fake_voicestudio.LOG[-1]
    assert entry["frames"] == 4 and entry["bytes"] == 416
    # only whitelisted query params are forwarded
    assert entry["query"] == {"language": "en"}


def test_ws_proxy_reports_unavailable_upstream(monkeypatch):
    monkeypatch.setattr(deps.voicestudio, "base_url", f"http://127.0.0.1:{free_port()}")
    with client.websocket_connect("/ws/stt") as ws:
        m = ws.receive_json()
        assert m["type"] == "error" and m["code"] == "upstream_unavailable"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_ws_rejects_foreign_origin():
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/stt", headers={"origin": "https://evil.example"}) as ws:
            ws.receive_json()


@pytest.mark.parametrize(
    "origin,ok",
    [(None, True), ("http://localhost:5173", True), ("http://127.0.0.1:8080", True), ("https://evil.example", False)],
)
def test_origin_allowed(origin, ok):
    assert origin_allowed(origin) is ok


def test_batch_stt_against_fake(vs_url):
    client.put("/api/settings", json={"stt_language": "en"})
    r = client.post("/api/stt", files={"file": ("speech.webm", b"\x1a\x45\xdf\xa3" + b"0" * 2000, "audio/webm")})
    assert r.status_code == 200
    assert r.json()["text"].startswith("Hello avatar")
    entry = fake_voicestudio.LOG[-1]
    assert entry["stt_batch"] and entry["bytes"] == 2004
    assert entry["model"] == "whisper-1" and entry["language"] == "en"
    client.put("/api/settings", json={"stt_language": ""})


def test_batch_stt_validation():
    assert client.post("/api/stt", files={"file": ("a.webm", b"", "audio/webm")}).status_code == 422


@respx.mock
def test_batch_stt_unreachable():
    respx.post(f"{deps.voicestudio.base_url}/v1/audio/transcriptions").mock(side_effect=httpx.ConnectError("nope"))
    r = client.post("/api/stt", files={"file": ("a.webm", b"abc", "audio/webm")})
    assert r.status_code == 503


def test_auto_send_setting_roundtrip():
    assert client.get("/api/settings").json()["auto_send"] is True
    assert client.put("/api/settings", json={"auto_send": False}).json()["auto_send"] is False
    client.put("/api/settings", json={"auto_send": True})
