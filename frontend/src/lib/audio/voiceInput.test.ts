import { describe, expect, it } from 'vitest';
import { TranscriptBuilder, join } from './voiceInput.svelte';

describe('TranscriptBuilder', () => {
	it('shows live partials, commits utterances, and prefers the summary', () => {
		const b = new TranscriptBuilder();
		b.apply({ type: 'partial', text: 'hello' });
		expect(b.text).toBe('hello');
		b.apply({ type: 'partial', text: 'hello there' });
		expect(b.text).toBe('hello there');
		b.apply({ type: 'final', final_kind: 'utterance', text: 'Hello there.' });
		expect(b.text).toBe('Hello there.');
		b.apply({ type: 'partial', text: 'how are' });
		expect(b.text).toBe('Hello there. how are');
		b.apply({ type: 'final', final_kind: 'utterance', text: 'How are you?' });
		expect(b.text).toBe('Hello there. How are you?');
		b.apply({ type: 'final', final_kind: 'summary', text: 'Hello there, how are you?' });
		expect(b.text).toBe('Hello there, how are you?');
	});

	it('falls back to committed text when the summary is empty', () => {
		const b = new TranscriptBuilder();
		b.apply({ type: 'final', final_kind: 'utterance', text: 'Testing' });
		b.apply({ type: 'final', final_kind: 'summary', text: '' });
		expect(b.text).toBe('Testing');
	});

	it('treats a bare final (no final_kind) as an utterance', () => {
		const b = new TranscriptBuilder();
		b.apply({ type: 'final', text: 'one' });
		b.apply({ type: 'final', text: 'two' });
		expect(b.text).toBe('one two');
	});
});

describe('join', () => {
	it('joins with single spaces and skips blanks', () => {
		expect(join('a ', ' b')).toBe('a b');
		expect(join('', 'b')).toBe('b');
		expect(join('a', '  ')).toBe('a');
	});
});
