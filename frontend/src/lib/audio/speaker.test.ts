import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Speaker } from './speaker.svelte';

// Minimal fake Web Audio: records the order and start time of scheduled buffers.
const played: { label: string; at: number }[] = [];
class FakeSource {
	buffer: { label: string; duration: number } | null = null;
	onended: (() => void) | null = null;
	connect() {}
	start(at: number) {
		played.push({ label: this.buffer!.label, at });
		setTimeout(() => this.onended?.(), this.buffer!.duration * 1000);
	}
	stop() {}
}
class FakeAudioContext {
	state = 'running';
	currentTime = 0;
	destination = {};
	resume() {}
	createBufferSource() {
		return new FakeSource();
	}
	async decodeAudioData(buf: ArrayBuffer) {
		return { label: new TextDecoder().decode(buf), duration: 0.05 };
	}
}

beforeEach(() => {
	played.length = 0;
	vi.stubGlobal('AudioContext', FakeAudioContext);
});
afterEach(() => vi.unstubAllGlobals());

const enc = (s: string) => new TextEncoder().encode(s).buffer as ArrayBuffer;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe('Speaker', () => {
	it('plays chunks in order even when TTS responses arrive out of order', async () => {
		const delays: Record<string, number> = { one: 60, two: 5, three: 20 };
		const sp = new Speaker(async (t) => {
			await sleep(delays[t]);
			return enc(t);
		}, 3);
		sp.unlock();
		sp.begin();
		for (const t of ['one', 'two', 'three']) sp.enqueue(t);
		sp.end();
		await vi.waitFor(() => expect(played.length).toBe(3), { timeout: 1000 });
		expect(played.map((p) => p.label)).toEqual(['one', 'two', 'three']);
		// gapless: each starts where the previous ends
		expect(played[1].at).toBeCloseTo(played[0].at + 0.05);
		expect(played[2].at).toBeCloseTo(played[1].at + 0.05);
		await vi.waitFor(() => expect(sp.busy).toBe(false), { timeout: 1000 });
	});

	it('limits concurrent TTS requests to the prefetch window', async () => {
		let inFlight = 0;
		let maxInFlight = 0;
		const sp = new Speaker(async (t) => {
			inFlight++;
			maxInFlight = Math.max(maxInFlight, inFlight);
			await sleep(10);
			inFlight--;
			return enc(t);
		}, 2);
		sp.unlock();
		sp.speakAll(['a', 'b', 'c', 'd', 'e']);
		await vi.waitFor(() => expect(played.length).toBe(5), { timeout: 2000 });
		expect(maxInFlight).toBeLessThanOrEqual(2);
	});

	it('skips a failed chunk, reports it, and keeps going', async () => {
		const errors: string[] = [];
		const sp = new Speaker(async (t) => {
			if (t === 'bad') throw new Error('boom');
			return enc(t);
		});
		sp.onError = (e) => errors.push(e.message);
		sp.unlock();
		sp.speakAll(['ok1', 'bad', 'ok2']);
		await vi.waitFor(() => expect(played.length).toBe(2), { timeout: 1000 });
		expect(played.map((p) => p.label)).toEqual(['ok1', 'ok2']);
		expect(errors).toEqual(['boom']);
	});

	it('keeps only ~lookahead seconds scheduled ahead of playback', async () => {
		let fetched = 0;
		const sp = new Speaker(
			async (t) => {
				fetched++;
				return enc(t);
			},
			2,
			0.1 // seconds; each fake buffer is 0.05s, first starts at 0.02
		);
		sp.unlock();
		sp.speakAll(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']);
		await sleep(400);
		// Clock is frozen at 0, so scheduling must stall once 0.12s is queued (> 0.1s window).
		expect(played.length).toBe(2);
		expect(fetched).toBeLessThanOrEqual(2 + 2);
		const ctx = (sp as unknown as { ctx: FakeAudioContext }).ctx;
		const clock = setInterval(() => (ctx.currentTime += 0.05), 20); // time passes -> the rest gets scheduled
		await vi.waitFor(() => expect(played.length).toBe(8), { timeout: 3000 });
		clearInterval(clock);
		expect(played.map((p) => p.label).join('')).toBe('abcdefgh');
		sp.stop();
	});

	it('stop() drops queued audio and pending fetches', async () => {
		const sp = new Speaker(async (t, signal) => {
			await sleep(30);
			if (signal.aborted) throw Object.assign(new Error('aborted'), { name: 'AbortError' });
			return enc(t);
		});
		sp.unlock();
		sp.speakAll(['x', 'y']);
		sp.stop();
		await sleep(80);
		expect(played).toEqual([]);
		expect(sp.busy).toBe(false);
		expect(sp.speaking).toBe(false);
	});
});
