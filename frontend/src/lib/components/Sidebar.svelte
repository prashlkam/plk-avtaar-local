<script lang="ts">
	import { app } from '$lib/state.svelte';
	import type { ChatSummary } from '$lib/types';
	import Icon from './Icon.svelte';

	let { onSettings }: { onSettings: () => void } = $props();

	let editingId = $state<string | null>(null);
	let editTitle = $state('');

	const groups = $derived.by(() => {
		const startOfToday = new Date().setHours(0, 0, 0, 0) / 1000;
		const day = 86400;
		const buckets: [string, ChatSummary[]][] = [
			['Today', []],
			['Yesterday', []],
			['Previous 7 days', []],
			['Older', []]
		];
		for (const c of app.chats) {
			const t = c.updated_at;
			const i = t >= startOfToday ? 0 : t >= startOfToday - day ? 1 : t >= startOfToday - 7 * day ? 2 : 3;
			buckets[i][1].push(c);
		}
		return buckets.filter(([, list]) => list.length);
	});

	function startRename(c: ChatSummary) {
		editingId = c.id;
		editTitle = c.title;
	}
	async function commitRename() {
		if (editingId) await app.renameChat(editingId, editTitle);
		editingId = null;
	}
	async function remove(c: ChatSummary) {
		if (confirm(`Delete "${c.title}"? This cannot be undone.`)) await app.deleteChat(c.id);
	}
	function focus(node: HTMLInputElement) {
		node.focus();
		node.select();
	}
</script>

<aside
	class="flex h-full w-64 shrink-0 flex-col bg-gray-50 text-sm dark:bg-gray-950"
	aria-label="Chat history"
>
	<div class="flex items-center gap-2 p-2">
		<button
			class="rounded-lg p-2 text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-850"
			onclick={() => app.toggleSidebar()}
			title="Close sidebar"
		>
			<Icon name="menu" class="size-5" />
		</button>
		<button
			class="flex flex-1 items-center gap-2 rounded-lg px-3 py-2 font-medium hover:bg-gray-200 dark:hover:bg-gray-850"
			onclick={() => app.newChat()}
		>
			<img src={app.avatarImages.idle} alt="" class="size-6 rounded-full" />
			<span class="flex-1 text-left">New chat</span>
			<Icon name="pencil" class="size-4 text-gray-500" />
		</button>
	</div>

	<nav class="flex-1 overflow-y-auto px-2 pb-2">
		{#if !app.chats.length}
			<p class="px-3 py-6 text-center text-xs text-gray-500">No conversations yet</p>
		{/if}
		{#each groups as [label, list] (label)}
			<div class="mt-3 px-3 pb-1 text-xs font-medium text-gray-500">{label}</div>
			{#each list as c (c.id)}
				<div
					class="group relative flex items-center rounded-lg {app.current?.id === c.id
						? 'bg-gray-200 dark:bg-gray-850'
						: 'hover:bg-gray-100 dark:hover:bg-gray-900'}"
				>
					{#if editingId === c.id}
						<input
							class="w-full rounded-lg bg-transparent px-3 py-2 outline-none ring-1 ring-gray-400"
							bind:value={editTitle}
							use:focus
							onkeydown={(e) => {
								if (e.key === 'Enter') commitRename();
								if (e.key === 'Escape') editingId = null;
							}}
							onblur={commitRename}
						/>
					{:else}
						<button
							class="w-full truncate px-3 py-2 text-left"
							onclick={() => app.openChat(c.id)}
							ondblclick={() => startRename(c)}
							title={c.title}
						>
							{c.title}
						</button>
						<div
							class="absolute right-1 hidden items-center gap-0.5 rounded-md bg-inherit group-hover:flex"
						>
							<button class="rounded p-1 text-gray-500 hover:text-gray-900 dark:hover:text-white" title="Rename" onclick={() => startRename(c)}>
								<Icon name="pencil" class="size-3.5" />
							</button>
							<button class="rounded p-1 text-gray-500 hover:text-red-500" title="Delete" onclick={() => remove(c)}>
								<Icon name="trash" class="size-3.5" />
							</button>
						</div>
					{/if}
				</div>
			{/each}
		{/each}
	</nav>

	<div class="flex items-center gap-1 border-t border-gray-200 p-2 dark:border-gray-850">
		<button
			class="flex flex-1 items-center gap-2 rounded-lg px-3 py-2 hover:bg-gray-200 dark:hover:bg-gray-850"
			onclick={onSettings}
		>
			<Icon name="settings" class="size-4" /> Settings
		</button>
		<button
			class="rounded-lg p-2 hover:bg-gray-200 dark:hover:bg-gray-850"
			onclick={() => app.toggleTheme()}
			title="Toggle theme"
		>
			<Icon name={app.dark ? 'sun' : 'moon'} class="size-4" />
		</button>
	</div>
</aside>
