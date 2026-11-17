import { api, streamChat } from './api';
import { SentenceChunker, chunkText } from './audio/sentenceChunker';
import { Speaker } from './audio/speaker.svelte';
import { VoiceInput, join } from './audio/voiceInput.svelte';
import type { AvatarImages, AvatarState, Chat, ChatSummary, Health, Message, ModelInfo, Settings } from './types';

function load(key: string, fallback: string) {
	try {
		return localStorage.getItem(key) ?? fallback;
	} catch {
		return fallback;
	}
}
function save(key: string, value: string) {
	try {
		localStorage.setItem(key, value);
	} catch {
		/* storage unavailable */
	}
}

class AppState {
	chats = $state<ChatSummary[]>([]);
	current = $state<Chat | null>(null);
	models = $state<ModelInfo[]>([]);
	model = $state('');
	settings = $state<Settings | null>(null);
	health = $state<Health | null>(null);
	streaming = $state(false);
	/** Text in the prompt box (live transcript is written here while talking). */
	draft = $state('');
	voice = new VoiceInput();
	speaker = new Speaker();
	voiceOn = $state(load('avtaar.voice', '1') === '1');
	/** Message currently being read aloud via its 🔊 button. */
	readingId = $state<string | null>(null);
	toast = $state<{ kind: 'error' | 'info'; text: string } | null>(null);

	sidebarOpen = $state(load('avtaar.sidebar', '1') === '1');
	avatarOpen = $state(load('avtaar.avatarPanel', '1') === '1');
	dark = $state(load('avtaar.theme', 'dark') === 'dark');
	/** Full-screen, voice-first view: big Avtaar + live captions. */
	avatarMode = $state(load('avtaar.avatarMode', '0') === '1');
	avatarImages = $state<AvatarImages>({
		idle: '/avatar/idle.png',
		talking: '/avatar/talking.gif',
		custom: { idle: false, talking: false }
	});
	/** The Initial setup dialog. */
	setupOpen = $state(false);
	/** Model currently being loaded into memory, if any. */
	warming = $state<string | null>(null);

	private abort: AbortController | null = null;
	private toastTimer: ReturnType<typeof setTimeout> | undefined;

	private ttsErrorShown = false;
	/** Prompt text that was already in the box when the mic was opened. */
	private draftBase = '';

	constructor() {
		this.voice.onTranscript = (t) => {
			this.draft = join(this.draftBase, t);
		};
		this.voice.onAutoStop = (reason) => {
			if (reason === 'max-duration') this.notify('Stopped listening after 60 seconds.', 'info');
			if (this.voice.state === 'listening') void this.finishTalk();
		};
		this.speaker.onError = (e) => {
			if (this.ttsErrorShown) return;
			this.ttsErrorShown = true;
			this.notify(`Voice output failed: ${e.message}`);
			this.refreshHealth();
		};
	}

	get messages(): Message[] {
		return this.current?.messages ?? [];
	}

	/** The avatar's state. "speaking" is tied to audible playback, not to the LLM. */
	get avatar(): AvatarState {
		if (this.listening) return 'listening';
		if (this.speaker.speaking) return 'speaking';
		if (this.streaming || this.speaker.busy) return 'thinking';
		return 'idle';
	}

	get listening(): boolean {
		return this.voice.active;
	}

	get voiceAvailable(): boolean {
		return this.health?.voicestudio.ok ?? false;
	}

	get autoSend(): boolean {
		return this.settings?.auto_send ?? true;
	}

	/**
	 * The 🎤 button. First click: barge in (stop any reply/speech) and start listening;
	 * the live transcript fills the prompt box. Second click: finish, then auto-send
	 * (if enabled) or leave the text in the box for editing.
	 */
	async toggleTalk() {
		if (this.voice.state === 'starting' || this.voice.state === 'finishing') return;
		if (this.voice.state === 'listening') {
			await this.finishTalk();
			return;
		}
		if (!this.voiceAvailable) {
			this.notify('VoiceStudio is not running on :3900, so voice input is unavailable.');
			return;
		}
		this.speaker.unlock(); // we're inside the click, so later replies can play audio
		if (this.streaming || this.speaker.busy) this.stop();
		this.draftBase = this.draft;
		try {
			await this.voice.start({
				language: this.settings?.stt_language || undefined,
				autoStopMs: this.settings?.auto_stop_ms ?? 1500
			});
		} catch (e) {
			const err = e as DOMException;
			if (err.name === 'NotReadableError') {
				this.notify('The microphone is busy or unavailable. Is another app using it?');
			} else if (err.name === 'NotAllowedError' || err.name === 'SecurityError') {
				this.notify('Microphone permission was denied. Allow mic access for this page and try again.');
			} else if (err.name === 'NotFoundError' || err.name === 'OverconstrainedError') {
				this.notify('No microphone was found.');
			} else {
				this.notify(`Could not start the microphone: ${err.message || err.name}`);
			}
		}
	}

	private async finishTalk() {
		let text = '';
		try {
			text = await this.voice.stop();
		} catch (e) {
			this.notify((e as Error).message);
		}
		this.draft = join(this.draftBase, text);
		this.draftBase = '';
		if (!text) {
			this.notify("I didn't catch that. Try again?", 'info');
			return;
		}
		if (this.autoSend && this.draft.trim()) {
			const msg = this.draft;
			this.draft = '';
			await this.send(msg);
		}
	}

	cancelTalk() {
		this.voice.cancel();
		this.draft = this.draftBase;
		this.draftBase = '';
	}

	toggleVoice() {
		this.voiceOn = !this.voiceOn;
		save('avtaar.voice', this.voiceOn ? '1' : '0');
		if (!this.voiceOn) this.stopSpeaking();
	}

	stopSpeaking() {
		this.speaker.stop();
		this.readingId = null;
	}

	/** 🔊 on a message: read it aloud (or stop if it is already being read). */
	readAloud(m: Message) {
		if (this.readingId === m.id && this.speaker.busy) {
			this.stopSpeaking();
			return;
		}
		if (!this.voiceAvailable) {
			this.notify('VoiceStudio is not running on :3900, so voice output is unavailable.');
			return;
		}
		this.speaker.unlock();
		this.ttsErrorShown = false;
		this.readingId = m.id;
		this.speaker.speakAll(chunkText(m.content));
	}

	async init() {
		await Promise.allSettled([this.refreshHealth(), this.refreshChats(), this.loadSettings(), this.loadAvatar()]);
		await this.refreshModels();
		void this.warmup();
		this.scheduleHealth();
	}

	private healthTimer: ReturnType<typeof setTimeout> | undefined;
	/** Poll health: every 5 s while something is down (so recovery is noticed fast), else every 20 s. */
	private scheduleHealth() {
		clearTimeout(this.healthTimer);
		const allUp = this.health?.ollama.ok && this.health?.voicestudio.ok;
		this.healthTimer = setTimeout(async () => {
			const wasOllama = this.health?.ollama.ok;
			const wasVoice = this.health?.voicestudio.ok;
			await this.refreshHealth();
			if (!wasOllama && this.health?.ollama.ok) {
				await this.refreshModels();
				this.notify('Ollama is back online', 'info');
				void this.warmup();
			}
			if (wasVoice === false && this.health?.voicestudio.ok) this.notify('VoiceStudio connected: voice is ready', 'info');
			this.scheduleHealth();
		}, allUp ? 20000 : 5000);
	}

	/** "Retry" in the service banner. */
	async recheck() {
		await this.refreshHealth();
		if (this.health?.ollama.ok && !this.models.length) await this.refreshModels();
		this.scheduleHealth();
	}

	notify(text: string, kind: 'error' | 'info' = 'error') {
		this.toast = { kind, text };
		clearTimeout(this.toastTimer);
		this.toastTimer = setTimeout(() => (this.toast = null), 6000);
	}

	async refreshHealth() {
		try {
			this.health = await api.health();
		} catch {
			this.health = {
				ok: false,
				ollama: { ok: false, url: '', error: 'Gateway not reachable', hint: 'Start the backend: make dev' },
				voicestudio: { ok: false, url: '', error: 'Gateway not reachable' }
			};
		}
	}

	async refreshModels() {
		try {
			const r = await api.models();
			this.models = r.models;
			const saved = load('avtaar.model', '');
			const names = r.models.map((m) => m.name);
			this.model = [saved, r.default, names[0]].find((n) => n && names.includes(n)) ?? r.default;
		} catch (e) {
			this.models = [];
		}
	}

	setModel(name: string) {
		this.model = name;
		save('avtaar.model', name);
		void this.warmup();
	}

	/** Load the selected model into memory in the background so the first reply is quick. */
	async warmup() {
		const model = this.model;
		if (!model || this.warming === model || !this.health?.ollama.ok) return;
		this.warming = model;
		try {
			await api.warmup(model);
		} catch (e) {
			if (this.model === model) this.notify((e as Error).message);
		} finally {
			if (this.warming === model) this.warming = null;
		}
	}

	async loadAvatar() {
		try {
			this.avatarImages = await api.avatar();
		} catch {
			/* keep defaults */
		}
	}

	async uploadAvatar(kind: 'idle' | 'talking', file: File) {
		try {
			this.avatarImages = await api.uploadAvatar(kind, file);
			this.notify(kind === 'idle' ? 'Idle image updated' : 'Talking animation updated', 'info');
		} catch (e) {
			this.notify(`Could not use that image: ${(e as Error).message}`);
		}
	}

	async resetAvatar(kind: 'idle' | 'talking') {
		this.avatarImages = await api.resetAvatar(kind);
	}

	toggleAvatarMode() {
		this.avatarMode = !this.avatarMode;
		save('avtaar.avatarMode', this.avatarMode ? '1' : '0');
	}

	async loadSettings() {
		this.settings = await api.settings();
	}

	async saveSettings(s: Partial<Settings>) {
		this.settings = await api.saveSettings(s);
		this.notify('Settings saved', 'info');
	}

	async refreshChats() {
		this.chats = await api.chats();
	}

	async openChat(id: string) {
		if (this.voice.active) this.cancelTalk();
		if (this.streaming) this.stop();
		this.stopSpeaking();
		try {
			this.current = await api.chat(id);
		} catch (e) {
			this.notify(`Could not open chat: ${(e as Error).message}`);
		}
	}

	newChat() {
		if (this.voice.active) this.cancelTalk();
		if (this.streaming) this.stop();
		this.stopSpeaking();
		this.current = null;
	}

	async renameChat(id: string, title: string) {
		const t = title.trim();
		if (!t) return;
		await api.renameChat(id, t);
		if (this.current?.id === id) this.current.title = t;
		await this.refreshChats();
	}

	async deleteChat(id: string) {
		await api.deleteChat(id);
		if (this.current?.id === id) this.current = null;
		await this.refreshChats();
	}

	toggleSidebar() {
		this.sidebarOpen = !this.sidebarOpen;
		save('avtaar.sidebar', this.sidebarOpen ? '1' : '0');
	}
	toggleAvatar() {
		this.avatarOpen = !this.avatarOpen;
		save('avtaar.avatarPanel', this.avatarOpen ? '1' : '0');
	}
	toggleTheme() {
		this.dark = !this.dark;
		document.documentElement.classList.toggle('dark', this.dark);
		save('avtaar.theme', this.dark ? 'dark' : 'light');
	}

	/** Stop everything: the LLM stream and any speech. */
	stop() {
		this.abort?.abort();
		this.stopSpeaking();
	}

	/** Send a new user message (or edit/regenerate) and stream the reply. */
	async send(content: string, opts: { replaceFrom?: string; regenerate?: boolean } = {}) {
		if (this.streaming) return;
		content = content.trim();
		if (!content && !opts.regenerate) return;
		if (!this.model) {
			this.notify('No model available. Is Ollama running?');
			return;
		}

		// Called synchronously from the click/Enter handler, so audio may start later.
		this.speaker.unlock();
		this.stopSpeaking();
		const speak = this.voiceOn && this.voiceAvailable;
		const chunker = speak ? new SentenceChunker() : null;
		if (speak) {
			this.ttsErrorShown = false;
			this.speaker.begin();
		}

		if (!this.current) {
			this.current = { id: '', title: 'New chat', model: this.model, created_at: 0, updated_at: 0, messages: [] };
		}
		const chat = this.current;

		// Optimistic local update mirrors what the server does.
		if (opts.replaceFrom) {
			const i = chat.messages.findIndex((m) => m.id === opts.replaceFrom);
			if (i >= 0) chat.messages.splice(i);
		}
		const now = Date.now() / 1000;
		if (!opts.regenerate) {
			chat.messages.push({ id: `tmp-user-${now}`, role: 'user', content, created_at: now });
		}
		chat.messages.push({
			id: `tmp-asst-${now}`,
			role: 'assistant',
			content: '',
			model: this.model,
			created_at: now,
			streaming: true
		});
		const userLocal = opts.regenerate ? null : chat.messages[chat.messages.length - 2];
		const asst = chat.messages[chat.messages.length - 1];

		this.streaming = true;
		this.abort = new AbortController();
		const signal = this.abort.signal;
		const isNew = !chat.id;

		try {
			await streamChat(
				{
					chat_id: chat.id || null,
					model: this.model,
					content,
					replace_from: opts.replaceFrom,
					regenerate: opts.regenerate
				},
				{
					onMeta: (d) => {
						chat.id = d.chat_id;
						chat.title = d.title;
						if (userLocal && d.user_message) userLocal.id = d.user_message.id;
						if (isNew) this.refreshChats();
					},
					onToken: (t) => {
						asst.content += t;
						if (chunker && this.voiceOn) for (const c of chunker.push(t)) this.speaker.enqueue(c);
					},
					onDone: (d) => {
						if (d.assistant_message) asst.id = d.assistant_message.id;
					},
					onError: (d) => {
						if (d.assistant_message) asst.id = d.assistant_message.id;
						asst.error = d.message;
					}
				},
				signal
			);
		} catch (e) {
			if ((e as Error).name !== 'AbortError') {
				asst.error = (e as Error).message;
			}
		} finally {
			asst.streaming = false;
			this.streaming = false;
			this.abort = null;
			if (chunker && !signal.aborted && this.voiceOn) {
				for (const c of chunker.flush()) this.speaker.enqueue(c);
				this.speaker.end();
			}
			// Re-sync ids (e.g. partial reply saved on Stop) from the server.
			if (chat.id && this.current === chat) {
				const err = asst.error;
				try {
					const fresh = await api.chat(chat.id);
					chat.messages = fresh.messages;
					if (err) {
						const last = chat.messages.at(-1);
						if (last?.role === 'assistant') last.error = err;
						else chat.messages.push({ id: `err-${now}`, role: 'assistant', content: '', created_at: now, error: err });
					}
				} catch {
					/* keep local copy */
				}
			}
			this.refreshChats();
		}
	}
}

export const app = new AppState();
