import { describe, expect, it } from 'vitest';
import { SentenceChunker, chunkText } from './sentenceChunker';
import { cleanForSpeech } from './speechCleaner';

function streamed(text: string, size = 3, opts = {}) {
	const c = new SentenceChunker(opts);
	const out: string[] = [];
	for (let i = 0; i < text.length; i += size) out.push(...c.push(text.slice(i, i + size)));
	out.push(...c.flush());
	return out;
}

describe('cleanForSpeech', () => {
	it('strips markdown formatting', () => {
		expect(cleanForSpeech('## Title\n**Bold** and _it_ and `code`')).toBe('Title Bold and it and code');
		expect(cleanForSpeech('- one\n- two\n1. three')).toBe('one two three');
		expect(cleanForSpeech('See [the docs](http://x.y/z) or https://a.b/c')).toBe('See the docs or a link');
	});
	it('drops code blocks and emoji', () => {
		expect(cleanForSpeech('Hi 👋🏽!\n```py\nprint(1)\n```\nBye')).toBe('Hi ! Bye');
	});
	it('keeps snake_case words intact', () => {
		expect(cleanForSpeech('use my_var_name here')).toBe('use my_var_name here');
	});
});

describe('SentenceChunker', () => {
	it('emits the first sentence immediately, then merges short ones', () => {
		const out = streamed('Hi. I am Avtaar. I live on your computer. Nice to meet you!');
		expect(out[0]).toBe('Hi.');
		expect(out.join(' ')).toBe('Hi. I am Avtaar. I live on your computer. Nice to meet you!');
		expect(out.length).toBeLessThan(4);
	});

	it('does not split decimals', () => {
		expect(streamed('Pi is 3.14 roughly. Yes.', 1).join(' ')).toContain('3.14');
		expect(streamed('Pi is 3.14 roughly. Yes.', 1)[0]).toBe('Pi is 3.14 roughly.');
	});

	it('skips fenced code split across tokens and says the note once', () => {
		const text = 'Here you go:\n```python\nprint("a. b. c.")\n```\nThat prints it.\n```js\nx()\n```\nDone.';
		const out = streamed(text, 2);
		const all = out.join(' ');
		expect(all).not.toContain('print(');
		expect(all).not.toContain('x()');
		expect(all.match(/put the code on screen/g)?.length).toBe(1);
		expect(all).toContain('That prints it.');
		expect(all).toContain('Done.');
	});

	it('splits very long sentences', () => {
		const long = Array.from({ length: 60 }, (_, i) => `word${i}`).join(' ');
		const out = streamed(long, 5, { maxChars: 100 });
		expect(out.length).toBeGreaterThan(2);
		for (const c of out) expect(c.length).toBeLessThanOrEqual(110);
		expect(out.join(' ')).toBe(long);
	});

	it('treats list lines as boundaries', () => {
		const out = chunkText('Steps:\n1. Open the app\n2. Click talk\n3. Speak clearly', { minChars: 1 });
		expect(out).toEqual(['Steps:', 'Open the app', 'Click talk', 'Speak clearly']);
	});

	it('emits nothing for code-only or emoji-only replies', () => {
		expect(chunkText('```\ncode\n```')).toEqual(["I've put the code on screen."]);
		expect(chunkText('🎉🎉')).toEqual([]);
	});
});
