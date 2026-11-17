"""Initial setup: runner orchestration, container command, origin guard, and a full run
against the fake VoiceStudio (real server in a thread) with Ollama mocked."""

import asyncio
import dataclasses
import json
import sys
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import deps, secrets_store
from app.main import app
from app.setup import steps
from app.setup.runner import SetupManager, SetupRun, Step, fail, ok, warn

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from test_stt import fake_vs  # noqa: E402,F401  (module-scoped fixture: fake VoiceStudio server)

OLLAMA = "http://127.0.0.1:11434"
client = TestClient(app)


def parse_sse(text: str):
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


# --------------------------------------------------------------------- runner


def run_steps(step_list):
    async def go():
        run = SetupRun(step_list)
        await run.execute()
        return run

    return asyncio.run(go())


def test_runner_skips_dependents_and_survives_crashes():
    async def good(ctx):
        ctx.log("hello")
        return ok("fine")

    async def bad(ctx):
        return fail("nope", hint="do X")

    async def boom(ctx):
        raise RuntimeError("kaboom")

    async def soft(ctx):
        return warn("meh")

    run = run_steps(
        [
            Step("a", "A", good),
            Step("b", "B", bad),
            Step("c", "C", good, needs=["b"]),
            Step("d", "D", boom),
            Step("e", "E", soft),
            Step("f", "F", good, needs=["a", "e"]),  # warn counts as passing
        ]
    )
    st = {k: v.status for k, v in run.results.items()}
    assert st == {"a": "ok", "b": "fail", "c": "skip", "d": "fail", "e": "warn", "f": "ok"}
    assert "kaboom" in run.results["d"].message
    kinds = [e for e, _ in run.events]
    assert kinds[0] == "plan" and kinds[-1] == "done" and "log" in kinds
    done = run.events[-1][1]
    assert done["ok"] is False and done["counts"] == {"ok": 2, "fail": 2, "skip": 1, "warn": 1}


def test_manager_attaches_to_running_run_and_saves_report(tmp_path):
    gate = asyncio.Event()

    async def slow(ctx):
        await gate.wait()
        return ok("done")

    async def go():
        mgr = SetupManager(tmp_path / "report.json", lambda: [Step("s", "Slow", slow)])
        r1, new1 = mgr.start()
        r2, new2 = mgr.start()
        assert new1 and not new2 and r1 is r2 and mgr.running
        # a late subscriber replays everything
        gate.set()
        events = [e async for e, _ in r1.subscribe()]
        await asyncio.sleep(0.05)
        return mgr, events

    mgr, events = asyncio.run(go())
    assert events[0] == "plan" and events[-1] == "done"
    saved = json.loads((tmp_path / "report.json").read_text())
    assert saved["steps"][0]["status"] == "ok"


# --------------------------------------------------------------------- pieces


def test_container_command_is_local_only_and_keyed():
    args = steps.container_run_args("podman", "KEY123", [])
    joined = " ".join(args)
    assert "-p 127.0.0.1:3900:3900" in joined  # never exposed beyond this machine
    assert "OMNIVOICE_API_KEY=KEY123" in joined
    assert "OMNIVOICE_ANALYTICS_DISABLED=1" in joined
    assert f"{steps.VOLUME}:/app/omnivoice_data" in joined  # models survive re-runs
    assert args[-1] == steps.IMAGE
    assert "--device" not in args
    assert "nvidia.com/gpu=all" in steps.container_run_args("podman", "k", ["--device", "nvidia.com/gpu=all"])


def test_secrets_file_is_private():
    secrets_store.put("probe", "x")
    path = secrets_store._path()
    assert path.stat().st_mode & 0o777 == 0o600
    assert secrets_store.get("probe") == "x"


def test_cross_site_writes_are_blocked():
    r = client.post("/api/setup/run", headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.delete("/api/chats/x", headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    # same-origin request passes the guard (404 = reached the route)
    assert client.delete("/api/chats/x", headers={"origin": "http://127.0.0.1:8080"}).status_code == 404


# --------------------------------------------------------------------- full run


@pytest.fixture
def setup_env(fake_vs, monkeypatch, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text("<html></html>")
    monkeypatch.setattr(steps, "settings", dataclasses.replace(steps.settings, frontend_dir=ui))
    monkeypatch.setattr(deps.voicestudio, "base_url", fake_vs)
    monkeypatch.setattr(steps, "container_exists", lambda rt: asyncio.sleep(0, result=False))
    deps.db.set_settings({"default_model": "gemma4:latest", "tts_voice": "alloy", "stt_language": ""})
    return fake_vs


def mock_ollama(m, model_present=True):
    tags = {"models": [{"name": "gemma4:latest", "details": {}}]} if model_present else {"models": []}
    m.get(f"{OLLAMA}/api/version").mock(return_value=httpx.Response(200, json={"version": "0.40.16"}))
    m.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json=tags))
    m.post(f"{OLLAMA}/api/generate").mock(return_value=httpx.Response(200, json={"done": True, "load_duration": 1e9}))
    m.post(f"{OLLAMA}/api/chat").mock(
        return_value=httpx.Response(
            200, json={"message": {"content": "Ready"}, "eval_count": 5, "eval_duration": 5e8, "done": True}
        )
    )
    pull = "\n".join(
        json.dumps(x)
        for x in [
            {"status": "pulling manifest"},
            {"status": "downloading", "completed": 0, "total": 100},
            {"status": "downloading", "completed": 100, "total": 100},
            {"status": "success"},
        ]
    )
    return m.post(f"{OLLAMA}/api/pull").mock(return_value=httpx.Response(200, text=pull))


def test_full_setup_run_against_fake_voicestudio(setup_env):
    with respx.mock(assert_all_called=False) as m:
        m.route(host="127.0.0.1", port=int(setup_env.rsplit(":", 1)[1])).pass_through()
        mock_ollama(m)
        r = client.post("/api/setup/run")
    events = parse_sse(r.text)
    final = {d["id"]: d for e, d in events if e == "step" and d["status"] != "running"}
    statuses = {k: v["status"] for k, v in final.items()}
    assert statuses == {
        "app": "ok",
        "ollama-installed": "ok",
        "ollama-running": "ok",
        "ollama-model": "ok",
        "ollama-test": "ok",
        "vs-install": "ok",
        "vs-ready": "ok",
        "vs-config": "ok",
        "tts-test": "ok",
        "stt-test": "ok",
        "live-stt-test": "ok",
    }, {k: (v["status"], v["message"], v.get("hint")) for k, v in final.items() if v["status"] != "ok"}
    assert "already running" in final["vs-install"]["message"]
    assert "100%" in final["stt-test"]["message"]
    assert events[-1][0] == "done" and events[-1][1]["ok"] is True

    # status + test audio are available afterwards
    st = client.get("/api/setup/status").json()
    assert st["running"] is False and len(st["report"]["steps"]) == 11
    audio = client.get("/api/setup/test-audio")
    assert audio.status_code == 200 and audio.content[:4] == b"RIFF"


def test_setup_pulls_missing_model_and_skips_dependents_on_failure(setup_env, monkeypatch):
    monkeypatch.setattr(deps.voicestudio, "base_url", "http://127.0.0.1:1")  # VoiceStudio unreachable
    monkeypatch.setattr(steps, "native_voicestudio", lambda: None)
    monkeypatch.setattr(steps, "container_runtime", lambda: None)
    with respx.mock(assert_all_called=False) as m:
        m.route(host="127.0.0.1", port=1).pass_through()
        pull = mock_ollama(m, model_present=False)
        r = client.post("/api/setup/run")
    final = {d["id"]: d for e, d in parse_sse(r.text) if e == "step" and d["status"] != "running"}
    assert pull.called
    assert final["ollama-model"]["status"] == "ok" and "Downloaded" in final["ollama-model"]["message"]
    assert final["vs-install"]["status"] == "fail" and "yay -S voicestudio-bin" in final["vs-install"]["hint"]
    for dep in ("vs-ready", "vs-config", "tts-test", "stt-test", "live-stt-test"):
        assert final[dep]["status"] == "skip"
