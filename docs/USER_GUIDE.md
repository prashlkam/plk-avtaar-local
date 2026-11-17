# Avtaar User Guide

Avtaar is an AI companion you can **type to or talk to**. It answers in text and out loud, and its animated face moves while it speaks. Everything runs **on your own computer**: no cloud service hears your voice or reads your messages.

This guide covers installing Avtaar, using every feature, and fixing common problems.

**Contents**

1. [How it works](#1-how-it-works)
2. [Before you start](#2-before-you-start)
3. [Installing](#3-installing)
4. [Initial setup](#4-initial-setup)
5. [Accepting the voice model licence](#accepting-the-voice-model-licence)
6. [The screen at a glance](#6-the-screen-at-a-glance)
7. [Chatting by text](#7-chatting-by-text)
8. [Talking to Avtaar](#8-talking-to-avtaar)
9. [Hearing Avtaar](#9-hearing-avtaar)
10. [The avatar and Avatar mode](#10-the-avatar-and-avatar-mode)
11. [Your conversations](#11-your-conversations)
12. [Settings reference](#12-settings-reference)
13. [Keyboard shortcuts](#13-keyboard-shortcuts)
14. [Privacy and your data](#14-privacy-and-your-data)
15. [Making it faster](#making-it-faster)
16. [Troubleshooting](#16-troubleshooting)
17. [Starting, stopping and uninstalling](#17-starting-stopping-and-uninstalling)

---

## 1. How it works

Avtaar is three programs working together on your computer:

| Part | What it does | Where |
|---|---|---|
| **Avtaar app** | The screen you use, plus a small local server that connects everything | http://127.0.0.1:8080 |
| **Ollama** | The "brain": a language model that writes the replies | http://127.0.0.1:11434 |
| **VoiceStudio** | The "voice and ears": turns text into speech, and your speech into text | http://127.0.0.1:3900 (usually in a container) |

You don't need to manage these separately. **Initial setup** installs, starts and checks them for you (see [section 4](#4-initial-setup)).

When you talk to Avtaar:

1. You click **Talk** and speak. VoiceStudio turns your speech into text, which appears in the message box.
2. The message is sent to Ollama, and the reply streams onto the screen word by word.
3. Each finished sentence goes to VoiceStudio and is spoken aloud. The avatar animates only while you can hear it.

---

## 2. Before you start

You need:

- **A Linux computer.** Avtaar was built and tested on Arch Linux; other systems are untested.
- **Python 3.11 or newer** and **Node.js 20 or newer.**
- **Ollama.** Installing it needs administrator rights, so do this one yourself:
  - Arch: `sudo pacman -S ollama` (or `ollama-cuda` for NVIDIA GPUs), then `sudo systemctl enable --now ollama`
  - Other systems: see https://ollama.com/download
- **Podman or Docker,** so setup can install VoiceStudio without administrator rights. Arch: `sudo pacman -S podman`.
- **About 20 GB of free disk space.** The VoiceStudio image is 11.6 GB and the speech models about 3 GB, plus your chat model (4–20 GB).
- **A microphone and speakers or headphones.** Headphones avoid Avtaar hearing itself.
- **An internet connection for the first setup only.** After that, Avtaar works offline.

> **About the voice licence:** Avtaar's default voice engine (OmniVoice) is free for **personal, non-commercial use** (CC-BY-NC). You'll be asked to accept this inside VoiceStudio. See [section 5](#accepting-the-voice-model-licence).

---

## 3. Installing

```bash
git clone https://github.com/prashlkam/plk-avtaar-local.git
cd plk-avtaar-local
make setup
make run
```

- `make setup` installs Avtaar's own dependencies (a Python environment and the web interface packages). It takes a minute or two.
- `make run` builds the interface and starts Avtaar. Leave this terminal open while you use it.

Then open **http://127.0.0.1:8080** in your browser. Chrome, Chromium, Firefox and Edge all work.

On first start you'll probably see an amber **"Voice is off"** banner. That's expected: run Initial setup next.

---

## 4. Initial setup

**Initial setup** installs, configures and tests everything Avtaar needs, in one click.

### Running it

1. Click **Settings** (bottom of the left sidebar).
2. In the **Initial setup** box at the top, click **Initial setup**.
3. Read the summary and click **Start setup**.

You can also open it from the **Run setup** button or the **Initial setup** link in a warning banner.

Each step shows its status as it runs:

| Icon | Meaning |
|---|---|
| ◯ | Waiting |
| spinner | Running. The line underneath shows what it's doing, e.g. a download percentage. |
| ✅ | Passed |
| ⚠️ | Works, but with a caveat. Click **Details** for advice. |
| ❌ | Failed. **Details** opens automatically with the fix. |
| – | Skipped because an earlier step it depends on didn't pass |

You can **close the dialog (Hide) while it runs**; setup carries on in the background. Open it again any time to see progress, or the results of the last run.

### The steps

| Step | What happens | If it fails |
|---|---|---|
| **App files and data folder** | Checks that Avtaar can save chats and settings | Check permissions on the `data/` folder |
| **Ollama installed** | Looks for Ollama | Install it (see [section 2](#2-before-you-start)) and run setup again |
| **Ollama running** | Starts Ollama if it isn't running | Run `sudo systemctl start ollama` yourself |
| **Language model downloaded** | Downloads your chosen chat model if it's missing (shows %) | Check your internet connection, or pick an installed model in Settings |
| **Language model answers** | Asks the model a test question and shows its speed in tokens per second | See [Troubleshooting](#16-troubleshooting) |
| **VoiceStudio installed** | Uses VoiceStudio if it's already running. Otherwise installs it as a container named `avtaar-voicestudio`. | Install Podman, or install VoiceStudio yourself (`yay -S voicestudio-bin`) |
| **VoiceStudio running** | Waits for VoiceStudio to start. The first start can take a few minutes. | Follow the hint to its log |
| **VoiceStudio connected** | Checks the connection and lists the available voices | — |
| **Speech-to-text model installed** | Installs a speech recognition model if VoiceStudio has none: Whisper small (0.5 GB) without a GPU | Install one in VoiceStudio's Model Catalogue |
| **Text-to-speech test** | Has VoiceStudio speak "Hello! Your local avatar is ready to talk." | Usually the licence: see [section 5](#accepting-the-voice-model-licence) |
| **Speech-to-text test** | Transcribes that phrase back and scores how many words matched | Try a bigger speech model, or set the spoken language |
| **Live transcription test** | Checks the live connection used by push-to-talk | A ⚠️ here is fine (see [section 8](#8-talking-to-avtaar)) |
| **Microphone (this browser)** | Asks for mic permission and listens for 1.5 s | Allow the microphone (see [Troubleshooting](#16-troubleshooting)) |
| **Speakers (this browser)** | Plays the test phrase | Check your volume and output device. Use **Play test phrase** to replay it. |

### How long it takes

- **First time:** 20–60 minutes, mostly downloads (VoiceStudio 11.6 GB, speech models about 3 GB, and your chat model if missing). The first voice test is also slow while the models load.
- **Later runs:** about 2 minutes.

### Running it again

Click **Run again (reconfigure & retest)** whenever:

- something stopped working,
- you changed the chat model, voice or language in Settings,
- you installed a GPU driver or the NVIDIA container toolkit,
- you restarted the computer and voice isn't working.

Running again **reconfigures** each part and **retests** it. If setup installed VoiceStudio, its container is recreated with the current settings. Downloaded models and accepted licences are kept, so nothing is downloaded twice.

### What setup will never do

- **Run anything with administrator rights.** Steps that need sudo tell you the exact command to run yourself.
- **Accept licences for you.**
- **Expose anything to your network.** VoiceStudio is published only on `127.0.0.1`, with analytics turned off.

---

<a id="accepting-the-voice-model-licence"></a>

## 5. Accepting the voice model licence

VoiceStudio won't speak until you accept the licence of its voice model. Until then the **Text-to-speech test** fails with *"Licence not accepted for k2-fsa/OmniVoice…"*.

**What you're agreeing to:**

| Model | Licence | In short |
|---|---|---|
| **k2-fsa/OmniVoice** (the voice) | CC-BY-NC, plus Higgs Audio 2 and Meta Llama 3 terms | **Non-commercial use only** |
| **eustlb/higgs-audio-v2-tokenizer** (part of the voice engine) | No licence declared upstream | Covered by the OmniVoice terms above |

**How to accept:**

1. Get VoiceStudio's admin key. Setup created it and stores it in `data/secrets.json`. This prints it without quotes:
   ```bash
   python3 -c 'import json; print(json.load(open("data/secrets.json"))["voicestudio_api_key"])'
   ```
   Run it from the Avtaar folder.
2. Open **http://127.0.0.1:3900** **on the same computer** that runs Avtaar.
3. VoiceStudio shows **"Remote backend: API key"**. Paste the key and click **Connect**.
4. Go to **Model Catalogue**, find **OmniVoice**, read the licence and accept it. Accept the tokenizer licence too if it's listed separately.
5. Back in Avtaar: **Settings → Initial setup → Run again**.

> **Tip:** If you open `127.0.0.1:3900` on a **different** computer, you're talking to that computer, not the one running Avtaar. Your acceptance won't count.

---

## 6. The screen at a glance

```
┌──────────────┬────────────────────────────────────────────┬──────────────┐
│ ☰  New chat ✎│ gemma4:latest ▾   (Loading model…)  ⤢ 🔊 ▯ │              │
│              │                                            │   (avatar)   │
│ Today        │        your messages (right, grey)         │              │
│  • chat 1    │  🙂 Avtaar's replies (left, formatted)     │    Avtaar    │
│  • chat 2    │     📋 🔊 🔄                                │   ● Ready    │
│ Yesterday    │                                            │ Voice on  ⤢  │
│  • …         │ ┌────────────────────────────────────────┐ │  "caption"   │
│              │ │ Ask anything…                          │ │              │
│ ⚙ Settings ☀ │ │                      🎤 Talk     ➤     │ │ LLM ● Voice ●│
└──────────────┴─┴────────────────────────────────────────┴─┴──────────────┘
```

| Area | What's there |
|---|---|
| **Left sidebar** | **New chat**, your past conversations grouped by day, **Settings**, and the light/dark switch. Collapse it with ☰. |
| **Header** | **Model picker** (which brain answers), a *Loading model…* spinner while it warms up, **⤢ Avatar mode**, **🔊 voice on/off**, **▯ show/hide avatar panel** |
| **Chat** | The conversation. Hover over a message to see its buttons. |
| **Message box** | Type here, or watch your speech appear. **🎤 Talk**, **➤ Send**, and **■ Stop** while it's replying or speaking. |
| **Avatar panel** (wide screens) | The avatar, its status, **Voice on/off**, **Avatar mode** or **Stop**, the sentence being spoken, and service status (LLM and Voice) |
| **Banners** (when needed) | Red: *Ollama is not reachable*. Amber: *Voice is off*. Each has **Retry** and a link to setup. |

On narrow windows the avatar panel is hidden. A small avatar floats over the chat while it's listening, thinking or speaking, and the sidebar slides over the chat.

---

## 7. Chatting by text

- **Send:** type in the box and press **Enter** (or click ➤). **Shift+Enter** starts a new line.
- **Watch the reply stream in.** Replies are formatted: lists, tables, **bold**, and code blocks with syntax colouring and a **Copy** button.
- **Stop a reply:** click **■** or press **Esc**. What it wrote so far is kept.
- **Message buttons** (hover over a message):

  | Button | On | Does |
  |---|---|---|
  | 📋 Copy | any message | Copies the text |
  | ✏️ Edit | your messages | Change your message and resend. Everything after it is replaced by a new reply. |
  | 🔊 Read aloud | Avtaar's messages | Speaks the message (click again to stop) |
  | 🔄 Regenerate | Avtaar's last reply | Writes a fresh answer to the same question |

- **Change the brain:** use the model picker in the header. Your choice is remembered, and the model is loaded in the background (*Loading model…*) so the first answer is quick. Smaller models answer faster; bigger ones are smarter.
- **Suggestions:** a new chat shows a few example questions. Click one to send it.

---

## 8. Talking to Avtaar

### Push-to-talk

1. Click **🎤 Talk**, or press **Ctrl+Space**. The first time, your browser asks for **microphone permission**: choose **Allow**.
2. The button turns red and says **Done**, the box says *Listening… start speaking*, and the avatar shows **Listening…** with a red ring. A light bar inside the button shows how loud you are.
3. Speak naturally.
4. **Finish** in any of these ways:
   - **Pause**: by default Avtaar stops listening after 1.5 s of silence,
   - click **Done**, or
   - press **Ctrl+Space** again.
5. Your words appear in the box and are **sent automatically**. Avtaar thinks, then answers out loud.

To **cancel** without sending, press **Esc** while listening. Anything you'd already typed in the box is put back.

### Live text vs. text when you're done

- With a **streaming** speech model, your words appear **as you speak**.
- With the default **Whisper** model (especially on a CPU), the text appears **when you finish**. The box shows *Transcribing…* briefly.

Both work the same otherwise. If the live connection isn't available, the button area says *Listening (will transcribe when you stop)*.

### Editing before sending

Prefer to check the text first? Turn off **Settings → Voice input → Send automatically when I click Done**. Your words then stay in the box. Fix anything, then press **Enter**.

### Interrupting (barge-in)

Click **Talk** (or press **Ctrl+Space**) while Avtaar is talking or still writing. It stops at once and starts listening to you. Its unfinished reply stays in the chat.

### Tips for good recognition

- Use **headphones** so Avtaar doesn't hear its own voice.
- Speak at a normal pace, about 30–50 cm from the mic.
- In a noisy room, set **Stop listening automatically** to a longer pause, or to **Off** and click **Done** yourself.
- If you speak a language other than English, set **Spoken language** (e.g. `hi`, `ta`, `fr`).
- A single recording is limited to 60 seconds.

---

## 9. Hearing Avtaar

- With **voice on** (🔊 in the header, or **Voice on** in the avatar panel), every reply is spoken **sentence by sentence while it's being written**. You don't have to wait for the whole answer.
- **Mute** with the same 🔊 button (it changes to a crossed-out speaker). Text replies continue as normal.
- **Stop speaking:** **■ Stop**, the **Stop** button in the avatar panel, or **Esc**.
- **Hear a message again:** 🔊 under any reply.
- **What isn't read out:** code blocks (Avtaar says *"I've put the code on screen."* once), link addresses (read as "a link"), emoji, and Markdown symbols.
- **Choose a voice and speed:** **Settings → Voice (VoiceStudio)**.

---

## 10. The avatar and Avatar mode

### What the avatar is doing

| Status | Ring | Image | Meaning |
|---|---|---|---|
| **Ready** | grey | still image | Waiting for you |
| **Listening…** | red | still image | Recording your voice |
| **Thinking…** | amber, with a bouncing "…" bubble | still image | Writing a reply, or preparing the next sentence's audio |
| **Speaking…** | green | **animated** | Its voice is playing |

The animation runs **only while you can actually hear the voice**. Between sentences you may briefly see **Thinking…** while the next sentence is prepared.

### Avatar mode (full screen)

Click **⤢** in the header, or **Avatar mode** in the avatar panel. You get:

- a large avatar,
- **captions**: the sentence it's saying, or your own words in grey while you talk,
- your last question at the top,
- one big **🎤** button (it turns red with a pulsing ring while listening), and **■** to stop.

Click **Exit avatar mode** (top right) to return. Avtaar remembers which view you used last. If voice is offline, a small text box appears at the bottom so you can still type.

### Using your own avatar

1. **Settings → Avtaar images.**
2. **Idle (static)** → **Choose…**: a still picture, shown most of the time.
3. **Talking (animated)** → **Choose…**: an **animated GIF or WebP**, shown only while speaking.
4. Done. The previews update immediately. **Use default** brings back the built-in face.

Tips:

- **Square images** work best; they're shown in a circle.
- Accepted formats: PNG, JPEG, GIF, WebP, up to 8 MB.
- Make both images match, for example the same character with mouth closed and mouth moving. A still frame of your GIF makes a good idle image:
  ```bash
  ffmpeg -i talking.gif -vframes 1 idle.png
  ```

---

## 11. Your conversations

- Every conversation is **saved automatically** on your computer and listed in the sidebar under *Today*, *Yesterday*, *Previous 7 days* and *Older*.
- **New chat:** the **New chat** button (or ✎ when the sidebar is collapsed).
- **Rename:** double-click a chat, or hover and click ✎. Type the name and press **Enter** (**Esc** cancels).
- **Delete:** hover and click 🗑, then confirm. **This can't be undone.**
- The first message becomes the chat's title automatically.

---

## 12. Settings reference

Open with **⚙ Settings** in the sidebar. Click **Save** to apply; **Cancel** discards changes. Avatar images apply as soon as you choose them.

| Setting | Default | What it does |
|---|---|---|
| **Initial setup** | — | Opens setup (see [section 4](#4-initial-setup)) |
| **Default model** | `gemma4:latest` | The chat model used for new chats |
| **System prompt / persona** | A friendly local companion that keeps answers short | Avtaar's personality and instructions. Keep it short and ask for brief answers, since they're spoken aloud. |
| **Temperature** | 0.7 | Lower is more focused and predictable; higher is more creative |
| **Voice** | `alloy` (VoiceStudio's default voice) | Which voice speaks. The list comes from VoiceStudio. |
| **Speed** | 1.00× | Speaking speed (0.5×–2×) |
| **TTS engine / model id** | `tts-1` | Leave as is: it means "VoiceStudio's active engine" |
| **Send automatically when I click Done** | On | Off: your spoken words wait in the box for you to edit |
| **Stop listening automatically** | After 1.5 s of silence | Off, 1, 1.5, 2.5 or 4 s |
| **Spoken language** | Auto-detect | A language code such as `en`, `hi`, `ta`, `fr`. Setting it improves accuracy. |
| **Avtaar images** | Built-in face | See [Using your own avatar](#using-your-own-avatar) |

Settings stored in your browser rather than in Avtaar: theme, sidebar and panel visibility, voice on/off, Avatar mode, and the last selected model.

---

## 13. Keyboard shortcuts

| Keys | Action |
|---|---|
| **Enter** | Send |
| **Shift+Enter** | New line |
| **Ctrl+Space** | Start talking / finish talking |
| **Esc** | While listening: cancel. While replying or speaking: stop. In dialogs: close. |
| **Double-click** a chat | Rename it |

---

## 14. Privacy and your data

**Nothing leaves your computer during normal use.**

- Avtaar, Ollama and VoiceStudio all listen only on `127.0.0.1`, so other devices on your network can't reach them.
- The page is locked so it can only talk to Avtaar itself, and other websites you have open can't control it.
- Avtaar hides Ollama's cloud models, and VoiceStudio runs with analytics turned off.
- The internet is used only by **Initial setup**, to download programs and models.

**Where things are stored:**

| What | Where |
|---|---|
| Conversations and settings | `data/app.db` |
| Your avatar images | `data/avatars/` |
| VoiceStudio admin key | `data/secrets.json` (readable only by you) |
| Last setup results and the test phrase audio | `data/setup_report.json`, `data/setup/` |
| Logs from programs setup started | `data/logs/` |
| VoiceStudio's models, voices and licence choices | the container volume `avtaar-voicestudio-data` |
| Chat models | Ollama's own folder (e.g. `/var/lib/ollama`) |

**To back up** your chats and avatars, copy the `data/` folder. **To erase everything Avtaar knows**, stop it and delete `data/`; setup recreates it.

---

<a id="making-it-faster"></a>

## 15. Making it faster

Voice speed depends mostly on your hardware.

| Symptom | Cause | Fix |
|---|---|---|
| 10–20 s before Avtaar starts speaking, with long pauses between sentences | VoiceStudio is running on the **CPU**. Setup shows ⚠️ *"running on the CPU"*. | Give the container your NVIDIA GPU (below) |
| Replies are written slowly (under ~10 words per second) | The chat model doesn't fit in your GPU's memory | Choose a smaller model (2–4 billion parameters) |
| Both slow | The chat model and the voice engine compete for the same CPU | Do both of the above, or use a smaller model |

**Letting the VoiceStudio container use an NVIDIA GPU** (needs administrator rights):

```bash
sudo pacman -S nvidia-container-toolkit
```
```bash
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
```

Then **Settings → Initial setup → Run again**. The *VoiceStudio installed* step should now say *running on the GPU*, and setup switches speech recognition to the more accurate large-v3-turbo model.

> With a small GPU (4 GB), the chat model and the voice engine may not both fit. If it gets slower, pick a smaller chat model.

**Other tips:**

- Keep answers short (the default persona already asks for this). Shorter replies are spoken sooner.
- The model is kept loaded for 30 minutes after use. The first message after a long break may take a few extra seconds.

---

## 16. Troubleshooting

**Start with Settings → Initial setup → Run again.** It finds and explains most problems.

| Problem | What to do |
|---|---|
| Red banner **"Ollama is not reachable"** | Run `sudo systemctl start ollama`, then **Retry**. If Ollama isn't installed, see [section 2](#2-before-you-start). |
| **"No models"** in the model picker | Run setup (it downloads the default model), or `ollama pull gemma4:latest` |
| Amber banner **"Voice is off"** | VoiceStudio isn't running, which is common after a reboot. Run setup, or start it with `podman start avtaar-voicestudio` (see [section 17](#17-starting-stopping-and-uninstalling)). |
| Text-to-speech test: **"Licence not accepted"** | See [Accepting the voice model licence](#accepting-the-voice-model-licence) |
| VoiceStudio's page asks for an **API key** | Use the key from `data/secrets.json` (command in [section 5](#accepting-the-voice-model-licence)). Make sure you're on the same computer. |
| Speech-to-text: **"No speech-to-text model is installed"** | Run setup; it installs one. Or install one in VoiceStudio's **Model Catalogue**. |
| **"Microphone permission was denied"** | Click the lock or mic icon in the address bar, allow the microphone for `127.0.0.1:8080`, reload, and try again |
| **"No microphone was found"** / **"The microphone is busy"** | Plug in or select a microphone in your system sound settings, and close other apps using it (video calls) |
| Mic check: **"picked up complete silence"** | The mic is muted, or the wrong input is selected in your system sound settings |
| **"I didn't catch that"** | Speak a little louder or longer. Set **Spoken language**. Try a longer auto-stop pause. |
| Your words appear only **when you finish**, not live | Normal with the Whisper model on a CPU. See [section 8](#live-text-vs-text-when-youre-done). |
| Avtaar stops listening **too early or too late** | **Settings → Stop listening automatically**: choose a longer or shorter pause, or Off |
| **No sound** from Avtaar | Check 🔊 isn't muted and your system volume/output. In setup, click **Play test phrase**. |
| **Long delay** before speaking | See [Making it faster](#making-it-faster) |
| The avatar doesn't animate | It animates only while audio plays. If you hear nothing, see *No sound*. If you hear audio but it stays still, reload the page. |
| Setup is stuck on **"Downloading VoiceStudio image"** | It's 11.6 GB, so this can take a long time on slow connections. Setup gives up only after 15 minutes with no progress. If it does, run it again: finished parts aren't downloaded twice. |
| Setup: **"Port 3900 is in use"** | Another program (e.g. a VoiceStudio desktop app) uses that port. Close it, or set `VOICESTUDIO_URL` in `.env` to another port and run setup again. |
| The page doesn't load at http://127.0.0.1:8080 | Is `make run` still running in a terminal? Start it again. |
| Something is badly wrong | Stop Avtaar, then run `podman rm -f avtaar-voicestudio`, then start Avtaar and run setup. Your chats and VoiceStudio's models are kept. |

**Checking services from a terminal:**

```bash
make services
```

**VoiceStudio's own log:**

```bash
podman logs --tail 50 avtaar-voicestudio
```

---

## 17. Starting, stopping and uninstalling

**Start Avtaar:** in the Avtaar folder, run `make run`, then open http://127.0.0.1:8080.

**Stop Avtaar:** press **Ctrl+C** in that terminal.

**VoiceStudio** keeps running in its container after you stop Avtaar. To stop or start it yourself:

```bash
podman stop avtaar-voicestudio
```
```bash
podman start avtaar-voicestudio
```

**After a reboot**, VoiceStudio does not start by itself unless Podman's restart service is enabled for your user. Either start it with the command above (or by running Initial setup), or enable the service once:

```bash
systemctl --user enable --now podman-restart.service
```

**Uninstall:**

1. Stop Avtaar (Ctrl+C).
2. Remove VoiceStudio's container, its data (models, voices, licence choices) and its image:
   ```bash
   podman rm -f avtaar-voicestudio
   ```
   ```bash
   podman volume rm avtaar-voicestudio-data
   ```
   ```bash
   podman rmi ghcr.io/debpalash/voicestudio:stable
   ```
3. Delete the Avtaar folder. This removes your chats and avatars too, so copy `data/` first if you want to keep them.
4. Ollama and its models are separate and stay installed. Remove models with `ollama rm <model>`.
