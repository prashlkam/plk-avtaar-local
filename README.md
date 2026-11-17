# Avtaar (local)

A local AI avatar you can talk to. Avtaar has an open-webui-style chat interface plus an animated avatar that speaks its replies and listens when you click **Talk**. **Everything runs on your own computer**: the language model in [Ollama](https://ollama.com), and speech-to-text and text-to-speech in [VoiceStudio](https://github.com/debpalash/VoiceStudio).

- 📖 **[User Guide](docs/USER_GUIDE.md)**: how to install and use every feature, plus troubleshooting
- 🧭 **[Plan.md](Plan.md)**: design, implementation status and lessons learned

## Status

| | |
|---|---|
| Text chat (streaming, Markdown, history) | ✅ Tested with the real Ollama |
| Spoken replies + animated avatar | ✅ Tested end to end with the real VoiceStudio 0.5.8 |
| Push-to-talk (live text, auto-send, auto-stop, barge-in) | ✅ Tested with a synthetic mic · ⚠️ not yet tried with a real microphone |
| Avatar mode, custom avatars, health banners, mobile layout | ✅ |
| **Initial setup** (installs, configures and tests everything) | ✅ Tested with real runs on Arch Linux + Podman |
| Desktop launcher, compose file, screenshots | ⏳ To do |

> **Speed note:** on a laptop whose GPU can't be used by containers, VoiceStudio runs on the CPU. The first spoken words then arrive about 10–20 s after you send, with pauses between sentences. Text replies are not affected. See [Making it faster](docs/USER_GUIDE.md#making-it-faster).

## Requirements

| | Needed for | Notes |
|---|---|---|
| Linux (tested: Arch) | everything | macOS/Windows untested |
| Python 3.11+ and Node 20+ | the app | |
| [Ollama](https://ollama.com/download) | chat | Installing it needs sudo, so do it yourself (e.g. `sudo pacman -S ollama`). Setup does the rest. |
| Podman or Docker | voice | Lets Initial setup install VoiceStudio without sudo. Alternatively, install VoiceStudio yourself. |
| ~20 GB free disk | voice | VoiceStudio image 11.6 GB + speech models ~3 GB |
| A microphone and speakers | voice | |

## Quick start

```bash
git clone https://github.com/prashlkam/plk-avtaar-local.git
cd plk-avtaar-local
make setup        # Python venv + npm install
make run          # builds the UI and serves the app on http://127.0.0.1:8080
```

Open **http://127.0.0.1:8080**, then go to **Settings → Initial setup → Start setup**. The first run downloads several GB; afterwards it takes about 2 minutes. When it finishes, click **🎤 Talk** (or press **Ctrl+Space**) and say hello.

## Initial setup

One button that **installs, configures and tests** every component. **Running it again reconfigures and retests**. Each step reports ✅, ⚠️ or ❌ with a fix hint, and steps that depend on a failed one are skipped.

| # | Step | What it does |
|---|---|---|
| 1 | App files and data folder | Checks the data folder and database, and builds the UI if needed |
| 2–3 | Ollama installed / running | Starts the service, or falls back to `ollama serve` as your user. If Ollama is missing, it shows the install command. |
| 4–5 | Language model downloaded / answers | Pulls the default model if missing, then gets a real reply and reports tokens/s |
| 6 | VoiceStudio installed | Reuses a running VoiceStudio, launches an installed desktop app, or **installs the official image as the rootless container `avtaar-voicestudio`**. The container listens only on `127.0.0.1:3900`, gets a generated admin key, has analytics off, keeps its data in a persistent volume, and uses the GPU when the NVIDIA container toolkit is set up. |
| 7–8 | VoiceStudio running / connected | Waits for `/health` and checks auth and voices |
| 9 | Speech-to-text model installed | If VoiceStudio has no ASR model, installs the one it asks for: **Whisper small** on CPU, large-v3-turbo on GPU |
| 10–12 | Text-to-speech / speech-to-text / live transcription tests | Speaks a test phrase, transcribes it back and scores the match, then tests the live socket |
| 13–14 | Microphone / speakers (in your browser) | Checks mic permission and input level, then plays the test phrase |

**Model licences:** VoiceStudio's speech engine (OmniVoice) is licensed **CC-BY-NC, non-commercial**, and must be accepted in VoiceStudio before it will speak. Setup never accepts licences for you. See [Accepting the voice model licence](docs/USER_GUIDE.md#accepting-the-voice-model-licence).

## Features

- **Chat:** streaming replies with Markdown and code highlighting, model picker, edit and resend, regenerate, stop (`Esc`), chat history (rename, delete), dark/light theme, system prompt and temperature
- **Voice output:** replies are spoken sentence by sentence while they stream, cleaned for speech (code, links and emoji are not read out), played in order and without gaps. 🔊 reads any message aloud.
- **Avatar:** static image while idle, listening or thinking; **animated GIF only while audio is actually playing**. Status ring, live captions, and full-screen **Avatar mode**. Upload your own images.
- **Push-to-talk:** your words appear in the prompt box (live with a streaming ASR model). It stops automatically when you pause, sends automatically, and talking interrupts the avatar (barge-in).
- **Reliability:** model warm-up, health banners with Retry, clear mic and permission errors, and a batch transcription fallback

## Configuration

Copy `.env.example` to `.env` to change defaults:

| Variable | Default | Meaning |
|---|---|---|
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama server (localhost only unless `ALLOW_LAN=1`) |
| `VOICESTUDIO_URL` | `http://127.0.0.1:3900` | VoiceStudio server (same rule) |
| `DEFAULT_MODEL` | `gemma4:latest` | Chat model if none is chosen in Settings |
| `HOST` / `PORT` | `127.0.0.1` / `8080` | Where the app listens |
| `DATA_DIR` | `./data` | Chats, avatars, setup report, generated keys |
| `VOICESTUDIO_API_KEY` | (generated by setup) | Use your own VoiceStudio key instead |
| `VOICESTUDIO_IMAGE` | `ghcr.io/debpalash/voicestudio:stable` | Image setup installs |
| `AVTAAR_ASR_MODEL` | auto | Speech-to-text model setup pins in the container, e.g. `Systran/faster-whisper-medium` |
| `ALLOW_LAN` | `0` | Allow non-localhost upstreams and binding (not recommended) |

Everything else (model, voice, speed, language, auto-send, auto-stop, avatar images) is in **Settings** in the app.

## Privacy: 100% local

- The app listens only on `127.0.0.1` and refuses non-local Ollama or VoiceStudio URLs.
- A strict Content-Security-Policy (`connect-src 'self'`) stops the browser from talking to anything else. All scripts, styles and icons are bundled, with no CDNs or web fonts.
- Requests from other websites can't change data or start setup (Origin checks on writes and on the speech WebSocket).
- Ollama cloud models (`*-cloud`) are hidden. The VoiceStudio container runs with analytics off and is published only on `127.0.0.1`.
- Internet is used only to **download** things during setup (the container image and models). Chatting and speaking work offline after that.

## Commands

| Command | What it does |
|---|---|
| `make setup` | Create the Python venv and install backend + frontend dependencies |
| `make run` | Build the UI and serve everything on http://127.0.0.1:8080 |
| `make dev` | Hot reload: API on :8080, UI on http://127.0.0.1:5173 |
| `make test` | Backend (pytest) + frontend (Vitest) tests |
| `make check` | Tests + Svelte/TypeScript type check |
| `make services` | Check that Ollama and VoiceStudio are reachable |
| `make fake-voice` | Fake VoiceStudio on :3900 for development (tones instead of speech). Stop it before using the real one. |
| `make avatar` | Regenerate the placeholder `idle.png` / `talking.gif` |

## Project layout

```
backend/                FastAPI gateway (Python)
  app/main.py           app, security headers, static UI
  app/routes/           chat, chats/settings, tts, stt (WS proxy), avatar, health, setup
  app/services/         Ollama and VoiceStudio clients
  app/setup/            Initial setup: runner, steps, subprocess helpers
  tests/                pytest (43 tests)
frontend/               SvelteKit + Tailwind UI
  src/lib/state.svelte.ts            app state, chat, talk, warm-up
  src/lib/audio/                     speaker (TTS playback), voiceInput (mic/STT),
                                     sentenceChunker, speechCleaner, silenceDetector
  src/lib/components/                chat, prompt box, avatar panel/mode, settings, setup dialog
  static/avatar/                     placeholder idle.png / talking.gif
scripts/                fake VoiceStudio, service checks, smoke test, avatar generator
docs/USER_GUIDE.md      user guide
data/                   runtime data (not committed): app.db, avatars/, secrets.json, setup report
```

## Licences

- **This app:** source in this repository.
- **VoiceStudio** is AGPL-3.0. The app talks to it over HTTP as a separate program and doesn't include or modify its code.
- **Speech models** have their own licences, shown and accepted in VoiceStudio. **OmniVoice (TTS) is CC-BY-NC: non-commercial use only.** Whisper (ASR) is MIT.
- **Chat models** in Ollama have their own licences (e.g. Gemma terms).
