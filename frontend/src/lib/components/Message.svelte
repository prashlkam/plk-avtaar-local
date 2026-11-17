<script lang="ts">
	import { handleCodeCopy, renderMarkdown } from '$lib/markdown';
	import { app } from '$lib/state.svelte';
	import type { Message } from '$lib/types';
	import Icon from './Icon.svelte';

	let { message, isLast }: { message: Message; isLast: boolean } = $props();

	let editing = $state(false);
	let draft = $state('');
	let copied = $state(false);

	const html = $derived(message.role === 'assistant' ? renderMarkdown(message.content) : '');
	const persisted = $derived(!message.id.startsWith('tmp-') && !message.id.startsWith('err-'));

	function copy() {
		navigator.clipboard?.writeText(message.content);
		copied = true;
		setTimeout(() => (copied = false), 1200);
	}
	function startEdit() {
		draft = message.content;
		editing = true;
	}
	function submitEdit() {
		editing = false;
		if (draft.trim() && draft.trim() !== message.content) app.send(draft, { replaceFrom: message.id });
	}
	function autosize(node: HTMLTextAreaElement) {
		const fit = () => {
			node.style.height = 'auto';
			node.style.height = node.scrollHeight + 'px';
		};
		fit();
		node.focus();
		node.addEventListener('input', fit);
	}
</script>

{#if message.role === 'user'}
	<div class="group flex flex-col items-end">
		{#if editing}
			<div class="w-full rounded-3xl bg-gray-100 p-3 dark:bg-gray-800">
				<textarea
					class="w-full resize-none bg-transparent px-2 outline-none"
					bind:value={draft}
					use:autosize
					onkeydown={(e) => {
						if (e.key === 'Enter' && !e.shiftKey) {
							e.preventDefault();
							submitEdit();
						}
						if (e.key === 'Escape') editing = false;
					}}
				></textarea>
				<div class="mt-2 flex justify-end gap-2 text-sm">
					<button class="rounded-full px-3 py-1.5 hover:bg-gray-200 dark:hover:bg-gray-700" onclick={() => (editing = false)}>Cancel</button>
					<button class="rounded-full bg-gray-900 px-3 py-1.5 text-white dark:bg-white dark:text-gray-900" onclick={submitEdit}>Send</button>
				</div>
			</div>
		{:else}
			<div class="max-w-[85%] whitespace-pre-wrap break-words rounded-3xl bg-gray-100 px-5 py-2.5 dark:bg-gray-850">
				{message.content}
			</div>
			<div class="mt-1 flex gap-1 text-gray-500 opacity-0 transition group-hover:opacity-100">
				<button class="rounded-lg p-1.5 hover:bg-gray-100 hover:text-gray-900 dark:hover:bg-gray-800 dark:hover:text-white" title="Copy" onclick={copy}>
					<Icon name={copied ? 'check' : 'copy'} />
				</button>
				{#if persisted && !app.streaming}
					<button class="rounded-lg p-1.5 hover:bg-gray-100 hover:text-gray-900 dark:hover:bg-gray-800 dark:hover:text-white" title="Edit" onclick={startEdit}>
						<Icon name="edit" />
					</button>
				{/if}
			</div>
		{/if}
	</div>
{:else}
	<div class="group flex gap-3">
		<img src={app.avatarImages.idle} alt="" class="mt-0.5 size-8 shrink-0 rounded-full" />
		<div class="min-w-0 flex-1">
			<div class="mb-1 text-sm font-semibold">
				Avtaar <span class="ml-1 text-xs font-normal text-gray-500">{message.model ?? ''}</span>
			</div>
			{#if message.streaming && !message.content}
				<div class="flex gap-1 py-2" aria-label="Thinking">
					{#each [0, 1, 2] as i (i)}
						<span class="size-2 animate-bounce rounded-full bg-gray-400" style="animation-delay: {i * 150}ms"></span>
					{/each}
				</div>
			{:else}
				<!-- eslint-disable-next-line svelte/no-at-html-tags (sanitized by DOMPurify) -->
				<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
				<div
					class="md prose prose-gray max-w-none dark:prose-invert prose-p:my-2 prose-pre:bg-transparent {message.streaming
						? 'streaming-caret'
						: ''}"
					onclick={handleCodeCopy}
				>
					{@html html}
				</div>
			{/if}
			{#if message.error}
				<div class="mt-2 flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
					<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
					<span>{message.error}</span>
				</div>
			{/if}
			{#if !message.streaming}
				<div class="mt-1 flex gap-1 text-gray-500 {isLast ? '' : 'opacity-0 transition group-hover:opacity-100'}">
					{#if message.content}
						<button class="rounded-lg p-1.5 hover:bg-gray-100 hover:text-gray-900 dark:hover:bg-gray-800 dark:hover:text-white" title="Copy" onclick={copy}>
							<Icon name={copied ? 'check' : 'copy'} />
						</button>
					{/if}
					{#if message.content}
						{@const reading = app.readingId === message.id && app.speaker.busy}
						<button
							class="rounded-lg p-1.5 hover:bg-gray-100 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-40 dark:hover:bg-gray-800 dark:hover:text-white {reading ? 'text-emerald-500' : ''}"
							title={app.voiceAvailable ? (reading ? 'Stop reading' : 'Read aloud') : 'VoiceStudio is not running'}
							disabled={!app.voiceAvailable}
							onclick={() => app.readAloud(message)}
						>
							<Icon name={reading ? 'stop' : 'speaker'} class={reading ? 'size-4 fill-current' : 'size-4'} />
						</button>
					{/if}
					{#if isLast && persisted && !app.streaming}
						<button class="rounded-lg p-1.5 hover:bg-gray-100 hover:text-gray-900 dark:hover:bg-gray-800 dark:hover:text-white" title="Regenerate" onclick={() => app.send('', { replaceFrom: message.id, regenerate: true })}>
							<Icon name="refresh" />
						</button>
					{/if}
				</div>
			{/if}
		</div>
	</div>
{/if}
