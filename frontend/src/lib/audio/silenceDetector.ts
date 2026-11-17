/**
 * Decides when push-to-talk should end by itself: once the user has spoken,
 * stop after `silenceMs` of quiet. The speech threshold adapts to the room's
 * background noise, so a fan or hum doesn't count as speech.
 */
export interface SilenceOptions {
	/** Never treat anything quieter than this RMS (0..1) as speech. */
	minThreshold?: number;
	/** Speech must be this many times louder than the noise floor. */
	ratio?: number;
	/** Speech must last this long before it counts (ignores clicks/pops). */
	minSpeechMs?: number;
	/** Hard limit on one recording. */
	maxMs?: number;
	/** The first this-many ms only measure background noise (nobody talks that fast). */
	calibrateMs?: number;
}

export type SilenceEvent = 'silence' | 'max-duration' | null;

export class SilenceDetector {
	private noise: number | null = null;
	private startedAt: number | null = null;
	private speechStart: number | null = null;
	private lastVoice = 0;
	heardSpeech = false;
	private readonly minThreshold: number;
	private readonly ratio: number;
	private readonly minSpeechMs: number;
	private readonly maxMs: number;
	private readonly calibrateMs: number;
	private calSum = 0;
	private calN = 0;

	constructor(
		private silenceMs: number,
		opts: SilenceOptions = {}
	) {
		this.minThreshold = opts.minThreshold ?? 0.015;
		this.ratio = opts.ratio ?? 3;
		this.minSpeechMs = opts.minSpeechMs ?? 200;
		this.maxMs = opts.maxMs ?? 60_000;
		this.calibrateMs = opts.calibrateMs ?? 250;
	}

	get threshold(): number {
		return Math.max(this.minThreshold, (this.noise ?? 0) * this.ratio);
	}

	/** Feed one RMS sample (0..1) taken at time `now` (ms). */
	feed(rms: number, now: number): SilenceEvent {
		this.startedAt ??= now;
		if (now - this.startedAt >= this.maxMs) return 'max-duration';

		if (now - this.startedAt < this.calibrateMs) {
			this.calSum += rms;
			this.calN++;
			this.noise = this.calSum / this.calN;
			return null;
		}

		if (rms > this.threshold) {
			this.speechStart ??= now;
			if (now - this.speechStart >= this.minSpeechMs) this.heardSpeech = true;
			this.lastVoice = now;
		} else {
			this.speechStart = null;
			// Learn the noise floor only from quiet samples.
			this.noise = this.noise === null ? rms : this.noise * 0.97 + rms * 0.03;
		}

		if (this.silenceMs > 0 && this.heardSpeech && now - this.lastVoice >= this.silenceMs) return 'silence';
		return null;
	}
}
