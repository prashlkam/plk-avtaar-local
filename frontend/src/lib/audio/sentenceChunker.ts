import { cleanForSpeech, isSpeakable } from './speechCleaner';

export interface ChunkerOptions {
	/** Merge short sentences until a chunk reaches this many characters (after the first). */
	minChars?: number;
	/** Force a split (at a comma/space) when a chunk grows past this without a sentence end. */
	maxChars?: number;
	/** Said once per reply in place of code blocks. */
	codeNote?: string;
}

// Sentence end: terminal punctuation (optionally followed by closing quotes/brackets) + whitespace,
// or a newline. Decimals like 3.14 never match because they lack the following whitespace.
const BOUNDARY = /([.!?。！？…]+["'”’)\]]*)(?=\s)|\n/g;

/**
 * Streams LLM tokens in, emits speakable text chunks out — sentence by sentence,
 * skipping fenced code blocks (which may arrive split across many tokens).
 */
export class SentenceChunker {
	private buf = '';
	private pending = '';
	private inFence = false;
	private emittedAny = false;
	private saidCodeNote = false;
	private readonly minChars: number;
	private readonly maxChars: number;
	private readonly codeNote: string;

	constructor(opts: ChunkerOptions = {}) {
		this.minChars = opts.minChars ?? 40;
		this.maxChars = opts.maxChars ?? 220;
		this.codeNote = opts.codeNote ?? "I've put the code on screen.";
	}

	push(token: string): string[] {
		this.buf += token;
		return this.drain(false);
	}

	flush(): string[] {
		return this.drain(true);
	}

	private drain(final: boolean): string[] {
		const out: string[] = [];
		for (;;) {
			if (this.inFence) {
				const close = this.buf.indexOf('```');
				if (close === -1) {
					// Keep only a short tail in case the closing fence is split across tokens.
					this.buf = final ? '' : this.buf.slice(-2);
					break;
				}
				const eol = this.buf.indexOf('\n', close + 3);
				this.buf = eol === -1 ? '' : this.buf.slice(eol + 1);
				this.inFence = false;
				continue;
			}

			const fence = this.buf.indexOf('```');
			const searchIn = fence === -1 ? this.buf : this.buf.slice(0, fence);

			BOUNDARY.lastIndex = 0;
			let m: RegExpExecArray | null;
			let cut = -1;
			while ((m = BOUNDARY.exec(searchIn))) {
				if (m[0] !== '\n') {
					// "3. " at the start of a line is a list marker, not a sentence end.
					const lineStart = searchIn.lastIndexOf('\n', m.index) + 1;
					if (/^\s*\d+$/.test(searchIn.slice(lineStart, m.index))) continue;
				}
				cut = m.index + m[0].length;
				break;
			}

			if (cut > 0) {
				this.addPending(this.buf.slice(0, cut), out, false);
				this.buf = this.buf.slice(cut);
				continue;
			}

			if (fence !== -1) {
				this.addPending(this.buf.slice(0, fence), out, true);
				this.buf = this.buf.slice(fence + 3);
				this.inFence = true;
				if (!this.saidCodeNote) {
					this.saidCodeNote = true;
					this.addPending(' ' + this.codeNote + ' ', out, true);
				}
				continue;
			}

			// No sentence end yet: split very long runs at a comma or space.
			if (this.buf.length + this.pending.length > this.maxChars) {
				const window = this.buf.slice(0, Math.max(1, this.maxChars - this.pending.length));
				const at = Math.max(window.lastIndexOf(', '), window.lastIndexOf('; '));
				const sp = at > 20 ? at + 1 : window.lastIndexOf(' ');
				if (sp > 0) {
					this.addPending(this.buf.slice(0, sp), out, true);
					this.buf = this.buf.slice(sp);
					continue;
				}
			}
			break;
		}

		if (final) {
			if (!this.inFence) this.pending += this.buf;
			this.buf = '';
			this.emit(out);
		}
		return out;
	}

	private addPending(text: string, out: string[], force: boolean) {
		this.pending += text;
		// First chunk goes out as soon as possible to cut time-to-first-audio.
		const threshold = this.emittedAny ? this.minChars : 1;
		if (force || cleanForSpeech(this.pending).length >= threshold) this.emit(out);
	}

	private emit(out: string[]) {
		const text = cleanForSpeech(this.pending);
		this.pending = '';
		if (isSpeakable(text)) {
			out.push(text);
			this.emittedAny = true;
		}
	}
}

/** Split a complete message into speakable chunks (used for "read aloud"). */
export function chunkText(markdown: string, opts?: ChunkerOptions): string[] {
	const c = new SentenceChunker(opts);
	return [...c.push(markdown), ...c.flush()];
}
