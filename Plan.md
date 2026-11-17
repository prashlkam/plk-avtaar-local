# Plan: Local AI Avtaar App

A chat app in the style of open-webui with an animated avatar ("Avtaar") that you can talk to by voice. It runs **100% locally**:

- **LLM:** Ollama (local models)
- **Speech-to-text (STT) and text-to-speech (TTS):** [VoiceStudio](https://github.com/debpalash/VoiceStudio), running locally on `http://127.0.0.1:3900`
- **UI:** an open-webui-style chat interface with an avatar panel. The avatar shows an animated GIF while it is speaking and a static image the rest of the time.

---

## 0. Status (updated 2026-11-17)

| Phase | Status |
|---|---|
| 0. Environment and API verification | ✅ Done. VoiceStudio 0.5.8 installed as a Podman container by Initial setup and verified against the real API. Differences from the docs are recorded in §4.3. |
| 1. Text chat MVP | ✅ Done and tested against the real Ollama |
| 2. Voice output and avatar | ✅ Done and tested end to end with the real VoiceStudio (CPU) |
| 3. Push-to-talk | ✅ Built and tested with a synthetic microphone. ⚠️ Not yet tried with a real microphone, and live partial text needs a streaming ASR model (§4.3). |
| 4. Polish | ✅ Done |
| 4b. **Initial setup** (added on request) | ✅ Done. One button installs, configures and tests every component, and re-running it reconfigures and retests (§8, Phase 4b). |
| 5. Packaging | 🟡 Partly done: `make setup/dev/run/test` and a user guide ([docs/USER_GUIDE.md](docs/USER_GUIDE.md)) exist. A desktop launcher, compose file, screenshots and the offline acceptance test remain. |

**Tests:** 43 backend (pytest) and 23 frontend (Vitest), plus a fake VoiceStudio ([scripts/fake_voicestudio.py](scripts/fake_voicestudio.py)) for development.

**Biggest open issue, speed on this laptop:** with no GPU available to the container, the first spoken audio of a reply arrives about 18 s after sending, with gaps of about 13 s between sentences (§13). The fix is GPU access for the VoiceStudio container (the NVIDIA container toolkit) and/or a smaller chat model.

Code: <https://github.com/prashlkam/plk-avtaar-local>

---

## 1. Goals and Non-Goals

### Goals
1. Everything runs on the local machine: no cloud APIs, no telemetry, and no CDN assets at runtime.
2. **Push-to-talk:** the user clicks a mic button to speak. Their words appear **live** in the prompt text box as they speak.
3. Every LLM reply is shown as **text** (streamed, rendered as Markdown) and also spoken as **voice**.
4. The avatar is **animated (GIF) while audio is playing** and **static (PNG) when idle**, listening, or thinking.
5. The chat UX is familiar from open-webui: a sidebar with conversations, a model picker, streaming responses, Markdown and code blocks, and dark/light themes.

### Non-Goals (for v1)
- Lip-sync or 3D/2D rigged avatars. The GIF swap comes first, and an upgrade path is described in §12.
- Multi-user accounts, auth, and remote access.
- RAG, documents, tools, and web search.
- A mobile app.

---

## 2. Environment Snapshot (this machine)

| Item | Status |
|---|---|
| OS | Arch Linux (kernel 7.3) |
| CPU / RAM | 31 GB RAM |
| GPU | NVIDIA T1200 Laptop, **4 GB** VRAM. `gemma4:latest` (6.6 GB) only partly fits, so Ollama splits it between GPU and CPU (about 14–16 tokens/s). |
| Ollama | 0.40.16, system service (`/usr/bin/ollama`) |
| Models available | `gemma4:latest` (6.6 GB), `gemma4:26b` (18 GB), `bonsai-2:27b`, `MichelRosselli/bonsai-27b` |
| Python / Node | Python 3.14, Node 24 |
| Containers | Podman 6.2 (rootless). Docker is not installed. **No NVIDIA container toolkit**, so containers run on the CPU. |
| VoiceStudio | **0.5.8**, installed by Initial setup as the Podman container `avtaar-voicestudio` (image `ghcr.io/debpalash/voicestudio:stable`, 11.6 GB), on `127.0.0.1:3900`. TTS: OmniVoice (licence accepted). ASR: Whisper small (faster-whisper). |

The default model is **`gemma4:latest`** because it is the fastest of the installed models. The user can change it in the UI.

---

## 3. Architecture

```
┌──────────────────────────── Browser (localhost:5173 dev / :8080 prod) ────────────────────────────┐
│  SvelteKit + Tailwind UI (open-webui look & feel)                                                │
│  ┌──────────────┐  ┌───────────────────────────────────────────┐  ┌──────────────────────────┐   │
│  │ Sidebar      │  │ Chat pane (messages, markdown, streaming) │  │ Avtaar panel             │   │
│  │ chats/models │  │ Prompt box  [🎤 Talk] [Send] [Stop]        │  │ idle.png / talking.gif   │   │
│  └──────────────┘  └───────────────────────────────────────────┘  └──────────────────────────┘   │
│         │ MediaRecorder (WebM/Opus) ──WS──┐     │ fetch SSE         │ <audio>/WebAudio playback  │
└─────────┼─────────────────────────────────┼─────┼───────────────────┼────────────────────────────┘
          │                                 ▼     ▼                   ▲
┌─────────┴──────────── Local gateway: FastAPI (127.0.0.1:8080) ──────┴────────────────────────────┐
│  /api/chat (SSE)   → Ollama  http://127.0.0.1:11434/api/chat (stream)                            │
│  /api/models       → Ollama  /api/tags                                                           │
│  /ws/stt  (WS proxy) → VoiceStudio ws://127.0.0.1:3900/v1/audio/transcriptions/stream            │
│  /api/stt (fallback) → VoiceStudio POST /v1/audio/transcriptions                                 │
│  /api/tts          → VoiceStudio POST /v1/audio/speech                                           │
│  /api/voices       → VoiceStudio GET  /v1/audio/voices                                           │
│  /api/health       → checks all three                                                            │
│  SQLite (chats, messages, settings)   + serves built frontend + avatar assets                    │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
          │                                   │
   ┌──────┴───────┐                  ┌────────┴──────────┐
   │ Ollama :11434│                  │ VoiceStudio :3900 │
   └──────────────┘                  └───────────────────┘
```

### Why a small backend gateway (and not a browser talking to the services directly)?
- **CORS:** neither Ollama nor VoiceStudio is guaranteed to allow browser origins. A same-origin gateway avoids that problem entirely.
- **One origin and one port** for the user. The gateway also serves the built frontend.
- **Persistence:** chat history is stored in SQLite.
- **Health checks and friendly errors** when Ollama or VoiceStudio is down.
- **Security:** the gateway binds to `127.0.0.1` only, and API keys never reach the browser.

### Tech stack
| Layer | Choice | Reason |
|---|---|---|
| Frontend | **SvelteKit + TypeScript + Tailwind CSS** (static adapter) | Same stack as open-webui, so the look and feel are easy to match |
| Markdown | `marked` + `DOMPurify` + `highlight.js` (bundled locally) | Safe rendering, code highlighting, no CDN |
| Backend | **Python 3.12 + FastAPI + uvicorn + httpx + websockets** | Async streaming proxy and simple WebSocket handling |
| Storage | SQLite via `sqlmodel` (or the plain `sqlite3` module) | Zero-config |
| Packaging | `uv` for Python, `npm`/`bun` for the UI, plus one `make dev` / `make run` | Simple |

---

## 4. External APIs Used (contracts)

> These come from the VoiceStudio docs (`docs/agentic-voice.md` and `docs/speech-platform.md`). **Phase 0 verifies them** against the installed version, because the project moves quickly.

### 4.1 Ollama
- `GET  /api/tags` lists the installed models.
- `POST /api/chat` with `{ model, messages:[{role,content}], stream:true, options:{temperature,...}, keep_alive:"30m" }` returns NDJSON chunks `{message:{content}, done}`.

### 4.2 VoiceStudio (base `http://127.0.0.1:3900`; loopback clients need no API key, *except in a container; see §4.3*)
- **Discovery:** `GET /.well-known/voicestudio-speech`
- **Live STT (preferred):** `WS /v1/audio/transcriptions/stream`
  - Client sends binary **WebM/Opus** frames by default, or `?pcm=1&sr=16000` for raw s16le mono PCM.
  - Client ends the stream with the text frame `{"type":"input_audio.end"}`.
  - Server sends:
    - `{"type":"session.started", "session_id":...}`
    - `{"type":"partial", "text":...}` (live text that keeps updating)
    - `{"type":"final", "final_kind":"utterance"|"summary", "text":...}`
- **Batch STT (fallback):** `POST /v1/audio/transcriptions` (OpenAI-compatible multipart: `file`, `model`, `language?`)
- **TTS:** `POST /v1/audio/speech`
  - Body: `{ model, voice, input, instructions?, speed?, response_format, stream_format? }`
  - `response_format`: `mp3` (default) | `opus` | `aac` | `flac` | `wav` | `pcm` (24 kHz s16le mono)
  - Streaming: `response_format:"pcm"` + `stream_format:"audio"` returns raw chunks, or `stream_format:"sse"` returns base64 `speech.audio.delta` events followed by `speech.audio.done`
- **Voices:** `GET /v1/audio/voices` returns `[{voice_id, name, addressable_by_name}]`
- **Models:** `GET /v1/models`

### 4.3 What we found against the real VoiceStudio 0.5.8 (Phase 0 results)

| Topic | Planned / documented | Actual | What the app does |
|---|---|---|---|
| Auth | Loopback needs no key | **In a container every request needs `Authorization: Bearer <key>`**: NAT makes host traffic look non-loopback. The web UI also opens on an "API key" screen. | Setup generates the key (`data/secrets.json`, 0600) and the gateway sends it on HTTP and WebSocket calls. |
| Health | Discovery endpoint | `GET /health` returns `{status, device, engine, version}` and 503 while starting | Setup waits on `/health` and falls back to discovery. |
| Model licences | Not mentioned | The TTS engine (k2-fsa/OmniVoice, CC-BY-NC, non-commercial) and its tokenizer must be **accepted** first. Until then `/v1/audio/speech` returns **403** "Licence not accepted". | Setup reports it with a hint. Acceptance is the user's decision. It can be done in the Model Catalogue, or with `POST /models/licenses/accept {repo_id, fingerprint, accepted:true}` (admin). Details: `GET /models/licenses/details/{repo}`. |
| ASR model | "downloads on first use" | `/v1/audio/transcriptions` returns **409** with `missing_repo_id` when no ASR model is installed. | Setup installs that repo with `POST /models/install {repo_id}` and waits until transcription works. |
| ASR choice | — | Auto-detect picks the **WhisperX** engine, which reads `ASR_MODEL_WHISPERX` (default large-v3, 3 GB). `ASR_MODEL_FASTER` alone is ignored. | The container is created with `OMNIVOICE_ASR_BACKEND=faster-whisper` and `ASR_MODEL_FASTER=Systran/faster-whisper-small` (CPU) or `deepdml/faster-whisper-large-v3-turbo-ct2` (GPU). Override with `AVTAAR_ASR_MODEL`. |
| Live STT | Partials while speaking | With Whisper small on CPU the socket returns **only a final** transcript (0 partials). | Push-to-talk still works; the text appears when you click Done. Live partials need a streaming (sherpa-onnx) ASR model. |
| Container data | — | `/app/omnivoice_data` holds models, the HF cache, licence acceptance and settings. | Mounted as the named volume `avtaar-voicestudio-data`, so re-running setup (which recreates the container) keeps models and licences. |
| Telemetry | — | The image supports `OMNIVOICE_ANALYTICS_DISABLED=1`. | Always set by setup. |

---

## 5. Core Interaction Flows

### 5.1 Avatar / app state machine

```
            click 🎤                    click 🎤 again / silence timeout
  IDLE ───────────────▶ LISTENING ─────────────────────────────────▶ (text in box)
   ▲                       │ partial text → prompt box (live)              │ auto-send (setting) or user clicks Send
   │                       ▼                                               ▼
   │                                                                 THINKING  (LLM streaming, text renders)
   │                                                                       │ first sentence ready → TTS
   │                                                                       ▼
   └──────────── audio queue empty & LLM done ◀──────────────────── SPEAKING  (talking.gif)
                 (or user clicks Stop / 🎤 = barge-in)
```

| State | Avatar image | Mic button | Notes |
|---|---|---|---|
| IDLE | `idle.png` (static) | "Talk" | |
| LISTENING | `idle.png` + pulsing "listening" ring | "Stop listening" (red) | Prompt box shows live text |
| THINKING | `idle.png` + subtle "…" indicator | "Talk" (barge-in allowed) | Text streams into the chat |
| SPEAKING | **`talking.gif`** (animated) | "Talk" (interrupts) | Shown **only while audio is actually playing** |

Optional assets (`listening.png`, `thinking.gif`) can be added later without code changes, using a per-state asset map in the config.

### 5.2 Voice input (push-to-talk), step by step
1. The user clicks **🎤 Talk**. The frontend calls `getUserMedia({audio:{echoCancellation:true, noiseSuppression:true}})`.
2. If TTS is playing, stop it at once (barge-in) and abort any TTS fetches still in flight.
3. Open `ws://localhost:8080/ws/stt`. The gateway opens the upstream WS to VoiceStudio and relays frames both ways.
4. `MediaRecorder` (`audio/webm;codecs=opus`, `timeslice=250ms`) sends each chunk as a binary frame.
5. On each `partial`, the prompt box shows `committedText + partialText`, with the partial text styled lighter. On `final/utterance`, that text is appended to `committedText`.
6. The user clicks the button again to stop. Optionally, a silence timeout ends listening (VAD, §5.5). The frontend sends `{"type":"input_audio.end"}`, waits for `final/summary` (with a 3 s timeout), then closes.
7. The prompt box now holds the final text, and **the user can edit it**. With **Auto-send after speaking** on (default ON), it submits at once. Otherwise the user presses Enter or Send.
8. **Fallback:** if the WS fails (an engine without streaming, or an older VoiceStudio), record the whole clip locally, then `POST /api/stt` and put the result in the box. Live partials are lost, but the feature still works.

### 5.3 LLM reply → text + voice (low-latency pipeline)
1. `POST /api/chat` sends `{chatId, model, messages}`. The gateway streams Ollama NDJSON back to the browser as **SSE** (`event: token`).
2. The frontend appends each token to the assistant message, and the message re-renders as Markdown (throttled with `requestAnimationFrame`).
3. **Sentence chunker** (in the frontend): it buffers tokens and emits a "speakable chunk" when it sees a sentence end (`. ! ? 。` + whitespace/newline), or once the buffer reaches about 200 characters at a comma or space. It does not split inside code fences.
4. **Speech text cleaner:** removes Markdown (`**`, `#`, list bullets, links → link text), **drops fenced code blocks** (replaced with "Here's the code." once), turns URLs into "link", and turns emojis into nothing.
5. **TTS queue:** each chunk becomes `POST /api/tts` → VoiceStudio `/v1/audio/speech` with `response_format:"wav"`. This is the simplest option and needs no ffmpeg. Requests are **pipelined** (up to 2 in flight), and playback is **strictly in order**.
6. **Audio player:** uses one `AudioContext`. It decodes each WAV and schedules buffers back to back so there are no gaps.
   - While any buffer is playing, the avatar is SPEAKING (`talking.gif`).
   - When the queue drains and the LLM stream is done, the avatar returns to IDLE.
7. **v1.1 latency upgrade:** use `response_format:"pcm"` + `stream_format:"audio"` and feed 24 kHz s16le chunks into an `AudioWorklet` ring buffer, so audio starts during the first sentence.
8. **Stop button:** aborts the SSE stream (the gateway cancels the Ollama request), aborts pending TTS, flushes the audio queue, and sets the avatar to IDLE. The partial text stays in the chat.

### 5.4 Per-message controls (open-webui style)
- 🔊 **Replay**: re-speaks the message. Audio is cached in memory per message for the session.
- 📋 Copy, ✏️ Edit and resend, 🔄 Regenerate.

### 5.5 Optional voice-activity detection (VAD) (phase 4)
- Use a simple RMS-energy VAD in an `AudioWorklet`. With "auto-stop after N ms of silence" enabled (default 1500 ms, configurable), listening ends on its own. This keeps the "click to talk" model but saves the second click.

---

## 6. UI Design (open-webui style + Avtaar)

```
┌──────────┬──────────────────────────────────────────────────────┬─────────────────┐
│ + New    │  Model: [gemma4:latest ▾]          Voice: [Aria ▾] ⚙ │                 │
│          │──────────────────────────────────────────────────────│   ┌─────────┐   │
│ Today    │                                                      │   │         │   │
│  • Chat1 │   🧑 What's the capital of France?                   │   │ AVTAAR  │   │
│  • Chat2 │                                                      │   │ gif/png │   │
│ Earlier  │   🤖 The capital of France is **Paris**. …    🔊📋🔄  │   │         │   │
│  • …     │                                                      │   └─────────┘   │
│          │                                                      │   ● Speaking…   │
│          │──────────────────────────────────────────────────────│                 │
│ ⚙ Settings│ [ Ask anything…  (live transcript appears here)   ] │  🔇 Mute voice  │
│          │                              [🎤 Talk] [➤ Send] [■]  │                 │
└──────────┴──────────────────────────────────────────────────────┴─────────────────┘
```

- **Layout:** collapsible left sidebar, center chat column (max-width ~ 768 px, like open-webui), and a right **Avtaar panel** (about 280–360 px). The panel can be collapsed, or switched to **"Avatar mode"**, a large centered avatar with captions underneath.
- **Responsive:** below 1024 px, the avatar moves to a small floating bubble above the prompt box.
- **Theme:** dark by default with neutral grays and rounded-2xl cards, like open-webui. Tailwind `dark:` classes and a toggle in Settings.
- **Mic button:** large and round. Its states are idle (gray), listening (red with a pulse animation and a live level meter), and disabled (STT unavailable, with a tooltip).
- **Keyboard:** `Enter` sends, `Shift+Enter` adds a newline, `Ctrl+Space` toggles push-to-talk, and `Esc` stops.
- **Status bar / toasts:** "Ollama not running", "VoiceStudio not reachable on :3900", and "Mic permission denied", each with a fix hint.
- **Settings modal:**
  - Model, system prompt / persona, and temperature
  - TTS voice (from `/v1/audio/voices`), speed, and the engine/model ID
  - STT language (auto or a fixed language)
  - Auto-send after speaking (on/off), voice output (on/off/mute), and auto-stop on silence
  - Avatar asset upload (idle image + talking GIF)
  - Endpoints (Ollama URL, VoiceStudio URL), which must be localhost-only (enforced, §9)

### Avatar assets
- `frontend/static/avatar/idle.png` and `frontend/static/avatar/talking.gif`. A default pair ships with the app. A simple original illustration can be made, or a still frame taken from the GIF with `ffmpeg -i talking.gif -vframes 1 idle.png`.
- Both images are **preloaded** at startup, so swapping between them is instant.
- **GIF restart trick:** to make the GIF start from frame 1 each time speech begins, re-assign `src` with a cache-busting fragment, or keep two `<img>` elements and toggle `visibility` instead of `src`. The second is preferred because it avoids flicker.
- Users can upload their own pair. Uploads go into `data/avatars/` and are served by the gateway.

---

## 7. Project Structure

> This is the original plan. The built layout is close, with a few renames: `recorder.ts` + `sttClient.ts` became `voiceInput.svelte.ts`, `ttsQueue.ts` + `player.ts` became `speaker.svelte.ts`, and `silenceDetector.ts` and `backend/app/setup/` were added. See the README's *Project layout* for the actual tree.

```
plk-avtaar-local/
├── Plan.md
├── README.md
├── Makefile                      # make setup | dev | run | check
├── .env.example                  # OLLAMA_URL, VOICESTUDIO_URL, DEFAULT_MODEL, DEFAULT_VOICE, PORT
├── backend/
│   ├── pyproject.toml            # fastapi, uvicorn[standard], httpx, websockets, sqlmodel, python-multipart
│   ├── app/
│   │   ├── main.py               # FastAPI app, static mount, CORS off (same-origin)
│   │   ├── config.py             # pydantic-settings; validates localhost-only URLs
│   │   ├── routes/
│   │   │   ├── chat.py           # POST /api/chat (SSE), GET /api/models
│   │   │   ├── stt.py            # WS /ws/stt proxy, POST /api/stt fallback
│   │   │   ├── tts.py            # POST /api/tts (streams audio through), GET /api/voices
│   │   │   ├── chats.py          # CRUD for conversations/messages
│   │   │   ├── settings.py       # GET/PUT settings, avatar upload
│   │   │   └── health.py         # GET /api/health
│   │   ├── services/
│   │   │   ├── ollama.py         # async client, streaming, cancellation
│   │   │   └── voicestudio.py    # async client for speech/transcription/voices
│   │   └── db.py                 # SQLite models: Chat, Message, Setting
│   └── tests/                    # pytest + respx mocks for Ollama/VoiceStudio
├── frontend/
│   ├── package.json              # svelte, @sveltejs/kit, adapter-static, tailwindcss, marked, dompurify, highlight.js
│   ├── src/
│   │   ├── routes/+page.svelte   # main layout
│   │   ├── lib/components/
│   │   │   ├── Sidebar.svelte
│   │   │   ├── ChatView.svelte
│   │   │   ├── Message.svelte    # markdown render + actions
│   │   │   ├── PromptBox.svelte  # textarea, mic, send, stop; shows live transcript
│   │   │   ├── MicButton.svelte  # recording UI + level meter
│   │   │   ├── AvatarPanel.svelte# idle.png / talking.gif switcher + status
│   │   │   └── SettingsModal.svelte
│   │   ├── lib/audio/
│   │   │   ├── recorder.ts       # getUserMedia + MediaRecorder → WS
│   │   │   ├── sttClient.ts      # WS protocol (partial/final), fallback batch
│   │   │   ├── sentenceChunker.ts
│   │   │   ├── speechCleaner.ts  # markdown → speakable text
│   │   │   ├── ttsQueue.ts       # pipelined fetch, ordered, abortable
│   │   │   └── player.ts         # AudioContext scheduling, onStart/onIdle events
│   │   ├── lib/stores/           # appState (IDLE/LISTENING/THINKING/SPEAKING), chats, settings
│   │   └── lib/api.ts            # fetch/SSE helpers
│   └── static/avatar/{idle.png,talking.gif}
├── data/                         # runtime: app.db, avatars/ (gitignored)
└── scripts/
    ├── check_services.sh         # pings Ollama + VoiceStudio, lists models/voices
    └── smoke_tts_stt.py          # end-to-end: TTS a sentence → STT it back → compare
```

---

## 8. Implementation Phases and Milestones

### Phase 0: Environment and API verification (½ day) ✅
- [x] Install VoiceStudio. *Done by Initial setup as a rootless Podman container rather than by hand. TTS is OmniVoice (licence accepted) and ASR is Whisper small, not a streaming Sherpa model (see §4.3).*
- [x] Discovery, voices and models respond (14 voices). *`/health` turned out to be the better readiness check.*
- [x] TTS returns WAV. *2.5 s of audio, played in the app.*
- [x] Batch STT round trip. *Setup speaks a test phrase, transcribes it back and scores the match: 100% of words.*
- [x] Streaming STT socket. *It works but returns only a final transcript with Whisper on CPU (§4.3). Frame shapes match the docs.*
- [x] Ollama time to first token measured (§13).
- [x] **Exit criteria:** all calls work and the differences are recorded in §4.3.

### Phase 1: Text chat MVP, open-webui look (1–2 days) ✅
- [x] Scaffold the FastAPI gateway: `/api/health`, `/api/models`, `/api/chat` (SSE proxy of Ollama with cancellation on client disconnect).
- [x] Scaffold SvelteKit + Tailwind with the dark theme, sidebar, chat view, and prompt box.
- [x] Streaming Markdown rendering (sanitized), code highlighting, Stop button. *Edit-and-resend and regenerate were added too.*
- [x] Persist chats in SQLite, with new/rename/delete in the sidebar.
- [x] **Exit criteria:** chatting with `gemma4:latest` works in an open-webui-style UI.

### Phase 2: Voice output and Avtaar (1–2 days) ✅
- [x] `/api/tts` proxy (streams bytes through) and `/api/voices`.
- [x] `sentenceChunker`, `speechCleaner`, `Speaker` (ordered, gapless). *Also: at most 2 requests in flight and about 2 s of lookahead, so a long reply doesn't flood the TTS engine.*
- [x] Avatar driven by audible playback, **not** LLM state. *A 400 ms hold avoids flicker between sentences. Placeholder art is generated by `scripts/make_placeholder_avatar.py`.*
- [x] Voice on/off toggle, voice picker, 🔊 replay per message.
- [x] **Exit criteria:** met with the real VoiceStudio. The GIF plays only while audio is audible.

### Phase 3: Voice input, push-to-talk (1–2 days) ✅ (⚠️ real mic untested)
- [x] `/ws/stt` bidirectional WS proxy, with an Origin check because WebSockets bypass CORS.
- [x] `voiceInput.svelte.ts`: live partials in the prompt box, final text committed, with a batch fallback if the socket fails at any point.
- [x] Mic button states, level meter, permission/no-mic/busy-mic errors, barge-in. *Barge-in stops both the speech and the LLM stream, not just the speech as first planned, so that the new spoken question can be sent at once. The partial reply is kept.*
- [x] Auto-send setting, plus the batch-STT fallback path.
- [ ] **Exit criteria:** verified with a synthetic mic and the fake VoiceStudio only. Still to do: test with a real microphone. Live partials depend on the ASR model (§4.3).

### Phase 4: Polish and robustness (1–2 days) ✅
- [x] Silence auto-stop (adaptive noise floor, 250 ms calibration, ignores clicks, 60 s cap), `Ctrl+Space`, full-screen **Avatar mode** with live captions, responsive/mobile layout.
- [x] Settings (system prompt/persona, temperature, voice, speed, language, auto-send, auto-stop, avatar upload).
- [x] Health banners with fix hints, Retry and adaptive polling (5 s while something is down, 20 s otherwise).
- [x] Ollama `keep_alive` and warm-up via `/api/warmup` on start and on model change.
- [ ] **Exit criteria:** every failure mode shows a clear message (verified). A 30-minute soak session has not been run yet.

### Phase 4b: Initial setup (added on request) ✅
- [x] **Settings → Initial setup** runs 12 server steps plus 2 browser checks. Each step is check → install/start if needed → configure → test. Re-running it reconfigures and retests. Progress streams to the dialog and continues in the background if it's closed.
- [x] VoiceStudio is installed as a rootless Podman/Docker container on `127.0.0.1` only, with a generated admin key, analytics off, a persistent data volume, and GPU flags when the NVIDIA toolkit is present.
- [x] Missing ASR model detected and installed automatically. Model licences are never accepted automatically.
- [x] Cross-site write protection added to the gateway, because the app can now install software.
- [x] Tested: 9 setup tests, including a full run against the fake VoiceStudio, plus real runs on this machine.

### Phase 5: Packaging (½–1 day) 🟡
- [x] `make setup` (pip venv + npm install), `make dev`, `make run`, `make test`, `make check`, `make services`, `make fake-voice`, `make avatar`.
- [ ] Optional: `docker-compose.yml` with the app + VoiceStudio.
- [ ] Optional: a systemd user unit or desktop launcher. Later, a Tauri/Electron shell.
- [x] README and a detailed [user guide](docs/USER_GUIDE.md) with troubleshooting. **Screenshots are still to come.**

**Total estimate:** about 6–9 working days for a polished v1. The actual build followed the plan, plus Initial setup.

---

## 9. "100% Local" Guarantees (and how we enforce them)

1. The gateway **binds to `127.0.0.1` only**.
2. `config.py` **rejects any upstream URL** whose host is not `localhost`, `127.0.0.1` or `::1`, unless an explicit `ALLOW_LAN=1` override is set.
3. **No CDN:** all JS, CSS and fonts are bundled by Vite. Add a CI check that greps the build output for `http(s)://` outside the allowed localhost URLs.
4. A **Content-Security-Policy** header in the gateway: `default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:`. The browser then blocks any accidental external call.
5. **VoiceStudio:** use only local engines (no "remote GPU" or Cloud features), and turn off any update checks or telemetry in its settings. Document this in the README.
6. **Ollama:** use local models only. Do not use `ollama.com` cloud models (names ending in `-cloud`).
7. **Offline test:** after models are downloaded, run the full flow with networking disabled (`nmcli networking off`). This is the acceptance test.

---

## 10. Error Handling and Edge Cases

| Situation | Behaviour |
|---|---|
| Ollama down / model missing | Red banner: "Start Ollama: `systemctl start ollama`", plus the model list from `/api/tags` |
| VoiceStudio down | Text chat still works. The mic and voice controls are disabled, with a tooltip on how to start it |
| Mic permission denied | Toast with steps to re-enable it. The text box still works |
| STT WS unsupported / fails | Falls back to the batch STT path (no live text, a "Transcribing…" spinner instead) |
| TTS fails for one chunk | Skip that chunk, log it, and keep playing the rest. The text is still shown |
| User clicks Talk while the avatar is speaking | Barge-in: stop audio, cancel pending TTS **and stop the LLM stream** (changed from the original plan so the new question can be sent at once). The partial reply is kept. |
| VoiceStudio needs a licence or ASR model | Setup detects it: the 403 licence error comes with a hint, and the missing ASR model (409) is installed automatically |
| A detached child keeps a pipe open (e.g. `podman run -d`) | Setup stops reading output once the process exits. Downloads give up only after 15 min with no output (6 h overall). |
| User clicks Stop | Cancel the LLM, TTS and audio. State goes to IDLE |
| Very long reply / code-heavy reply | The speech cleaner skips code. Optional setting: "Speak only the first N sentences" |
| Browser autoplay policy | The `AudioContext` is created/resumed on the first user click (Talk or Send) |
| Echo (TTS picked up by mic) | `echoCancellation:true`, and the mic is closed while the avatar speaks unless the user barges in |

---

## 11. Testing Strategy

- **Backend unit tests** (pytest + `respx`): SSE proxying, cancellation, the WS relay (mock upstream), the localhost-only URL validator.
- **Frontend unit tests** (Vitest):
  - `sentenceChunker`: abbreviations like "e.g.", decimals like "3.14", code fences, emoji
  - `speechCleaner`: Markdown cases
  - `ttsQueue`: ordering under out-of-order completion, abort
  - The state machine's transitions
- **Integration smoke** (`scripts/smoke_tts_stt.py`): TTS "The quick brown fox", then STT it back, then check word error rate < 20%.
- **E2E** (Playwright, Chromium with `--use-fake-device-for-media-stream --use-file-for-fake-audio-capture=sample.wav`): click Talk, see the transcript appear, auto-send, see the assistant text, and confirm `talking.gif` is visible during playback and `idle.png` after.
- **Manual checklist:** latency targets (§13), barge-in, the offline test (§9.7).

---

## 12. Future Enhancements (post-v1)
- **Better avatar:** a sprite-sheet with mouth shapes driven by audio amplitude (WebAudio `AnalyserNode`), giving cheap lip-flap sync. Later, Live2D/VRM (three-vrm) with visemes, or a local talking-head model (SadTalker/LivePortrait style) for photoreal output.
- **Voice cloning:** let the user create a VoiceStudio voice profile (with consent) and select it as the avatar's voice.
- **Persona packs:** avatar images + voice + system prompt bundled together.
- **Hands-free mode:** an always-listening VAD loop as an opt-in alternative to push-to-talk.
- **Emotion tags:** the LLM outputs a mood, which picks a matching avatar GIF and a TTS `instructions` style.
- **RAG / tools**, multi-language UI, a Tauri desktop app.

---

## 13. Performance Targets (on this machine, gemma4:latest)

| Metric | Target | Measured on this machine (CPU-only VoiceStudio) |
|---|---|---|
| Mic click → first live partial text | < 700 ms | n/a: Whisper small on CPU returns no partials (§4.3) |
| End of speech → final transcript | < 1 s | Not yet measured with a real mic. Silence auto-stop adds its 1.5 s pause on purpose. |
| Send → first LLM token | < 1.5 s (model warm) | ~1 s (gemma4:latest, 14–16 tokens/s, split across GPU and CPU) |
| First LLM sentence → first audio | < 1.2 s | ❌ **~9–18 s**. TTS runs at about 0.1–0.35× real time on CPU (3.1 s of speech in 8.8 s when idle; slower while the LLM also uses the CPU). |
| Gap between spoken sentences | small | ❌ ~13 s, for the same reason |
| Avatar GIF switch latency vs audio start | < 50 ms | ✅ the switch is scheduled on the audio clock |

**To meet the voice targets:** give the VoiceStudio container the GPU (`nvidia-container-toolkit` plus a CDI spec, then re-run setup), use a smaller chat model so it fits in 4 GB VRAM or frees the CPU, and/or switch to PCM streaming TTS (§5.3, step 7).

---

## 14. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| VoiceStudio API changes (a fast-moving project) | All calls go through `services/voicestudio.py`. Phase 0 verification plus a smoke script. Pin a known-good version |
| GPU memory contention (LLM + TTS + STT on one GPU) | Default to the smaller `gemma4:latest`. Allow running STT/TTS on CPU. Document VRAM needs |
| Streaming STT model not installed | Detect it through discovery or a WS failure, fall back to batch STT, and show a hint to install a streaming model |
| Choppy audio between sentences | Pipeline 2 TTS requests ahead and schedule gaplessly. Upgrade to PCM streaming |
| AGPL-3.0 licence of VoiceStudio | We only call it over HTTP as a separate local service and do not bundle or modify its code. Note this in the README. Check model licences per model |
| Browser differences in MediaRecorder | Target Chromium/Firefox. If `audio/webm;codecs=opus` is unsupported, use the PCM path (`?pcm=1&sr=16000`) via an AudioWorklet |

---

## 15. Definition of Done (v1)
- [x] `make run` brings up the app on `http://127.0.0.1:8080`, with Ollama and VoiceStudio running locally. *Initial setup gets VoiceStudio there.*
- [ ] You click 🎤, speak, see the words appear live in the prompt box, and the message is sent. *Works with a synthetic mic. Still to do: a real mic, and a streaming ASR model for live partials.*
- [x] The reply streams as Markdown text **and** is spoken. `talking.gif` animates only while the voice plays, and `idle.png` is shown otherwise. *Verified with the real VoiceStudio.*
- [x] Stop and barge-in work reliably. Chats persist across restarts.
- [ ] The full flow works with the network disabled. *Not yet run. Every model is local now, so this is expected to pass.*

---

## 16. Lessons Learned

1. **Verify third-party APIs against the real thing early.** The VoiceStudio docs were right about the endpoints but silent on what actually blocked us: container auth, model licences, the missing ASR model, and WhisperX ignoring `ASR_MODEL_FASTER`. All of these only showed up against the real container.
2. **A fake upstream pays for itself.** `scripts/fake_voicestudio.py` let Phases 2–4 and Initial setup be built and tested before VoiceStudio was installed, and backs a full-setup pytest.
3. **Detached processes and pipes:** `podman run -d` leaves conmon holding stdout, so "read to EOF" hangs forever. Wait for the process to exit, then drain the pipe briefly.
4. **Large downloads need inactivity timeouts, not wall-clock ones.** The 11.6 GB image took about 25 minutes at a variable 0.4–3.4 MB/s.
5. **Licences are the user's call.** Setup surfaces them with the actual terms; it never accepts them silently.
6. **Hardware dominates voice latency.** On a 4 GB GPU with VoiceStudio on the CPU, TTS speed, not app code, is the bottleneck.
