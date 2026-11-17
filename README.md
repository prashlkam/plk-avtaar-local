# Avtaar (local)

A fully local AI avatar chat app: an open-webui-style interface with an Avtaar you can type to (and soon talk to). The LLM runs in **Ollama**; speech will run in **VoiceStudio**. See [Plan.md](Plan.md) for the full design.

**Status:** Phases 1–4 are done: text chat, voice output with the animated Avtaar, push-to-talk, and polish. Voice has been tested against `scripts/fake_voicestudio.py` but not yet against the real VoiceStudio. Phase 5 (packaging) is next.

## Requirements

- [Ollama](https://ollama.com) running on `127.0.0.1:11434` with at least one model (default: `gemma4:latest`)
- Python 3.11+ and Node 20+
- [VoiceStudio](https://github.com/debpalash/VoiceStudio) on `127.0.0.1:3900`. This is optional until Phase 2. On Arch Linux: `yay -S voicestudio-bin`.

## Initial setup (one click)

Open **Settings → Initial setup** (also linked from the "Voice is off" and "Ollama is not reachable" banners). For each component it checks, installs or starts it if needed, configures it, and tests it. Progress streams into the dialog, and the run continues on the server if you close the dialog.

| Step | What it does |
|---|---|
| App files | Checks the data folder and database. Builds the UI if it's missing. |
| Ollama installed / running | Starts the system service, or falls back to `ollama serve` as your user. Installing Ollama itself needs sudo, so setup shows you the exact command. |
| Language model | Downloads the default model if it's missing (with progress), then gets a real reply and reports tokens/s. |
| VoiceStudio installed | Reuses one that's already running, or launches the desktop app if installed. Otherwise installs the official image as a **rootless Podman/Docker container** `avtaar-voicestudio`, bound to `127.0.0.1:3900`, with analytics off and a generated admin key (stored in `data/secrets.json`, mode 0600). Uses the GPU if the NVIDIA container toolkit is set up, otherwise the CPU. |
| VoiceStudio running / connected | Waits for `/health` (up to 15 min on first start) and checks voices. |
| Text-to-speech, speech-to-text, live transcription | Speaks a test phrase, transcribes it back and scores the match, then streams it through the live socket. The first run can download speech models (~2.4 GB). |
| Microphone / speakers | Runs in the browser: checks mic permission and input level, then plays the test phrase. |

**Running it again** reconfigures and retests everything. A container made by setup is recreated with the current settings, but its data volume (with downloaded models) is kept. Steps that depend on a failed step are skipped. Every failure or warning comes with a fix hint.

Because of this feature, the gateway now rejects cross-site `POST`/`PUT`/`PATCH`/`DELETE` requests: other websites open in your browser can't trigger setup or change data.

## Quick start

```bash
make setup     # Python venv + npm install
make run       # builds the UI and serves everything on http://127.0.0.1:8080
# then: Settings → Initial setup
```

For development (hot reload), run `make dev` and open http://127.0.0.1:5173.

Other commands:

| Command | What it does |
|---|---|
| `make test` | Backend tests (pytest) |
| `make check` | Tests + Svelte/TypeScript type check |
| `make services` | Shows whether Ollama and VoiceStudio are reachable, and lists models and voices |
| `make fake-voice` | Runs a stand-in VoiceStudio on :3900 for developing without the real one: tones instead of speech, and a fixed scripted transcript for STT. `FAKE_NO_STREAM=1` disables live STT so you can test the fallback. Stop it before starting VoiceStudio. |
| `make avatar` | Regenerates the placeholder `idle.png` / `talking.gif` |
| `python3 scripts/smoke_tts_stt.py` | Phase 0 VoiceStudio check: TTS → STT round trip, plus a dump of the live-STT WebSocket frames |

## Features (Phase 1)

- Streaming chat with any local Ollama model, rendered as Markdown with highlighted code blocks and a copy button
- Chat history in SQLite (`data/app.db`): new, rename (double-click), delete
- Edit a user message and resend it, regenerate the last reply, and Stop (or press `Esc`). Partial replies are kept.
- Settings: default model, system prompt / persona, temperature
- Dark/light theme, collapsible sidebar, Avtaar side panel with live status, and service health indicators

## Features (Phase 2: voice and avatar)

- Replies are spoken **sentence by sentence while they stream**. The first sentence goes to VoiceStudio as soon as it is complete.
- Speech is cleaned before it's sent: Markdown is removed, code blocks are replaced with "I've put the code on screen.", URLs become "a link", and emoji are dropped.
- Audio plays in order and without gaps. Up to 2 TTS requests run at once, and synthesis stays at most about 2 s ahead of playback to spare the GPU.
- **The Avtaar shows `talking.gif` only while audio is audible** and `idle.png` the rest of the time, with a short hold so it doesn't flicker between sentences.
- 🔊 reads any reply aloud. Voice on/off sits in the header and the Avtaar panel. Stop or `Esc` silences everything.
- Settings: voice (listed from VoiceStudio), speed, and TTS engine id. The default is `tts-1` / `alloy`, which VoiceStudio maps to its active engine and default voice.

## Features (Phase 3: push-to-talk)

- Click **🎤 Talk** (or press **Ctrl+Space**) and speak. Your words appear **live** in the prompt box. Click **Done** (or press Ctrl+Space again) to finish. **Esc** cancels and puts back whatever was in the box before.
- By default the message sends automatically. Turn off **Send automatically** in Settings to edit the transcript before sending.
- **Barge-in:** starting to talk while the Avtaar is replying stops its speech and the reply at once. The partial reply is kept.
- Audio streams from the mic (WebM/Opus, 250 ms slices) through `/ws/stt` to VoiceStudio's live STT socket. If that socket is unavailable or drops, the full recording is transcribed with `/api/stt` when you click Done.
- The Talk button shows a live input-level meter. Clear messages appear if mic permission is denied, no mic is found, or the mic is busy.
- Settings: spoken language (empty means auto-detect).

## Features (Phase 4: polish)

- **Hands-free stop:** push-to-talk ends by itself after you pause (1.5 s by default; Off, 1, 2.5 or 4 s in Settings). It ignores clicks and learns the room's background noise during the first 250 ms. A recording is capped at 60 s.
- **Avatar mode** (⤢ in the header or the Avtaar panel): a full-screen view with a large Avtaar, live captions of the sentence being spoken, your words shown live while you talk, and one big mic button. It's remembered between visits.
- **Custom Avtaar images:** upload in Settings → Avtaar images. Use a static image for idle and an animated GIF or WebP for talking. Images are stored in `data/avatars/`, the file type is checked from the image data, and "Use default" restores the placeholder.
- **Model warm-up:** the selected model is loaded into memory when the app opens and when you switch models, so the first reply isn't slowed by loading.
- **Service banners:** Ollama down (red) or VoiceStudio down (amber, dismissible), each with a fix hint and Retry. Health is re-checked every 5 s while something is down and every 20 s otherwise, and you get a notice when a service comes back.
- **Phones:** the sidebar opens as an overlay, long model names are truncated, and a small floating Avtaar appears while it's listening, thinking or speaking.

**Your own avatar:** upload it in Settings. Alternatively, replace the built-in placeholders in `frontend/static/avatar/` and run `make build`. Square images work best.

## 100% local

- `/ws/stt` refuses WebSocket connections from non-local web pages, because WebSockets bypass CORS.
- The gateway binds to `127.0.0.1`. Upstream URLs that aren't localhost are refused unless `ALLOW_LAN=1` is set.
- A strict Content-Security-Policy (`connect-src 'self'`) stops the browser from calling anything outside the app.
- All JS, CSS and icons are bundled. There are no CDNs or web fonts.
- Ollama cloud models (`*-cloud`) are hidden from the model list.

## Layout

```
backend/   FastAPI gateway (app/routes: chat, chats, health), SQLite, tests
frontend/  SvelteKit + Tailwind UI (src/lib/components, state.svelte.ts)
scripts/   service checks and the VoiceStudio smoke test
data/      runtime data (gitignored)
```

## Licence notes

VoiceStudio is AGPL-3.0. This app only calls it over HTTP as a separate local service and doesn't bundle or modify its code.
