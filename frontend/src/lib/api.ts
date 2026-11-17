import type { AvatarImages, Chat, ChatSummary, Health, Message, ModelInfo, Settings } from './types';

async function json<T>(res: Response): Promise<T> {
	if (!res.ok) {
		let detail = `${res.status} ${res.statusText}`;
		try {
			detail = (await res.json()).detail ?? detail;
		} catch {
			/* not json */
		}
		throw new Error(detail);
	}
	return res.json() as Promise<T>;
}

const jsonHeaders = { 'Content-Type': 'application/json' };

export const api = {
	health: () => fetch('/api/health').then((r) => json<Health>(r)),
	models: () => fetch('/api/models').then((r) => json<{ models: ModelInfo[]; default: string }>(r)),
	chats: () => fetch('/api/chats').then((r) => json<ChatSummary[]>(r)),
	chat: (id: string) => fetch(`/api/chats/${id}`).then((r) => json<Chat>(r)),
	renameChat: (id: string, title: string) =>
		fetch(`/api/chats/${id}`, { method: 'PATCH', headers: jsonHeaders, body: JSON.stringify({ title }) }).then(
			(r) => json<Chat>(r)
		),
	deleteChat: (id: string) => fetch(`/api/chats/${id}`, { method: 'DELETE' }).then((r) => json(r)),
	voices: () =>
		fetch('/api/voices').then((r) =>
			json<{ voices: { id: string; name: string; language?: string | null }[]; current: string }>(r)
		),
	warmup: (model: string) =>
		fetch('/api/warmup', { method: 'POST', headers: jsonHeaders, body: JSON.stringify({ model }) }).then((r) =>
			json<{ ok: boolean; load_ms: number }>(r)
		),
	avatar: () => fetch('/api/avatar').then((r) => json<AvatarImages>(r)),
	uploadAvatar: (kind: 'idle' | 'talking', file: File) => {
		const form = new FormData();
		form.append('file', file);
		return fetch(`/api/avatar/${kind}`, { method: 'POST', body: form }).then((r) => json<AvatarImages>(r));
	},
	resetAvatar: (kind: 'idle' | 'talking') =>
		fetch(`/api/avatar/${kind}`, { method: 'DELETE' }).then((r) => json<AvatarImages>(r)),
	settings: () => fetch('/api/settings').then((r) => json<Settings>(r)),
	saveSettings: (s: Partial<Settings>) =>
		fetch('/api/settings', { method: 'PUT', headers: jsonHeaders, body: JSON.stringify(s) }).then((r) =>
			json<Settings>(r)
		)
};

export interface ChatStreamRequest {
	chat_id?: string | null;
	model?: string;
	content: string;
	replace_from?: string;
	regenerate?: boolean;
}

export interface ChatStreamHandlers {
	onMeta?: (d: { chat_id: string; user_message: Message | null; title: string; model: string }) => void;
	onToken?: (t: string) => void;
	onDone?: (d: { assistant_message: Message | null; stats: Record<string, number> }) => void;
	onError?: (d: { message: string; assistant_message?: Message | null }) => void;
}

/** POST /api/chat and parse the Server-Sent Events stream. */
export async function streamChat(req: ChatStreamRequest, h: ChatStreamHandlers, signal: AbortSignal) {
	const res = await fetch('/api/chat', {
		method: 'POST',
		headers: jsonHeaders,
		body: JSON.stringify(req),
		signal
	});
	if (!res.ok || !res.body) {
		await json(res);
		return;
	}
	await readSSE(res, (event, payload) => {
		if (event === 'meta') h.onMeta?.(payload as never);
		else if (event === 'token') h.onToken?.((payload as { t: string }).t);
		else if (event === 'done') h.onDone?.(payload as never);
		else if (event === 'error') h.onError?.(payload as never);
	});
}

/** Parse a Server-Sent Events response body, calling onEvent(name, jsonData) per event. */
export async function readSSE(res: Response, onEvent: (event: string, data: unknown) => void) {
	if (!res.body) return;
	const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
	let buf = '';
	for (;;) {
		const { value, done } = await reader.read();
		if (done) break;
		buf += value;
		let idx: number;
		while ((idx = buf.indexOf('\n\n')) !== -1) {
			const block = buf.slice(0, idx);
			buf = buf.slice(idx + 2);
			let event = 'message';
			let data = '';
			for (const line of block.split('\n')) {
				if (line.startsWith('event: ')) event = line.slice(7);
				else if (line.startsWith('data: ')) data += line.slice(6);
			}
			if (data) onEvent(event, JSON.parse(data));
		}
	}
}
