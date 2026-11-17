import json

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

VS = "http://127.0.0.1:3900"
client = TestClient(app)


@respx.mock
def test_tts_streams_audio_with_defaults():
    route = respx.post(f"{VS}/v1/audio/speech").mock(
        return_value=httpx.Response(200, content=b"RIFF....WAVEfmt ", headers={"content-type": "audio/wav"})
    )
    r = client.post("/api/tts", json={"text": "Hello there."})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content.startswith(b"RIFF")
    sent = json.loads(route.calls.last.request.content)
    assert sent["input"] == "Hello there."
    assert sent["response_format"] == "wav"
    assert sent["model"] and sent["voice"]


@respx.mock
def test_tts_uses_saved_voice_settings():
    route = respx.post(f"{VS}/v1/audio/speech").mock(return_value=httpx.Response(200, content=b"x"))
    client.put("/api/settings", json={"tts_voice": "Aria", "tts_speed": 1.25, "tts_model": "omnivoice"})
    client.post("/api/tts", json={"text": "Hi"})
    sent = json.loads(route.calls.last.request.content)
    assert (sent["voice"], sent["speed"], sent["model"]) == ("Aria", 1.25, "omnivoice")
    # request values win over settings
    client.post("/api/tts", json={"text": "Hi", "voice": "Other"})
    assert json.loads(route.calls.last.request.content)["voice"] == "Other"


@respx.mock
def test_tts_error_is_reported():
    respx.post(f"{VS}/v1/audio/speech").mock(
        return_value=httpx.Response(409, json={"error": {"message": "ambiguous_voice"}})
    )
    r = client.post("/api/tts", json={"text": "Hi"})
    assert r.status_code == 409
    assert "ambiguous_voice" in r.json()["detail"]


@respx.mock
def test_tts_unreachable():
    respx.post(f"{VS}/v1/audio/speech").mock(side_effect=httpx.ConnectError("refused"))
    assert client.post("/api/tts", json={"text": "Hi"}).status_code == 503


def test_tts_validation():
    assert client.post("/api/tts", json={"text": ""}).status_code == 422
    assert client.post("/api/tts", json={"text": "x", "format": "exe"}).status_code == 422


@respx.mock
def test_voices_normalised():
    respx.get(f"{VS}/v1/audio/voices").mock(
        return_value=httpx.Response(
            200, json={"voices": [{"voice_id": "v1", "name": "Aria", "addressable_by_name": True}, {"id": "v2"}]}
        )
    )
    r = client.get("/api/voices").json()
    assert r["voices"][0] == {"id": "v1", "name": "Aria", "language": None}
    assert r["voices"][1]["id"] == "v2"
