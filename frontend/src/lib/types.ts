export type Role = 'user' | 'assistant' | 'system';

export interface Message {
	id: string;
	role: Role;
	content: string;
	model?: string | null;
	created_at: number;
	/** client-only flags */
	streaming?: boolean;
	error?: string;
}

export interface ChatSummary {
	id: string;
	title: string;
	model: string | null;
	created_at: number;
	updated_at: number;
}

export interface Chat extends ChatSummary {
	messages: Message[];
}

export interface ModelInfo {
	name: string;
	size?: number;
	parameter_size?: string;
	family?: string;
}

export interface ServiceHealth {
	ok: boolean;
	url: string;
	version?: string;
	error?: string;
	hint?: string;
}

export interface Health {
	ok: boolean;
	ollama: ServiceHealth;
	voicestudio: ServiceHealth;
}

export interface Settings {
	default_model: string;
	system_prompt: string;
	temperature: number;
	tts_model: string;
	tts_voice: string;
	tts_speed: number;
	stt_language: string;
	stt_model: string;
	auto_send: boolean;
	auto_stop_ms: number;
}

export interface AvatarImages {
	idle: string;
	talking: string;
	custom: { idle: boolean; talking: boolean };
}

export type AvatarState = 'idle' | 'listening' | 'thinking' | 'speaking';
