<script lang="ts">
	import { app } from '$lib/state.svelte';

	// Static image normally; the animated image only while voice audio is audible.
	// Both stay mounted so the swap is instant (no reload flicker).
	let { class: cls = 'size-56', ring = true }: { class?: string; ring?: boolean } = $props();

	const speaking = $derived(app.avatar === 'speaking');
	const ringColor = $derived(
		app.avatar === 'thinking'
			? 'ring-amber-400/60'
			: app.avatar === 'speaking'
				? 'ring-emerald-400/70'
				: app.avatar === 'listening'
					? 'ring-red-400/70'
					: 'ring-gray-200 dark:ring-gray-800'
	);
</script>

<div
	class="relative shrink-0 overflow-hidden rounded-full bg-gradient-to-b from-indigo-100 to-indigo-200 shadow-lg transition dark:from-indigo-950 dark:to-gray-900 {ring
		? `ring-4 ${ringColor}`
		: ''} {cls}"
>
	<img
		src={app.avatarImages.idle}
		alt="Avtaar"
		class="absolute inset-0 size-full object-cover"
		style:visibility={speaking ? 'hidden' : 'visible'}
	/>
	<img
		src={app.avatarImages.talking}
		alt=""
		class="absolute inset-0 size-full object-cover"
		style:visibility={speaking ? 'visible' : 'hidden'}
	/>
</div>
