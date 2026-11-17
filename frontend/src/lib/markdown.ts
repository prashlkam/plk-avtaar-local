import DOMPurify from 'dompurify';
import hljs from 'highlight.js/lib/common';
import { Marked, type Tokens } from 'marked';

function escapeHtml(s: string) {
	return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
}

const marked = new Marked({
	gfm: true,
	breaks: true,
	renderer: {
		code({ text, lang }: Tokens.Code) {
			const language = (lang || '').trim().split(/\s+/)[0];
			const valid = language && hljs.getLanguage(language);
			const html = valid ? hljs.highlight(text, { language }).value : hljs.highlightAuto(text).value;
			return (
				`<pre><div class="code-head"><span>${escapeHtml(language || 'code')}</span>` +
				`<button type="button" data-copy class="hover:text-white">Copy</button></div>` +
				`<code class="hljs">${html}</code></pre>`
			);
		},
		link({ href, text }: Tokens.Link) {
			return `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${text}</a>`;
		}
	}
});

export function renderMarkdown(src: string): string {
	const html = marked.parse(src, { async: false }) as string;
	return DOMPurify.sanitize(html, { ADD_ATTR: ['target', 'data-copy'] });
}

/** Event delegation handler for "Copy" buttons inside rendered code blocks. */
export function handleCodeCopy(e: MouseEvent) {
	const btn = (e.target as HTMLElement).closest('[data-copy]') as HTMLButtonElement | null;
	if (!btn) return;
	const code = btn.closest('pre')?.querySelector('code')?.textContent ?? '';
	navigator.clipboard?.writeText(code).then(() => {
		btn.textContent = 'Copied';
		setTimeout(() => (btn.textContent = 'Copy'), 1200);
	});
}
