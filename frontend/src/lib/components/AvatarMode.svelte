<script lang="ts">
	import { app } from '$lib/state.svelte';
	import type { AvatarState } from '$lib/types';
	import Avatar from './Avatar.svelte';
	import Icon from './Icon.svelte';

	// Full-screen, voice-first view: big Avtaar, live captions, one big talk button.

	const labels: Record<AvatarState, string> = {
		idle: 'Tap the mic and talk to me',
		listening: 'Listening…',
		thinking: 'Thinking…',
		speaking: 'Speaking…'
	};

	const vstate = $derived(app.voice.state);
	const talking = $derived(vstate === 'listening' || vstate === 'starting');
	const lastUser = $derived([...app.messages].reverse().find((m) => m.role === 'user')?.content ?? '');
	const lastReply = $derived(app.messages.at(-1)?.role === 'assistant' ? app.messages.at(-1)!.content : '');

	// What to show under the avatar right now.
	const caption = $derived(
		app.listening
			? app.draft || ' '
			: app.speaker.caption ||
					(app.streaming ? '' : app.voiceOn && app.voiceAvailable ? '' : lastReply.slice(0, 400))
	);

	let typed = $state('');
	function sendTyped(e: SubmitEvent) {
		e.preventDefault();
		if (!typed.trim() || app.streaming || app.voice.active) return;
		app.send(typed);
		typed = '';
	}
</script>

<div
	class="fixed inset-0 z-30 flex flex-col bg-gradient-to-b from-indigo-50 to-white dark:from-gray-950 dark:to-gray-900"
	role="dialog"
	aria-modal="true"
	aria-label="Avatar mode"
>
	<header class="flex items-center gap-2 p-3">
		<span class="px-2 text-sm font-medium text-gray-500">{app.current?.title ?? 'New chat'} · {app.model}</span>
		<div class="ml-auto flex items-center gap-1">
			<button
				class="rounded-lg p-2 text-gray-500 hover:bg-black/5 disabled:opacity-40 dark:hover:bg-white/10"
				onclick={() => app.toggleVoice()}
				disabled={!app.voiceAvailable}
				title={app.voiceOn ? 'Mute voice replies' : 'Speak replies aloud'}
			>
				<Icon name={app.voiceOn && app.voiceAvailable ? 'speaker' : 'mute'} class="size-5" />
			</button>
			<button
				class="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-gray-600 hover:bg-black/5 dark:text-gray-300 dark:hover:bg-white/10"
				onclick={() => app.toggleAvatarMode()}
				title="Back to chat view"
			>
				<Icon name="x" class="size-4" /> Exit avatar mode
			</button>
		</div>
	</header>

	<div class="flex min-h-0 flex-1 flex-col items-center justify-center gap-6 px-4">
		{#if lastUser && !app.listening}
			<p class="max-w-xl truncate text-center text-sm text-gray-400" title={lastUser}>You: {lastUser}</p>
		{/if}

		<Avatar class="size-[min(22rem,55vw,40vh)]" />

		<p class="flex items-center gap-2 text-sm text-gray-500">
			<span
				class="size-2 rounded-full {app.avatar === 'idle' ? 'bg-gray-400' : app.avatar === 'thinking' ? 'animate-pulse bg-amber-400' : app.avatar === 'listening' ? 'animate-pulse bg-red-400' : 'animate-pulse bg-emerald-400'}"
			></span>
			{labels[app.avatar]}
		</p>

		<div class="flex min-h-24 w-full max-w-2xl items-start justify-center" aria-live="polite">
			{#if caption.trim()}
				<p
					class="text-center text-xl leading-relaxed text-balance sm:text-2xl {app.listening
						? 'text-gray-500 italic dark:text-gray-400'
						: 'text-gray-900 dark:text-gray-100'}"
				>
					{caption}
				</p>
			{:else if app.avatar === 'thinking'}
				<div class="flex gap-1.5 pt-3">
					{#each [0, 1, 2] as i (i)}
						<span class="size-2.5 animate-bounce rounded-full bg-gray-400" style="animation-delay: {i * 150}ms"></span>
					{/each}
				</div>
			{/if}
		</div>
	</div>

	<footer class="flex flex-col items-center gap-3 pb-8">
		<div class="flex items-center gap-4">
			<button
				class="relative flex size-20 items-center justify-center rounded-full shadow-lg transition disabled:cursor-not-allowed disabled:opacity-50
				{talking ? 'bg-red-500 text-white' : 'bg-gray-900 text-white hover:scale-105 dark:bg-white dark:text-gray-900'}"
				onclick={() => app.toggleTalk()}
				disabled={!app.voiceAvailable || vstate === 'finishing'}
				title={talking ? 'Done (Ctrl+Space)' : 'Talk (Ctrl+Space)'}
				aria-pressed={talking}
				aria-label={talking ? 'Done talking' : 'Talk'}
			>
				{#if talking}
					<span
						class="pointer-events-none absolute inset-0 rounded-full ring-red-400/50 transition-[box-shadow]"
						style:box-shadow="0 0 0 {Math.round(app.voice.level * 28)}px rgb(248 113 113 / 0.35)"
					></span>
					<Icon name="stop" class="relative size-7 fill-current" />
				{:else if vstate === 'finishing'}
					<span class="size-7 animate-spin rounded-full border-[3px] border-current border-t-transparent"></span>
				{:else}
					<Icon name="mic" class="size-8" />
				{/if}
			</button>
			{#if app.streaming || app.speaker.busy}
				<button
					class="flex size-12 items-center justify-center rounded-full bg-white text-gray-900 shadow hover:bg-gray-100 dark:bg-gray-800 dark:text-white"
					onclick={() => app.stop()}
					title="Stop (Esc)"
					aria-label="Stop"
				>
					<Icon name="stop" class="size-4 fill-current" />
				</button>
			{/if}
		</div>
		{#if app.voiceAvailable}
			<p class="text-xs text-gray-400">
				{talking ? 'Click again when you are done' : 'Click or press Ctrl+Space to talk'}{app.settings?.auto_stop_ms
					? ' · stops automatically when you pause'
					: ''}
			</p>
		{:else}
			<form class="flex w-full max-w-md gap-2 px-4" onsubmit={sendTyped}>
				<input
					bind:value={typed}
					placeholder="Voice is offline. Type here…"
					class="flex-1 rounded-full border border-gray-200 bg-white px-4 py-2 text-sm dark:border-gray-700 dark:bg-gray-850"
				/>
				<button class="rounded-full bg-gray-900 px-4 text-sm text-white disabled:opacity-50 dark:bg-white dark:text-gray-900" disabled={!typed.trim() || app.streaming}>Send</button>
			</form>
		{/if}
	</footer>
</div>
