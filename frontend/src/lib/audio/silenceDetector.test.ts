import { describe, expect, it } from 'vitest';
import { SilenceDetector } from './silenceDetector';

/** Feed a level for `ms` milliseconds at 16 ms steps; return the first event. */
function run(d: SilenceDetector, clock: { t: number }, level: number, ms: number) {
	for (const end = clock.t + ms; clock.t < end; clock.t += 16) {
		const ev = d.feed(level, clock.t);
		if (ev) return ev;
	}
	return null;
}

describe('SilenceDetector', () => {
	it('stops after speech followed by enough silence', () => {
		const d = new SilenceDetector(1500);
		const c = { t: 0 };
		expect(run(d, c, 0.005, 500)).toBeNull(); // room noise
		expect(run(d, c, 0.2, 1200)).toBeNull(); // speaking
		expect(d.heardSpeech).toBe(true);
		expect(run(d, c, 0.005, 1000)).toBeNull(); // short pause: keep listening
		expect(run(d, c, 0.2, 600)).toBeNull(); // speaks again
		expect(run(d, c, 0.005, 2000)).toBe('silence');
	});

	it('never stops if the user has not spoken yet', () => {
		const d = new SilenceDetector(1000);
		expect(run(d, { t: 0 }, 0.004, 8000)).toBeNull();
	});

	it('ignores short clicks', () => {
		const d = new SilenceDetector(800);
		const c = { t: 0 };
		run(d, c, 0.005, 300);
		run(d, c, 0.5, 64); // a click
		expect(run(d, c, 0.005, 2000)).toBeNull();
		expect(d.heardSpeech).toBe(false);
	});

	it('adapts to a noisy room', () => {
		const d = new SilenceDetector(1000);
		const c = { t: 0 };
		// Steady fan noise well above the minimum threshold.
		expect(run(d, c, 0.04, 3000)).toBeNull();
		expect(d.heardSpeech).toBe(false);
		expect(d.threshold).toBeGreaterThan(0.1);
		expect(run(d, c, 0.3, 800)).toBeNull();
		expect(run(d, c, 0.04, 1500)).toBe('silence');
	});

	it('is disabled with silenceMs = 0 but still enforces the max duration', () => {
		const d = new SilenceDetector(0, { maxMs: 5000 });
		const c = { t: 0 };
		run(d, c, 0.2, 1000);
		expect(run(d, c, 0.0, 3000)).toBeNull();
		expect(run(d, c, 0.0, 2000)).toBe('max-duration');
	});
});
