/**
 * Speaker: fetches TTS audio for text chunks (pipelined), plays them strictly in
 * order and gaplessly through one AudioContext, and exposes `speaking` — true only
 * while audio is actually audible. The avatar GIF is bound to that flag.
 */

export type FetchAudio = (text: string, signal: AbortSignal) => Promise<ArrayBuffer>;

interface Item {
	text: string;
	audio?: Promise<AudioBuffer | null>;
	started: boolean;
}

export const fetchTTS: FetchAudio = async (text, signal) => {
	const res = await fetch('/api/tts', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ text, format: 'wav' }),
		signal
	});
	if (!res.ok) {
		let detail = `${res.status}`;
		try {
			detail = (await res.json()).detail ?? detail;
		} catch {
			/* ignore */
		}
		throw new Error(detail);
	}
	return res.arrayBuffer();
};

export class Speaker {
	/** True while audio is audible (with a short hold across sentence gaps). */
	speaking = $state(false);
	/** True from the first enqueue until everything queued has finished playing. */
	busy = $state(false);
	/** Text of the sentence currently audible (for captions). */
	caption = $state('');

	onError: (err: Error) => void = () => {};

	private ctx: AudioContext | null = null;
	private queue: Item[] = [];
	private sources = new Set<AudioBufferSourceNode>();
	private nextStart = 0;
	private generation = 0;
	private abort = new AbortController();
	private playing = false;
	private ended = true;
	private holdTimer: ReturnType<typeof setTimeout> | undefined;
	private startTimers = new Set<ReturnType<typeof setTimeout>>();

	constructor(
		private fetchAudio: FetchAudio = fetchTTS,
		private prefetch = 2,
		/** Seconds of audio to keep scheduled ahead of playback. */
		private lookahead = 2
	) {}

	/** Must be called from a user gesture at least once (browser autoplay policy). */
	unlock() {
		if (typeof AudioContext === 'undefined') return;
		this.ctx ??= new AudioContext();
		if (this.ctx.state === 'suspended') void this.ctx.resume();
	}

	/** Begin a new utterance stream (e.g. one assistant reply). Stops anything playing. */
	begin() {
		this.stop();
		this.ended = false;
		this.busy = true;
	}

	enqueue(text: string) {
		if (!text.trim()) return;
		this.queue.push({ text, started: false });
		this.busy = true;
		this.pump();
		void this.play();
	}

	/** No more chunks will be added for this utterance. */
	end() {
		this.ended = true;
		this.checkIdle();
	}

	/** Speak a complete list of chunks (read-aloud). */
	speakAll(chunks: string[]) {
		this.begin();
		for (const c of chunks) this.enqueue(c);
		this.end();
	}

	stop() {
		this.generation++;
		this.abort.abort();
		this.abort = new AbortController();
		this.queue = [];
		for (const s of this.sources) {
			s.onended = null;
			try {
				s.stop();
			} catch {
				/* already stopped */
			}
		}
		this.sources.clear();
		for (const t of this.startTimers) clearTimeout(t);
		this.startTimers.clear();
		clearTimeout(this.holdTimer);
		this.playing = false;
		this.ended = true;
		this.nextStart = 0;
		this.speaking = false;
		this.busy = false;
		this.caption = '';
	}

	/** Start fetching up to `prefetch` chunks ahead of playback. */
	private pump() {
		const gen = this.generation;
		const signal = this.abort.signal;
		let inFlightOrReady = 0;
		for (const item of this.queue) {
			if (item.started) continue;
			if (item.audio) {
				inFlightOrReady++;
				continue;
			}
			if (inFlightOrReady >= this.prefetch) break;
			inFlightOrReady++;
			item.audio = this.fetchAudio(item.text, signal)
				.then((buf) => (gen === this.generation ? this.decode(buf) : null))
				.catch((e: Error) => {
					if (e.name !== 'AbortError' && gen === this.generation) this.onError(e);
					return null;
				});
		}
	}

	private async decode(buf: ArrayBuffer): Promise<AudioBuffer | null> {
		this.unlock();
		if (!this.ctx) return null;
		return this.ctx.decodeAudioData(buf);
	}

	private async play() {
		if (this.playing) return;
		this.playing = true;
		const gen = this.generation;
		try {
			while (gen === this.generation) {
				const item = this.queue.find((i) => !i.started);
				if (!item) break;
				// Don't run far ahead of the listener: keeps VoiceStudio (and the GPU the LLM
				// shares) from synthesising a whole long reply up front.
				while (this.ctx && this.nextStart - this.ctx.currentTime > this.lookahead) {
					await new Promise((r) => setTimeout(r, 150));
					if (gen !== this.generation) return;
				}
				if (!item.audio) this.pump();
				const audio = await item.audio;
				if (gen !== this.generation) return;
				item.started = true;
				this.queue = this.queue.filter((i) => i !== item);
				if (audio) this.schedule(audio, item.text);
				this.pump();
			}
		} finally {
			if (gen === this.generation) {
				this.playing = false;
				this.checkIdle();
			}
		}
	}

	private schedule(buffer: AudioBuffer, text: string) {
		const ctx = this.ctx!;
		const src = ctx.createBufferSource();
		src.buffer = buffer;
		src.connect(ctx.destination);
		const at = Math.max(ctx.currentTime + 0.02, this.nextStart);
		this.nextStart = at + buffer.duration;
		this.sources.add(src);
		src.onended = () => {
			this.sources.delete(src);
			this.checkIdle();
		};
		src.start(at);
		// Flip the avatar exactly when the sound becomes audible.
		const delay = Math.max(0, (at - ctx.currentTime) * 1000);
		const t = setTimeout(() => {
			this.startTimers.delete(t);
			clearTimeout(this.holdTimer);
			this.speaking = true;
			this.caption = text;
		}, delay);
		this.startTimers.add(t);
	}

	private checkIdle() {
		if (this.sources.size > 0) return;
		const moreComing = this.queue.length > 0 || !this.ended || this.playing;
		clearTimeout(this.holdTimer);
		// Hold the talking state briefly across small gaps between sentences.
		this.holdTimer = setTimeout(
			() => {
				if (this.sources.size === 0) {
					this.speaking = false;
					if (!moreComing) this.caption = '';
				}
			},
			moreComing ? 400 : 0
		);
		if (!moreComing) this.busy = false;
	}
}
