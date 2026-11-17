import io
import json

import httpx
import respx
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

OLLAMA = "http://127.0.0.1:11434"
client = TestClient(app)


def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "PNG")
    return buf.getvalue()


def gif_bytes() -> bytes:
    buf = io.BytesIO()
    frames = [Image.new("P", (8, 8), c) for c in (1, 2)]
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    return buf.getvalue()


def test_avatar_defaults_upload_serve_reset():
    s = client.get("/api/avatar").json()
    assert s == {
        "custom": {"idle": False, "talking": False},
        "idle": "/avatar/idle.png",
        "talking": "/avatar/talking.gif",
    }

    r = client.post("/api/avatar/talking", files={"file": ("me.gif", gif_bytes(), "image/gif")})
    assert r.status_code == 200
    s = r.json()
    assert s["custom"]["talking"] is True and s["talking"].startswith("/avatars/talking?v=")
    served = client.get("/avatars/talking")
    assert served.status_code == 200 and served.headers["content-type"] == "image/gif"
    assert served.content[:6] == b"GIF89a"

    # Replacing with a PNG swaps the stored file type.
    client.post("/api/avatar/talking", files={"file": ("me.png", png_bytes(), "image/gif")})
    assert client.get("/avatars/talking").headers["content-type"] == "image/png"

    s = client.delete("/api/avatar/talking").json()
    assert s["custom"]["talking"] is False and s["talking"] == "/avatar/talking.gif"
    assert client.get("/avatars/talking").status_code == 404


def test_avatar_rejects_non_images_and_bad_kind():
    r = client.post("/api/avatar/idle", files={"file": ("x.png", b"<svg onload=alert(1)>", "image/png")})
    assert r.status_code == 415
    assert client.post("/api/avatar/evil", files={"file": ("x.png", png_bytes(), "image/png")}).status_code == 422
    assert client.get("/avatars/..%2Fapp.db").status_code in (404, 422)


@respx.mock
def test_warmup_loads_model():
    route = respx.post(f"{OLLAMA}/api/generate").mock(
        return_value=httpx.Response(200, json={"model": "gemma4:latest", "done": True, "load_duration": 2_500_000_000})
    )
    r = client.post("/api/warmup", json={"model": "gemma4:latest"})
    assert r.json() == {"ok": True, "model": "gemma4:latest", "load_ms": 2500}
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"model": "gemma4:latest", "keep_alive": "30m"}


@respx.mock
def test_warmup_error():
    respx.post(f"{OLLAMA}/api/generate").mock(return_value=httpx.Response(404, json={"error": "model not found"}))
    r = client.post("/api/warmup", json={"model": "nope"})
    assert r.status_code == 503 and "model not found" in r.json()["detail"]


def test_auto_stop_setting():
    assert client.get("/api/settings").json()["auto_stop_ms"] == 1500
    assert client.put("/api/settings", json={"auto_stop_ms": 0}).json()["auto_stop_ms"] == 0
    assert client.put("/api/settings", json={"auto_stop_ms": 200}).status_code == 422
    assert client.put("/api/settings", json={"auto_stop_ms": 2000}).json()["auto_stop_ms"] == 2000
    client.put("/api/settings", json={"auto_stop_ms": 1500})
