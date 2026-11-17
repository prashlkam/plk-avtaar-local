"""The Initial-setup steps. Each one: check -> install/start if needed -> configure -> test.

Running setup again re-applies configuration and re-runs every test. A VoiceStudio
container created by setup is recreated so it always matches the current settings
(its data volume, with downloaded speech models, is kept).
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import secrets
import shutil
import time
import wave
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx
from websockets.asyncio.client import connect as ws_connect

from .. import secrets_store
from ..config import ROOT_DIR, settings
from ..deps import db, effective_settings, ollama, voicestudio
from .procs import run_cmd, spawn_detached
from .runner import Step, StepContext, StepResult, fail, ok, skip, warn

CONTAINER = "avtaar-voicestudio"
VOLUME = "avtaar-voicestudio-data"
IMAGE = os.environ.get("VOICESTUDIO_IMAGE", "ghcr.io/debpalash/voicestudio:stable")
LOG_DIR = settings.data_dir / "logs"
TEST_PHRASE = "Hello! Your local avatar is ready to talk."
MODEL_RE = re.compile(r"^[\w.\-/:]{1,200}$")


# --------------------------------------------------------------------------- helpers


def words(s: str) -> set[str]:
    return set(re.findall(r"[a-z']+", s.lower()))


def vs_port() -> int:
    return urlparse(settings.voicestudio_url).port or 3900


def container_runtime() -> str | None:
    for rt in ("podman", "docker"):
        if shutil.which(rt):
            return rt
    return None


def nvidia_container_args(runtime: str) -> list[str]:
    """GPU flags if the NVIDIA container toolkit is set up, else [] (CPU)."""
    if runtime == "podman":
        for p in ("/etc/cdi/nvidia.yaml", "/var/run/cdi/nvidia.yaml", "/etc/cdi/nvidia.json"):
            if Path(p).is_file():
                return ["--device", "nvidia.com/gpu=all"]
        return []
    if shutil.which("nvidia-ctk") or shutil.which("nvidia-container-runtime"):
        return ["--gpus", "all"]
    return []


def asr_model_for(gpu_args: list[str]) -> str:
    """Speech-to-text model to pin in the container: VoiceStudio's own CPU pick
    (Whisper small, 0.5 GB) without a GPU, large-v3-turbo with one."""
    override = os.environ.get("AVTAAR_ASR_MODEL")
    if override:
        return override
    return "deepdml/faster-whisper-large-v3-turbo-ct2" if gpu_args else "Systran/faster-whisper-small"


def container_run_args(runtime: str, api_key: str, gpu_args: list[str]) -> list[str]:
    return [
        runtime, "run", "-d",
        "--name", CONTAINER,
        "--restart", "unless-stopped",
        "-p", f"127.0.0.1:{vs_port()}:3900",
        "-e", f"OMNIVOICE_API_KEY={api_key}",
        "-e", "OMNIVOICE_DATA_DIR=/app/omnivoice_data",
        "-e", "OMNIVOICE_ANALYTICS_DISABLED=1",
        # VoiceStudio's default ASR is Whisper large-v3 (3 GB, slow on CPU); pin a fitting one.
        # The engine must be pinned too: auto-detect picks WhisperX, which ignores ASR_MODEL_FASTER.
        "-e", "OMNIVOICE_ASR_BACKEND=faster-whisper",
        "-e", f"ASR_MODEL_FASTER={asr_model_for(gpu_args)}",
        "-v", f"{VOLUME}:/app/omnivoice_data",
        *gpu_args,
        IMAGE,
    ]  # fmt: skip


async def container_exists(runtime: str) -> bool:
    return (await run_cmd([runtime, "container", "inspect", CONTAINER], timeout=20)).ok


def native_voicestudio() -> str | None:
    for cand in ("voicestudio", str(Path.home() / ".local/bin/voicestudio"), str(Path.home() / ".local/bin/VoiceStudio")):
        if shutil.which(cand) or Path(cand).is_file():
            return cand
    return None


async def vs_reachable() -> bool:
    try:
        status, _ = await voicestudio.health()
        return status in (200, 503)
    except httpx.HTTPError:
        return False


async def with_heartbeat(ctx: StepContext, coro, every: float, message: str, timeout: float):
    """Await `coro`, posting `message` (with elapsed time) every `every` seconds."""
    task = asyncio.ensure_future(coro)
    start = time.monotonic()
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=every)
            if done:
                return task.result()
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                task.cancel()
                raise asyncio.TimeoutError
            ctx.progress(f"{message} ({int(elapsed)} s)")
    finally:
        if not task.done():
            task.cancel()


# --------------------------------------------------------------------------- app


async def step_app(ctx: StepContext) -> StepResult:
    probe = settings.data_dir / ".write-test"
    try:
        probe.write_text("ok")
        probe.unlink()
    except OSError as e:
        return fail(f"Data folder {settings.data_dir} is not writable: {e}")
    (settings.data_dir / "logs").mkdir(exist_ok=True)
    notes = []
    if not (settings.frontend_dir / "index.html").is_file():
        if shutil.which("npm"):
            ctx.progress("Building the user interface…")
            r = await run_cmd(["npm", "--prefix", str(ROOT_DIR / "frontend"), "run", "build"], timeout=600, on_line=ctx.log)
            if not r.ok:
                return fail("Building the UI failed.", hint=r.tail())
            notes.append("built the UI")
        else:
            return fail("The UI is not built and npm is missing.", hint="Install Node.js, then run: make build")
    db.get_settings()  # database opens
    return ok("App files, database and data folder are fine" + (f" ({', '.join(notes)})." if notes else "."))


# --------------------------------------------------------------------------- Ollama


async def step_ollama_installed(ctx: StepContext) -> StepResult:
    path = shutil.which("ollama")
    try:
        version = await ollama.version()
        return ok(f"Ollama {version} is installed" + (f" ({path})." if path else " (reached over the network)."))
    except httpx.HTTPError:
        pass
    if path:
        r = await run_cmd(["ollama", "--version"], timeout=15)
        return ok(f"Ollama is installed: {r.tail(1) or path}.")
    return fail(
        "Ollama is not installed.",
        hint="Installing it needs administrator rights. On Arch: sudo pacman -S ollama (or ollama-cuda for NVIDIA), "
        "then sudo systemctl enable --now ollama. Other systems: see https://ollama.com/download. "
        "Then run Initial setup again.",
    )


async def _wait_ollama(seconds: float) -> str | None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            return await ollama.version()
        except httpx.HTTPError:
            await asyncio.sleep(1)
    return None


async def step_ollama_running(ctx: StepContext) -> StepResult:
    try:
        return ok(f"Ollama is running at {settings.ollama_url} (v{await ollama.version()}).")
    except httpx.HTTPError:
        pass
    # 1) The system service (works without a password only if polkit allows it).
    if shutil.which("systemctl"):
        ctx.progress("Starting the Ollama service…")
        r = await run_cmd(["systemctl", "--no-ask-password", "start", "ollama"], timeout=30)
        ctx.log(r.output)
        if r.ok and (v := await _wait_ollama(20)):
            return ok(f"Started the Ollama service (v{v}).")
    # 2) A user-level server.
    if shutil.which("ollama"):
        host = urlparse(settings.ollama_url)
        ctx.progress("Starting `ollama serve` for this user…")
        spawn_detached(
            ["ollama", "serve"], LOG_DIR / "ollama.log", env={"OLLAMA_HOST": f"{host.hostname}:{host.port or 11434}"}
        )
        if v := await _wait_ollama(30):
            return warn(
                f"Started `ollama serve` as your user (v{v}).",
                hint="It stops when you log out. To start it at boot: sudo systemctl enable --now ollama. "
                "Note: the system service and a user server keep models in different folders.",
            )
    return fail(
        f"Could not start Ollama at {settings.ollama_url}.",
        hint="Start it yourself: sudo systemctl start ollama (or run: ollama serve). "
        f"Log: {LOG_DIR / 'ollama.log'}",
    )


async def step_ollama_model(ctx: StepContext) -> StepResult:
    prefs = effective_settings()
    model = prefs["default_model"]
    if not MODEL_RE.match(model):
        return fail(f"The configured model name {model!r} is not valid.", hint="Pick a model in Settings.")
    names = [m["name"] for m in await ollama.list_models()]
    if model in names or f"{model}:latest" in names:
        return ok(f"Model {model} is installed ({len(names)} local models in total).")

    ctx.progress(f"Downloading {model}…")
    last = {"pct": -10, "status": ""}

    def on_progress(status: str, completed, total):
        if total and completed is not None:
            pct = int(completed * 100 / total)
            if pct >= last["pct"] + 5:
                last["pct"] = pct
                ctx.progress(f"Downloading {model}: {pct}% of {total / 1e9:.1f} GB")
        elif status and status != last["status"]:
            last["status"] = status
            ctx.log(status)

    try:
        await ollama.pull(model, on_progress)
    except Exception as e:  # noqa: BLE001
        if names:
            return fail(
                f"Could not download {model}: {e}",
                hint=f"Pick one of your installed models in Settings ({', '.join(names[:4])}), or check your internet connection.",
            )
        return fail(f"Could not download {model}: {e}", hint="Check your internet connection and run setup again.")
    db.set_settings({"default_model": model})
    return ok(f"Downloaded {model} and set it as the default model.")


async def step_ollama_test(ctx: StepContext) -> StepResult:
    model = effective_settings()["default_model"]
    ctx.progress(f"Loading {model} into memory…")
    try:
        load_ms = await ollama.warmup(model)
        ctx.progress(f"Asking {model} a test question…")
        res = await ollama.chat_once(model, "Reply with exactly one word: ready")
    except Exception as e:  # noqa: BLE001
        return fail(f"{model} did not answer: {e}", hint="Check `ollama ps` and the Ollama logs (journalctl -u ollama).")
    reply = (res.get("message") or {}).get("content", "").strip()
    if not reply:
        return fail(f"{model} returned an empty reply.", hint="Try another model in Settings.")
    tps = ""
    if res.get("eval_count") and res.get("eval_duration"):
        tps = f", {res['eval_count'] / (res['eval_duration'] / 1e9):.1f} tokens/s"
    return ok(f"{model} answered “{reply[:40]}” (load {load_ms / 1000:.1f} s{tps}).")


# --------------------------------------------------------------------------- VoiceStudio


async def step_vs_install(ctx: StepContext) -> StepResult:
    runtime = container_runtime()
    ours = bool(runtime) and await container_exists(runtime)  # type: ignore[arg-type]

    # Someone else's VoiceStudio is already serving: use it as-is.
    if not ours and await vs_reachable():
        ctx.state["vs_mode"] = "external"
        return ok(f"VoiceStudio is already running at {settings.voicestudio_url}; using it.")

    # Native desktop install: launch it (it starts its backend on :3900).
    native = native_voicestudio()
    if not ours and native:
        ctx.progress("Launching the installed VoiceStudio app…")
        spawn_detached([native], LOG_DIR / "voicestudio.log")
        ctx.state["vs_mode"] = "native"
        return ok(f"Launched the installed VoiceStudio app ({native}).")

    if not runtime:
        return fail(
            "VoiceStudio is not installed, and Podman or Docker is not available to install it automatically.",
            hint="Either install Podman (sudo pacman -S podman) and run setup again, or install VoiceStudio "
            "yourself: yay -S voicestudio-bin.",
        )

    # Container install (rootless with Podman, no sudo needed). Re-runs recreate it.
    api_key = secrets_store.get("voicestudio_api_key") or secrets.token_urlsafe(32)
    secrets_store.put("voicestudio_api_key", api_key)

    ctx.progress(f"Downloading the VoiceStudio image with {runtime} (several GB the first time)…")
    last = {"t": 0.0}

    def on_line(line: str):
        now = time.monotonic()
        if now - last["t"] > 3:
            last["t"] = now
            ctx.progress(f"Downloading VoiceStudio image: {line[:120]}")
        ctx.log(line)

    # Multi-GB image on possibly slow links: allow hours, but give up if nothing happens for 15 min.
    pull = await run_cmd([runtime, "pull", IMAGE], timeout=6 * 3600, idle_timeout=900, on_line=on_line)
    if not pull.ok:
        if not ours:
            return fail(f"Could not download {IMAGE}.", hint=pull.tail())
        ctx.log("Pull failed; reusing the image already on this machine.")

    if ours:
        ctx.progress("Recreating the VoiceStudio container with the current settings…")
        await run_cmd([runtime, "rm", "-f", CONTAINER], timeout=120, on_line=ctx.log)

    gpu = nvidia_container_args(runtime)
    r = await run_cmd(container_run_args(runtime, api_key, gpu), timeout=180, on_line=ctx.log)
    if not r.ok:
        hint = r.tail()
        if "address already in use" in r.output:
            hint = f"Port {vs_port()} is in use by another program. Stop it, or change VOICESTUDIO_URL in .env."
        return fail("Could not start the VoiceStudio container.", hint=hint)

    voicestudio.api_key = api_key
    ctx.state["vs_mode"] = "container"
    ctx.state["vs_runtime"] = runtime
    where = "on the GPU" if gpu else "on the CPU"
    msg = f"{'Recreated' if ours else 'Installed'} VoiceStudio as the {runtime} container “{CONTAINER}”, running {where}."
    if not gpu:
        return warn(
            msg,
            hint="Speech will be slower on the CPU. For GPU speed, install the NVIDIA Container Toolkit "
            "(sudo pacman -S nvidia-container-toolkit; sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml) "
            "and run setup again.",
        )
    return ok(msg)


async def step_vs_ready(ctx: StepContext) -> StepResult:
    timeout = 900 if ctx.state.get("vs_mode") in ("container", "native") else 30
    deadline = time.monotonic() + timeout
    last_msg = ""
    while time.monotonic() < deadline:
        try:
            status, body = await voicestudio.health()
        except httpx.HTTPError:
            status, body = 0, {}
        if status == 200:
            device = body.get("device")
            engine = body.get("engine")
            extra = ", ".join(x for x in (f"device {device}" if device else "", f"engine {engine}" if engine else "") if x)
            return ok(f"VoiceStudio is up at {settings.voicestudio_url}" + (f" ({extra})." if extra else "."))
        if status in (401, 403):
            return fail(
                "VoiceStudio refused the connection (API key).",
                hint="Set VOICESTUDIO_API_KEY in .env to VoiceStudio's key, or let setup install its own container.",
            )
        msg = body.get("step") or body.get("message") or body.get("status") or ("starting…" if status else "waiting for it to start…")
        if msg != last_msg:
            last_msg = str(msg)
            ctx.progress(f"VoiceStudio: {msg}")
        await asyncio.sleep(3)
    hint = f"Check its log: {CONTAINER} → `{ctx.state.get('vs_runtime', 'podman')} logs {CONTAINER}`" if ctx.state.get(
        "vs_mode"
    ) == "container" else "Start VoiceStudio and run setup again."
    return fail(f"VoiceStudio did not become ready within {timeout // 60 or 1} min.", hint=hint)


async def step_vs_config(ctx: StepContext) -> StepResult:
    prefs = effective_settings()
    notes = []
    try:
        voices = await voicestudio.voices()
    except Exception as e:  # noqa: BLE001
        voices = []
        notes.append(f"could not list voices ({e})")
    ids = {v["id"] for v in voices} | {v["name"] for v in voices}
    voice = prefs["tts_voice"]
    if voices and voice not in ids and voice not in {"alloy", "ash", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer"}:
        db.set_settings({"tts_voice": "alloy"})
        notes.append(f"voice “{voice}” no longer exists, so it was reset to the default")
    ctx.state["voices"] = len(voices)
    auth = "with an API key" if voicestudio.api_key else "without an API key (local)"
    msg = f"Connected {auth}; {len(voices)} voices available."
    return warn(msg + " " + "; ".join(notes).capitalize() + ".") if notes else ok(msg)


def silent_wav(seconds: float = 1.0, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


async def probe_asr() -> tuple[int, dict]:
    """Transcribe one second of silence. Returns (status, json). A 409 carries
    VoiceStudio's `missing_repo_id` when no speech-to-text model is installed."""
    prefs = effective_settings()
    data = {"model": prefs["stt_model"]}
    r = await voicestudio._client.post(
        "/v1/audio/transcriptions",
        data=data,
        files={"file": ("probe.wav", silent_wav(), "audio/wav")},
        timeout=httpx.Timeout(10.0, read=600.0),
    )
    try:
        body = r.json()
    except ValueError:
        body = {}
    return r.status_code, body if isinstance(body, dict) else {}


def missing_asr_repo(body: dict) -> str | None:
    """Find VoiceStudio's ASR_MODEL_MISSING payload wherever it nests it."""
    stack = [body]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            repo = cur.get("missing_repo_id")
            if isinstance(repo, str) and "/" in repo:
                return repo
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


async def step_asr_model(ctx: StepContext) -> StepResult:
    ctx.progress("Checking for a speech-to-text model…")
    try:
        status, body = await with_heartbeat(ctx, probe_asr(), 10, "Loading the speech-to-text model", 900)
    except Exception as e:  # noqa: BLE001
        return fail(f"Could not reach VoiceStudio's speech-to-text: {e or type(e).__name__}")
    if status == 200:
        return ok("A speech-to-text model is installed and loads.")
    repo = missing_asr_repo(body) if status == 409 else None
    if not repo:
        return fail(
            f"Speech-to-text check failed (HTTP {status}): {json.dumps(body)[:200]}",
            hint=f"Open VoiceStudio at {settings.voicestudio_url} → Model Catalogue and install a speech-to-text model.",
        )

    ctx.progress(f"Installing the speech-to-text model {repo}…")
    r = await voicestudio._client.post("/models/install", json={"repo_id": repo}, timeout=httpx.Timeout(10.0, read=3600.0))
    if r.status_code >= 400:
        return fail(
            f"VoiceStudio refused to install {repo} (HTTP {r.status_code}): {r.text[:200]}",
            hint=f"Install it from VoiceStudio's Model Catalogue at {settings.voicestudio_url}.",
        )
    # The install may finish in the request or continue in the background: wait until ASR works.
    deadline = time.monotonic() + 3600
    start = time.monotonic()
    while time.monotonic() < deadline:
        try:
            status, body = await probe_asr()
        except httpx.HTTPError:
            status, body = 0, {}
        if status == 200:
            return ok(f"Installed {repo} ({int(time.monotonic() - start)} s) and it transcribes.")
        if status not in (0, 409, 503):
            return fail(f"Speech-to-text still failing after installing {repo} (HTTP {status}).", hint=json.dumps(body)[:300])
        ctx.progress(f"Downloading {repo}… ({int(time.monotonic() - start)} s)")
        await asyncio.sleep(10)
    return fail(f"{repo} did not finish installing within 60 min.", hint="Check VoiceStudio's Model Catalogue for progress.")


async def step_tts_test(ctx: StepContext) -> StepResult:
    prefs = effective_settings()
    payload = {
        "model": prefs["tts_model"],
        "voice": prefs["tts_voice"],
        "input": TEST_PHRASE,
        "speed": float(prefs["tts_speed"]),
        "response_format": "wav",
    }

    async def synth() -> bytes:
        resp = await voicestudio.speech(payload)
        try:
            return await resp.aread()
        finally:
            await resp.aclose()

    started = time.monotonic()
    try:
        audio = await with_heartbeat(
            ctx, synth(), 10, "Synthesising a test phrase (the first time can download speech models, ~2.4 GB)", 1800
        )
    except asyncio.TimeoutError:
        return fail("Text-to-speech did not finish within 30 min.", hint="Check VoiceStudio's Model Catalogue and logs.")
    except Exception as e:  # noqa: BLE001
        return fail(
            f"Text-to-speech failed: {e}",
            hint=f"Open VoiceStudio at {settings.voicestudio_url} → Model Catalogue and install a TTS engine, "
            "or pick another voice/engine in Settings.",
        )
    secs = time.monotonic() - started
    if len(audio) < 2000 or audio[:4] != b"RIFF":
        return fail(f"Text-to-speech returned no usable audio ({len(audio)} bytes).")
    try:
        with wave.open(io.BytesIO(audio)) as w:
            duration = w.getnframes() / w.getframerate()
    except wave.Error:
        duration = 0
    (settings.data_dir / "setup").mkdir(exist_ok=True)
    (settings.data_dir / "setup" / "tts_test.wav").write_bytes(audio)
    ctx.state["tts_wav"] = audio
    rtf = f", {duration / secs:.1f}× real time" if duration and secs else ""
    return ok(f"Spoke the test phrase: {duration:.1f} s of audio in {secs:.1f} s{rtf}.")


async def step_stt_test(ctx: StepContext) -> StepResult:
    prefs = effective_settings()
    audio = ctx.state["tts_wav"]

    async def transcribe():
        return await voicestudio.transcribe(audio, "setup.wav", "audio/wav", prefs["stt_model"], prefs["stt_language"] or None)

    try:
        res = await with_heartbeat(ctx, transcribe(), 10, "Transcribing the test phrase (first use may download a model)", 1800)
    except Exception as e:  # noqa: BLE001
        return fail(
            f"Speech-to-text failed: {e or type(e).__name__}",
            hint=f"Open VoiceStudio at {settings.voicestudio_url} → Model Catalogue and install a speech-to-text (ASR) model.",
        )
    text = (res.get("text") or "").strip()
    expected = words(TEST_PHRASE)
    score = len(expected & words(text)) / len(expected)
    if not text:
        return fail("Speech-to-text returned nothing for the test phrase.", hint="Install or switch the ASR model in VoiceStudio.")
    if score < 0.5:
        return warn(
            f"Speech-to-text heard “{text[:80]}” ({int(score * 100)}% of words matched).",
            hint="Recognition looks weak. Try a larger ASR model in VoiceStudio, or set the spoken language in Settings.",
        )
    return ok(f"Speech-to-text heard “{text[:80]}” ({int(score * 100)}% of words matched).")


async def step_live_stt_test(ctx: StepContext) -> StepResult:
    audio = ctx.state["tts_wav"]
    with wave.open(io.BytesIO(audio)) as w:
        sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        pcm = w.readframes(w.getnframes())
    if ch != 1 or width != 2:
        return skip(f"Test audio is {ch}-channel/{width * 8}-bit; the live check needs 16-bit mono.")
    params = {"pcm": "1", "sr": str(sr)}
    lang = effective_settings()["stt_language"]
    if lang:
        params["language"] = lang
    url = voicestudio.stream_url + "?" + urlencode(params)
    frames: list[dict] = []

    async def run():
        async with ws_connect(url, max_size=None, open_timeout=10, additional_headers=voicestudio.auth_headers) as ws:
            chunk = sr * 2 // 5  # 200 ms
            for i in range(0, len(pcm), chunk):
                await ws.send(pcm[i : i + chunk])
                await asyncio.sleep(0.02)
            await ws.send(json.dumps({"type": "input_audio.end"}))
            async for msg in ws:
                if isinstance(msg, bytes):
                    continue
                f = json.loads(msg)
                frames.append(f)
                if f.get("type") == "final" and f.get("final_kind", "summary") == "summary":
                    return
                if f.get("type") == "error":
                    return

    try:
        await with_heartbeat(ctx, run(), 10, "Testing live transcription", 300)
    except Exception as e:  # noqa: BLE001
        return warn(
            f"Live transcription is not available ({e or type(e).__name__}).",
            hint="Push-to-talk will still work: your words appear when you click Done instead of while you speak. "
            "For live text, install a streaming ASR model in VoiceStudio.",
        )
    kinds = [f.get("type") for f in frames]
    final = next((f.get("text", "") for f in reversed(frames) if f.get("type") == "final"), "")
    if "error" in kinds or not final:
        return warn(
            "Live transcription answered but returned no final text.",
            hint="Push-to-talk will fall back to transcribing when you click Done.",
            detail={"frames": frames[-5:]},
        )
    partials = kinds.count("partial")
    return ok(f"Live transcription works ({partials} live updates, final: “{final[:60]}”).")


# --------------------------------------------------------------------------- plan


def build_steps() -> list[Step]:
    return [
        Step("app", "App files and data folder", step_app),
        Step("ollama-installed", "Ollama installed", step_ollama_installed),
        Step("ollama-running", "Ollama running", step_ollama_running, needs=["ollama-installed"]),
        Step("ollama-model", "Language model downloaded", step_ollama_model, needs=["ollama-running"]),
        Step("ollama-test", "Language model answers", step_ollama_test, needs=["ollama-model"]),
        Step("vs-install", "VoiceStudio installed", step_vs_install),
        Step("vs-ready", "VoiceStudio running", step_vs_ready, needs=["vs-install"]),
        Step("vs-config", "VoiceStudio connected", step_vs_config, needs=["vs-ready"]),
        Step("asr-model", "Speech-to-text model installed", step_asr_model, needs=["vs-config"]),
        Step("tts-test", "Text-to-speech test", step_tts_test, needs=["vs-config"]),
        Step("stt-test", "Speech-to-text test", step_stt_test, needs=["tts-test", "asr-model"]),
        Step("live-stt-test", "Live transcription test", step_live_stt_test, needs=["tts-test", "asr-model"]),
    ]


