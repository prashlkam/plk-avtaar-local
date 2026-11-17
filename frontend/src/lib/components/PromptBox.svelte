<script lang="ts">
	import { app } from '$lib/state.svelte';
	import Icon from './Icon.svelte';

	let el: HTMLTextAreaElement | undefined = $state();

	const vstate = $derived(app.voice.state);
	const talking = $derived(vstate === 'listening' || vstate === 'starting');
	const finishing = $derived(vstate === 'finishing');

	function fit() {
		if (!el) return;
		el.style.height = 'auto';
		el.style.height = Math.min(el.scrollHeight, 240) + 'px';
	}

	// Resize as the live transcript (or anything else) changes the text.
	$effect(() => {
		void app.draft;
		queueMicrotask(fit);
	});

	function submit() {
		if (!app.draft.trim() || app.streaming || app.voice.active) return;
		const text = app.draft;
		app.draft = '';
		app.send(text);
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
			e.preventDefault();
			submit();
		}
	}

	$effect(() => {
		// Re-focus the box whenever the conversation changes.
		void app.current?.id;
		el?.focus();
	});

	function onWindowKey(e: KeyboardEvent) {
		if (e.key === ' ' && e.ctrlKey && !e.repeat) {
			e.preventDefault();
			app.toggleTalk();
		} else if (e.key === 'Escape') {
			if (app.voice.state === 'listening') app.cancelTalk();
			else if (app.streaming || app.speaker.busy) app.stop();
		}
	}

	const micTitle = $derived(
		!app.voiceAvailable
			? 'VoiceStudio is not running on :3900, so voice input is unavailable'
			: talking
				? 'Stop and use what I said (Ctrl+Space) · Esc cancels'
				: finishing
					? 'Transcribing…'
					: 'Talk to Avtaar (Ctrl+Space)'
	);
</script>

<svelte:window onkeydown={onWindowKey} />

<div class="mx-auto w-full max-w-3xl px-3 pb-3">
	<div
		class="rounded-3xl border bg-white px-3 py-2 shadow-sm transition dark:bg-gray-850
		{talking
			? 'border-red-300 ring-4 ring-red-500/10 dark:border-red-900'
			: 'border-gray-200 focus-within:border-gray-300 dark:border-gray-800 dark:focus-within:border-gray-700'}"
	>
		<textarea
			bind:this={el}
			bind:value={app.draft}
			oninput={fit}
			onkeydown={onKeydown}
			rows="1"
			readonly={app.voice.active}
			placeholder={talking ? 'Listening… start speaking' : finishing ? 'Transcribing…' : 'Ask anything…'}
			aria-label="Message"
			class="block max-h-60 w-full resize-none bg-transparent px-2 pt-1.5 pb-1 outline-none placeholder:text-gray-400 {app.voice.active
				? 'text-gray-500 dark:text-gray-400'
				: ''}"
		></textarea>
		<div class="flex items-center justify-end gap-2 pt-1">
			{#if talking}
				<span class="mr-auto flex items-center gap-2 pl-2 text-xs text-red-500">
					<span class="relative flex size-2">
						<span class="absolute inline-flex size-full animate-ping rounded-full bg-red-400 opacity-75"></span>
						<span class="relative inline-flex size-2 rounded-full bg-red-500"></span>
					</span>
					Listening{app.voice.live ? '' : ' (will transcribe when you stop)'}
				</span>
			{:else if finishing}
				<span class="mr-auto pl-2 text-xs text-gray-500">Transcribing…</span>
			{/if}

			<button
				class="relative flex h-9 items-center gap-1.5 overflow-hidden rounded-full px-3.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50
				{talking
					? 'bg-red-500 text-white hover:bg-red-600'
					: 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800'}"
				onclick={() => app.toggleTalk()}
				disabled={!app.voiceAvailable || finishing}
				title={micTitle}
				aria-pressed={talking}
			>
				{#if talking}
					<!-- live input level -->
					<span
						class="pointer-events-none absolute inset-y-0 left-0 bg-white/25 transition-[width] duration-75"
						style:width="{Math.round(app.voice.level * 100)}%"
					></span>
					<Icon name="stop" class="relative size-3.5 fill-current" />
					<span class="relative">Done</span>
				{:else if finishing}
					<span class="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"></span>
					Talk
				{:else}
					<Icon name="mic" class="size-4" /> Talk
				{/if}
			</button>

			{#if app.streaming || app.speaker.busy}
				<button
					class="flex size-9 items-center justify-center rounded-full bg-gray-900 text-white hover:bg-gray-700 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
					onclick={() => app.stop()}
					title={app.streaming ? 'Stop (Esc)' : 'Stop speaking (Esc)'}
				>
					<Icon name="stop" class="size-3.5 fill-current" />
				</button>
			{:else}
				<button
					class="flex size-9 items-center justify-center rounded-full bg-gray-900 text-white transition hover:bg-gray-700 disabled:bg-gray-200 disabled:text-gray-400 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200 dark:disabled:bg-gray-700 dark:disabled:text-gray-500"
					onclick={submit}
					disabled={!app.draft.trim() || app.voice.active}
					title="Send (Enter)"
				>
					<Icon name="send" class="size-4" stroke={2.5} />
				</button>
			{/if}
		</div>
	</div>
	<p class="mt-2 text-center text-xs text-gray-400">
		Runs 100% locally · {app.model || 'no model'} · voice {app.voiceAvailable ? (app.voiceOn ? 'on' : 'muted') : 'unavailable'}
		{#if app.voiceAvailable}· Ctrl+Space to talk{/if}
	</p>
</div>
