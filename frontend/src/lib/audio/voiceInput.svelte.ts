/**
 * Push-to-talk recorder.
 *
 *  start(): mic -> MediaRecorder (WebM/Opus, 250 ms slices) -> /ws/stt (live partials)
 *  stop():  sends {"type":"input_audio.end"}, waits for the final transcript.
 *
 * Every slice is also kept locally, so if the live socket is unavailable or fails
 * mid-way, stop() falls back to uploading the whole recording to /api/stt.
 */

import { SilenceDetector } from './silenceDetector';

export type VoiceInputState = 'idle' | 'starting' | 'listening' | 'finishing';

export interface StreamFrame {
	type: string;
	text?: string;
	final_kind?: 'utterance' | 'summary';
	message?: string;
	code?: string;
}

/** Accumulates live STT frames into the current transcript. Pure, for testing. */
export class TranscriptBuilder {
	committed = '';
	partial = '';
	summary: string | null = null;

	apply(f: StreamFrame): void {
		if (f.type === 'partial') this.partial = (f.text ?? '').trim();
		else if (f.type === 'final' && f.final_kind === 'summary') {
			this.summary = (f.text ?? '').trim();
			this.partial = '';
		} else if (f.type === 'final') {
			this.committed = join(this.committed, f.text ?? '');
			this.partial = '';
		}
	}

	get text(): string {
		// The summary is the authoritative full transcript once it arrives.
		if (this.summary !== null && this.summary !== '') return this.summary;
		return join(this.committed, this.partial);
	}
}

export function join(a: string, b: string): string {
	a = a.trim();
	b = b.trim();
	return a && b ? `${a} ${b}` : a || b;
}

function pickMime(): string {
	if (typeof MediaRecorder === 'undefined') return '';
	for (const m of ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']) {
		if (MediaRecorder.isTypeSupported(m)) return m;
	}
	return '';
}

export class VoiceInput {
	state = $state<VoiceInputState>('idle');
	/** Mic input level 0..1 for the meter. */
	level = $state(0);
	/** Live transcript so far (partials included). */
	transcript = $state('');
	/** false once we have fallen back to batch transcription for this recording. */
	live = $state(true);

	onTranscript: (text: string) => void = () => {};
	/** Called once when silence (or the max duration) should end the recording. */
	onAutoStop: (reason: 'silence' | 'max-duration') => void = () => {};

	private detector: SilenceDetector | null = null;

	private stream: MediaStream | null = null;
	private recorder: MediaRecorder | null = null;
	private ws: WebSocket | null = null;
	private chunks: Blob[] = [];
	private mime = '';
	private builder = new TranscriptBuilder();
	private wsReady = false;
	private wsFailed = false;
	private finalResolve: (() => void) | null = null;
	private meterCtx: AudioContext | null = null;
	private raf = 0;

	get active() {
		return this.state !== 'idle';
	}

	async start(opts: { language?: string; autoStopMs?: number } = {}): Promise<void> {
		if (this.state !== 'idle') return;
		this.state = 'starting';
		this.reset();
		this.detector = new SilenceDetector(opts.autoStopMs ?? 0);
		try {
			this.stream = await navigator.mediaDevices.getUserMedia({
				audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 }
			});
		} catch (e) {
			this.state = 'idle';
			throw e;
		}

		try {
			if (!this.stream.getAudioTracks().some((t) => t.readyState === 'live')) {
				throw new DOMException('The microphone stream is not live', 'NotReadableError');
			}
			this.mime = pickMime();
			this.recorder = new MediaRecorder(this.stream, this.mime ? { mimeType: this.mime } : undefined);
			this.mime = this.recorder.mimeType || this.mime || 'audio/webm';

			this.recorder.ondataavailable = (e) => {
				if (!e.data.size) return;
				this.chunks.push(e.data);
				// Before session.started, slices are only buffered; they are replayed once the session opens.
				if (this.wsReady && !this.wsFailed && this.ws?.readyState === WebSocket.OPEN) this.ws.send(e.data);
			};
			this.recorder.start(250);

			// Live streaming only for WebM/Opus (VoiceStudio's default container).
			if (this.mime.startsWith('audio/webm')) this.openSocket(opts.language);
			else this.markFallback();

			this.startMeter();
			this.state = 'listening';
		} catch (e) {
			// Never leave the UI stuck in "starting".
			this.cancel();
			throw e;
		}
	}

	/** Stop recording and resolve with the final transcript ('' if nothing was heard). */
	async stop(): Promise<string> {
		if (this.state !== 'listening') return this.builder.text;
		this.state = 'finishing';
		this.stopMeter();

		await this.stopRecorder();
		this.stream?.getTracks().forEach((t) => t.stop());

		try {
			if (this.ws && this.wsReady && !this.wsFailed && this.ws.readyState === WebSocket.OPEN) {
				const gotFinal = new Promise<void>((r) => (this.finalResolve = r));
				this.ws.send(JSON.stringify({ type: 'input_audio.end' }));
				await Promise.race([gotFinal, new Promise((r) => setTimeout(r, 4000))]);
			}
			const liveUsable = this.wsReady && !this.wsFailed;
			this.closeSocket();

			let text = this.builder.text;
			if (!liveUsable && this.chunks.length) {
				// Live STT never started or broke mid-way: transcribe the whole recording instead.
				this.markFallback();
				text = await this.transcribeBatch();
			}
			this.transcript = text;
			return text;
		} finally {
			this.closeSocket();
			this.state = 'idle';
		}
	}

	/** Abort without transcribing. */
	cancel() {
		this.stopMeter();
		try {
			this.recorder?.state !== 'inactive' && this.recorder?.stop();
		} catch {
			/* ignore */
		}
		this.stream?.getTracks().forEach((t) => t.stop());
		this.stream = null;
		this.recorder = null;
		this.closeSocket();
		this.state = 'idle';
	}

	private reset() {
		this.chunks = [];
		this.builder = new TranscriptBuilder();
		this.transcript = '';
		this.live = true;
		this.wsReady = false;
		this.wsFailed = false;
		this.finalResolve = null;
	}

	private openSocket(language?: string) {
		const proto = location.protocol === 'https:' ? 'wss' : 'ws';
		const qs = language ? `?language=${encodeURIComponent(language)}` : '';
		const ws = new WebSocket(`${proto}://${location.host}/ws/stt${qs}`);
		this.ws = ws;
		ws.onmessage = (ev) => {
			if (typeof ev.data !== 'string') return;
			let f: StreamFrame;
			try {
				f = JSON.parse(ev.data);
			} catch {
				return;
			}
			if (f.type === 'session.started') {
				this.wsReady = true;
				// Catch up on audio recorded before the session opened (incl. the WebM header).
				for (const c of this.chunks) ws.send(c);
				return;
			}
			if (f.type === 'error') {
				this.markFallback();
				return;
			}
			this.builder.apply(f);
			this.transcript = this.builder.text;
			this.onTranscript(this.transcript);
			if (f.type === 'final' && f.final_kind === 'summary') this.finalResolve?.();
		};
		ws.onerror = () => this.markFallback();
		ws.onclose = () => {
			// Closing before the session opened, or while still recording, means live STT failed.
			if (!this.wsReady || this.state === 'listening') this.markFallback();
			this.finalResolve?.();
		};
	}

	private markFallback() {
		this.wsFailed = true;
		this.live = false;
	}

	private closeSocket() {
		if (!this.ws) return;
		this.ws.onclose = this.ws.onerror = this.ws.onmessage = null;
		try {
			this.ws.close();
		} catch {
			/* ignore */
		}
		this.ws = null;
	}

	private stopRecorder(): Promise<void> {
		const rec = this.recorder;
		if (!rec || rec.state === 'inactive') return Promise.resolve();
		return new Promise((resolve) => {
			// The final dataavailable fires before stop.
			rec.addEventListener('stop', () => setTimeout(resolve, 0), { once: true });
			rec.stop();
		});
	}

	private async transcribeBatch(): Promise<string> {
		const blob = new Blob(this.chunks, { type: this.mime });
		const ext = this.mime.includes('ogg') ? 'ogg' : 'webm';
		const form = new FormData();
		form.append('file', blob, `speech.${ext}`);
		const res = await fetch('/api/stt', { method: 'POST', body: form });
		if (!res.ok) {
			let detail = `${res.status}`;
			try {
				detail = (await res.json()).detail ?? detail;
			} catch {
				/* ignore */
			}
			throw new Error(`Transcription failed: ${detail}`);
		}
		return ((await res.json()).text ?? '').trim();
	}

	private startMeter() {
		if (!this.stream || typeof AudioContext === 'undefined') return;
		const ctx = new AudioContext();
		this.meterCtx = ctx;
		const analyser = ctx.createAnalyser();
		analyser.fftSize = 512;
		ctx.createMediaStreamSource(this.stream).connect(analyser);
		const data = new Uint8Array(analyser.fftSize);
		const tick = () => {
			analyser.getByteTimeDomainData(data);
			let sum = 0;
			for (const v of data) sum += ((v - 128) / 128) ** 2;
			const rms = Math.sqrt(sum / data.length);
			this.level = Math.min(1, this.level * 0.6 + Math.min(1, rms * 4) * 0.4);
			const ev = this.state === 'listening' ? this.detector?.feed(rms, performance.now()) : null;
			if (ev) {
				this.detector = null; // fire once
				this.onAutoStop(ev);
				return;
			}
			this.raf = requestAnimationFrame(tick);
		};
		tick();
	}

	private stopMeter() {
		cancelAnimationFrame(this.raf);
		this.level = 0;
		void this.meterCtx?.close();
		this.meterCtx = null;
	}
}
