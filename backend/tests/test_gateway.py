import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import ConfigError, ensure_local_url
from app.main import app

OLLAMA = "http://127.0.0.1:11434"
client = TestClient(app)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


@pytest.mark.parametrize("url", ["http://localhost:11434", "http://127.0.0.1:3900/", "http://[::1]:3900"])
def test_local_urls_allowed(url):
    assert ensure_local_url("X", url) == url.rstrip("/")


@pytest.mark.parametrize("url", ["http://example.com", "http://192.168.1.5:11434", "ftp://localhost"])
def test_remote_urls_rejected(url):
    with pytest.raises(ConfigError):
        ensure_local_url("X", url)


def test_remote_url_allowed_with_override():
    assert ensure_local_url("X", "http://192.168.1.5:11434", allow_lan=True)


@respx.mock
def test_models_hides_cloud_models():
    respx.get(f"{OLLAMA}/api/tags").mock(
        return_value=httpx.Response(
            200,
            json={"models": [{"name": "gemma4:latest", "details": {}}, {"name": "gpt-oss:120b-cloud", "details": {}}]},
        )
    )
    r = client.get("/api/models")
    assert r.status_code == 200
    assert [m["name"] for m in r.json()["models"]] == ["gemma4:latest"]


@respx.mock
def test_chat_streams_and_persists():
    ndjson = "\n".join(
        json.dumps(c)
        for c in [
            {"message": {"role": "assistant", "content": "Hello"}, "done": False},
            {"message": {"role": "assistant", "content": " there!"}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True, "eval_count": 2},
        ]
    )
    route = respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, text=ndjson))

    r = client.post("/api/chat", json={"content": "Hi Avtaar", "model": "gemma4:latest"})
    assert r.status_code == 200
    events = parse_sse(r.text)
    kinds = [e[0] for e in events]
    assert kinds == ["meta", "token", "token", "done"]
    chat_id = events[0][1]["chat_id"]
    assert events[0][1]["title"] == "Hi Avtaar"

    sent = json.loads(route.calls.last.request.content)
    assert sent["stream"] is True
    assert sent["messages"][0]["role"] == "system"
    assert sent["messages"][-1] == {"role": "user", "content": "Hi Avtaar"}

    chat = client.get(f"/api/chats/{chat_id}").json()
    assert [(m["role"], m["content"]) for m in chat["messages"]] == [
        ("user", "Hi Avtaar"),
        ("assistant", "Hello there!"),
    ]

    # Regenerate: drop the assistant reply and stream a new one without a new user message.
    assistant_id = chat["messages"][1]["id"]
    r = client.post(
        "/api/chat", json={"chat_id": chat_id, "content": "", "regenerate": True, "replace_from": assistant_id}
    )
    assert [e[0] for e in parse_sse(r.text)] == ["meta", "token", "token", "done"]
    chat = client.get(f"/api/chats/{chat_id}").json()
    assert [m["role"] for m in chat["messages"]] == ["user", "assistant"]

    assert client.delete(f"/api/chats/{chat_id}").json() == {"ok": True}
    assert client.get(f"/api/chats/{chat_id}").status_code == 404


@respx.mock
def test_chat_reports_ollama_error():
    respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(404, json={"error": "model 'nope' not found"}))
    r = client.post("/api/chat", json={"content": "hi", "model": "nope"})
    events = parse_sse(r.text)
    assert events[-1][0] == "error"
    assert "not found" in events[-1][1]["message"]


def test_settings_roundtrip():
    r = client.put("/api/settings", json={"system_prompt": "Be brief.", "temperature": 0.2})
    assert r.json()["system_prompt"] == "Be brief."
    assert r.json()["temperature"] == 0.2
    assert client.put("/api/settings", json={"temperature": 5}).status_code == 422


def test_csp_header():
    r = client.get("/api/settings")
    assert "default-src 'self'" in r.headers["content-security-policy"]
