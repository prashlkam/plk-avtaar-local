/** Turn a chunk of Markdown into text that sounds natural when spoken. */
export function cleanForSpeech(md: string): string {
	let s = md;
	// Fenced code (complete or dangling) is never read out.
	s = s.replace(/```[\s\S]*?(```|$)/g, ' ');
	// Images, then links -> their text.
	s = s.replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1');
	s = s.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');
	// Bare URLs.
	s = s.replace(/\bhttps?:\/\/\S+/gi, 'a link');
	// Inline code -> its text.
	s = s.replace(/`([^`]+)`/g, '$1');
	// Headings, blockquotes, list markers, horizontal rules (line starts).
	s = s.replace(/^\s{0,3}#{1,6}\s+/gm, '');
	s = s.replace(/^\s*>\s?/gm, '');
	s = s.replace(/^\s*(?:[-*+]|\d+[.)])\s+/gm, '');
	s = s.replace(/^\s*([-*_])\s*(?:\1\s*){2,}$/gm, ' ');
	// Tables: drop separator rows, turn pipes into pauses.
	s = s.replace(/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/gm, ' ');
	s = s.replace(/\s*\|\s*/g, ', ');
	// Emphasis / strike markers.
	s = s.replace(/(\*\*|__|~~)(.+?)\1/g, '$2');
	s = s.replace(/(^|[^\w*])[*_]([^*_\n]+)[*_](?=[^\w*]|$)/g, '$1$2');
	s = s.replace(/[*_~]{2,}/g, '');
	// HTML tags.
	s = s.replace(/<\/?[a-z][^>]*>/gi, ' ');
	// Emoji and pictographs.
	s = s.replace(/[\p{Extended_Pictographic}\p{Emoji_Modifier}\u{FE0F}\u{200D}]/gu, '');
	// Whitespace.
	s = s.replace(/\s+/g, ' ').trim();
	s = s.replace(/^[,;:\s]+|[,;\s]+$/g, '');
	return s;
}

/** True when a cleaned chunk contains something worth speaking. */
export function isSpeakable(s: string): boolean {
	return /[\p{L}\p{N}]/u.test(s);
}
