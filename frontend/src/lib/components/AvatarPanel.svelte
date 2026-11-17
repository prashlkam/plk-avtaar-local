<script lang="ts">
	import { app } from '$lib/state.svelte';
	import type { AvatarState } from '$lib/types';
	import Avatar from './Avatar.svelte';
	import Icon from './Icon.svelte';

	const labels: Record<AvatarState, string> = {
		idle: 'Ready',
		listening: 'Listening…',
		thinking: 'Thinking…',
		speaking: 'Speaking…'
	};
</script>

<aside class="flex h-full w-80 shrink-0 flex-col items-center border-l border-gray-100 px-6 py-8 dark:border-gray-850">
	<div class="relative mt-6">
		<Avatar class="size-56" />
		{#if app.avatar === 'thinking'}
			<span class="absolute -right-1 bottom-6 flex gap-1 rounded-full bg-white px-2.5 py-1.5 shadow dark:bg-gray-800">
				{#each [0, 1, 2] as i (i)}
					<span class="size-1.5 animate-bounce rounded-full bg-gray-500" style="animation-delay: {i * 150}ms"></span>
				{/each}
			</span>
		{/if}
	</div>

	<h2 class="mt-6 text-lg font-semibold">Avtaar</h2>
	<p class="mt-1 flex items-center gap-2 text-sm text-gray-500">
		<span
			class="size-2 rounded-full {app.avatar === 'idle' ? 'bg-gray-400' : app.avatar === 'thinking' ? 'animate-pulse bg-amber-400' : app.avatar === 'listening' ? 'animate-pulse bg-red-400' : 'animate-pulse bg-emerald-400'}"
		></span>
		{labels[app.avatar]}
	</p>

	<div class="mt-5 flex flex-wrap justify-center gap-2">
		<button
			class="flex items-center gap-2 rounded-full border border-gray-200 px-3.5 py-1.5 text-sm hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:hover:bg-gray-850"
			onclick={() => app.toggleVoice()}
			disabled={!app.voiceAvailable}
			title={app.voiceAvailable ? (app.voiceOn ? 'Mute voice replies' : 'Speak replies aloud') : 'VoiceStudio is not running'}
			aria-pressed={app.voiceOn}
		>
			<Icon name={app.voiceOn && app.voiceAvailable ? 'speaker' : 'mute'} />
			{app.voiceOn && app.voiceAvailable ? 'Voice on' : 'Voice off'}
		</button>
		{#if app.speaker.busy}
			<button
				class="flex items-center gap-2 rounded-full bg-gray-900 px-3.5 py-1.5 text-sm text-white hover:bg-gray-700 dark:bg-white dark:text-gray-900"
				onclick={() => app.stopSpeaking()}
			>
				<Icon name="stop" class="size-3 fill-current" /> Stop
			</button>
		{:else}
			<button
				class="flex items-center gap-2 rounded-full border border-gray-200 px-3.5 py-1.5 text-sm hover:bg-gray-100 dark:border-gray-700 dark:hover:bg-gray-850"
				onclick={() => app.toggleAvatarMode()}
				title="Full-screen Avtaar with captions"
			>
				<Icon name="expand" /> Avatar mode
			</button>
		{/if}
	</div>

	{#if app.speaker.caption}
		<p class="mt-5 line-clamp-4 text-center text-sm text-gray-600 dark:text-gray-300" aria-live="polite">
			“{app.speaker.caption}”
		</p>
	{/if}

	<div class="mt-auto w-full space-y-2 text-xs">
		<div class="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-850">
			<span>LLM (Ollama)</span>
			<span class={app.health?.ollama.ok ? 'text-emerald-500' : 'text-red-500'}>
				{app.health ? (app.health.ollama.ok ? (app.warming ? 'loading model…' : `v${app.health.ollama.version}`) : 'offline') : '…'}
			</span>
		</div>
		<div class="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-850">
			<span>Voice (VoiceStudio)</span>
			<span class={app.health?.voicestudio.ok ? 'text-emerald-500' : 'text-amber-500'}>
				{app.health ? (app.health.voicestudio.ok ? 'online' : 'not running') : '…'}
			</span>
		</div>
	</div>
</aside>
