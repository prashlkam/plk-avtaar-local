<script lang="ts">
	import { onMount, tick } from 'svelte';
	import Avatar from '$lib/components/Avatar.svelte';
	import AvatarMode from '$lib/components/AvatarMode.svelte';
	import AvatarPanel from '$lib/components/AvatarPanel.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import Message from '$lib/components/Message.svelte';
	import PromptBox from '$lib/components/PromptBox.svelte';
	import SettingsModal from '$lib/components/SettingsModal.svelte';
	import SetupDialog from '$lib/components/SetupDialog.svelte';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import { app } from '$lib/state.svelte';

	let settingsOpen = $state(false);
	let voiceBannerDismissed = $state(false);
	let scroller: HTMLDivElement | undefined = $state();
	let stickToBottom = true;

	const suggestions = [
		'Tell me a fun fact about space',
		'Help me plan a relaxing weekend',
		'Explain how a neural network learns',
		'Write a short poem about the monsoon'
	];

	onMount(() => {
		// On phones the sidebar starts closed and opens as an overlay.
		if (window.innerWidth < 768 && app.sidebarOpen) app.sidebarOpen = false;
		app.init();
	});

	function closeSidebarOnMobile() {
		if (window.innerWidth < 768 && app.sidebarOpen) app.toggleSidebar();
	}

	function onScroll() {
		if (!scroller) return;
		stickToBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 80;
	}

	// Follow the stream while the user is at the bottom.
	$effect(() => {
		const last = app.messages.at(-1);
		void last?.content;
		void app.messages.length;
		if (stickToBottom) tick().then(() => scroller?.scrollTo({ top: scroller.scrollHeight }));
	});

	$effect(() => {
		void app.current?.id;
		stickToBottom = true;
	});
</script>

<svelte:head>
	<title>{app.current?.title && app.current.title !== 'New chat' ? `${app.current.title} · Avtaar` : 'Avtaar'}</title>
</svelte:head>

<div class="flex h-dvh overflow-hidden">
	{#if app.sidebarOpen}
		<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
		<div class="fixed inset-0 z-30 bg-black/40 md:hidden" onclick={() => app.toggleSidebar()}></div>
		<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
		<div
			class="fixed inset-y-0 left-0 z-40 shadow-xl md:static md:z-auto md:shadow-none"
			onclick={(e) => (e.target as HTMLElement).closest('nav button') && closeSidebarOnMobile()}
		>
			<Sidebar onSettings={() => (settingsOpen = true)} />
		</div>
	{/if}

	<main class="flex min-w-0 flex-1 flex-col">
		<header class="flex h-14 shrink-0 items-center gap-2 px-3">
			{#if !app.sidebarOpen}
				<button class="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-850" onclick={() => app.toggleSidebar()} title="Open sidebar">
					<Icon name="menu" class="size-5" />
				</button>
				<button class="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-850" onclick={() => app.newChat()} title="New chat">
					<Icon name="pencil" class="size-5" />
				</button>
			{/if}

			<div class="relative min-w-0">
				<select
					class="w-full max-w-[38vw] appearance-none truncate rounded-lg bg-transparent py-1.5 pr-8 pl-3 text-lg font-medium hover:bg-gray-100 focus:outline-none sm:max-w-xs dark:hover:bg-gray-850"
					value={app.model}
					onchange={(e) => app.setModel((e.target as HTMLSelectElement).value)}
					disabled={app.streaming || !app.models.length}
					aria-label="Model"
				>
					{#each app.models as m (m.name)}
						<option value={m.name} class="text-base dark:bg-gray-850">{m.name}</option>
					{:else}
						<option value="">No models</option>
					{/each}
				</select>
				<Icon name="chevron" class="pointer-events-none absolute top-1/2 right-2 size-4 -translate-y-1/2 text-gray-500" />
			</div>
			{#if app.warming}
				<span class="flex items-center gap-1.5 text-xs text-gray-500" title="Loading the model into memory so replies start faster">
					<span class="size-3 animate-spin rounded-full border-2 border-gray-400 border-t-transparent"></span>
					<span class="hidden sm:inline">Loading model…</span>
				</span>
			{/if}

			<div class="ml-auto flex items-center gap-1">
				<button
					class="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-850"
					onclick={() => app.toggleAvatarMode()}
					title="Avatar mode: full-screen Avtaar with captions"
				>
					<Icon name="expand" class="size-5" />
				</button>
				<button
					class="rounded-lg p-2 text-gray-500 hover:bg-gray-100 disabled:opacity-40 dark:hover:bg-gray-850"
					onclick={() => app.toggleVoice()}
					disabled={!app.voiceAvailable}
					title={app.voiceAvailable ? (app.voiceOn ? 'Mute voice replies' : 'Speak replies aloud') : 'VoiceStudio is not running'}
					aria-pressed={app.voiceOn}
				>
					<Icon name={app.voiceOn && app.voiceAvailable ? 'speaker' : 'mute'} class="size-5" />
				</button>
				<button
					class="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-850 {app.avatarOpen ? 'text-gray-900 dark:text-white' : ''}"
					onclick={() => app.toggleAvatar()}
					title="Toggle Avtaar panel"
				>
					<Icon name="panel" class="size-5" />
				</button>
			</div>
		</header>

		{#if app.avatarOpen && app.avatar !== 'idle'}
			<!-- Small floating Avtaar for narrow screens where the side panel is hidden. -->
			<div class="fixed right-4 bottom-32 z-20 lg:hidden">
				<Avatar class="size-20" />
			</div>
		{/if}

		{#if app.health && !app.health.ollama.ok}
			<div class="mx-3 mb-2 flex items-start gap-2 rounded-xl border border-red-300 bg-red-50 px-4 py-2.5 text-sm text-red-700 md:mx-auto md:w-full md:max-w-3xl dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
				<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
				<div class="flex-1">
					<strong>Ollama is not reachable.</strong>
					{app.health.ollama.hint}
				</div>
				<button class="shrink-0 rounded-lg px-2 py-0.5 font-medium underline-offset-2 hover:underline" onclick={() => (app.setupOpen = true)}>Run setup</button>
				<button class="shrink-0 rounded-lg px-2 py-0.5 font-medium underline-offset-2 hover:underline" onclick={() => app.recheck()}>Retry</button>
			</div>
		{:else if app.health && !app.health.voicestudio.ok && !voiceBannerDismissed}
			<div class="mx-3 mb-2 flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm text-amber-800 md:mx-auto md:w-full md:max-w-3xl dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
				<Icon name="mute" class="mt-0.5 size-4 shrink-0" />
				<div class="flex-1">
					<strong>Voice is off.</strong> VoiceStudio isn't running on {app.health.voicestudio.url || ':3900'}. Start it
					(and download one speech-to-text and one text-to-speech model) to talk with Avtaar, or let
					<button class="font-medium underline underline-offset-2" onclick={() => (app.setupOpen = true)}>Initial setup</button> install it for you.
					It connects automatically.
				</div>
				<button class="shrink-0 rounded-lg px-2 py-0.5 font-medium underline-offset-2 hover:underline" onclick={() => app.recheck()}>Retry</button>
				<button class="shrink-0 rounded-lg p-1 hover:bg-amber-100 dark:hover:bg-amber-900/40" onclick={() => (voiceBannerDismissed = true)} aria-label="Dismiss">
					<Icon name="x" class="size-3.5" />
				</button>
			</div>
		{/if}

		<div class="flex-1 overflow-y-auto" bind:this={scroller} onscroll={onScroll}>
			{#if !app.messages.length}
				<div class="mx-auto flex h-full max-w-3xl flex-col items-center justify-center px-4 pb-10">
					<img src={app.avatarImages.idle} alt="" class="size-20 rounded-full object-cover shadow" />
					<h1 class="mt-4 text-2xl font-semibold">Hello, I'm Avtaar</h1>
					<p class="mt-1 text-gray-500">How can I help you today?</p>
					<div class="mt-8 grid w-full max-w-xl grid-cols-1 gap-2 sm:grid-cols-2">
						{#each suggestions as s (s)}
							<button
								class="rounded-xl border border-gray-200 px-4 py-3 text-left text-sm text-gray-600 transition hover:bg-gray-50 dark:border-gray-800 dark:text-gray-300 dark:hover:bg-gray-850"
								onclick={() => app.send(s)}
								disabled={app.streaming}
							>
								{s}
							</button>
						{/each}
					</div>
				</div>
			{:else}
				<div class="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6">
					{#each app.messages as m, i (m.id)}
						<Message message={m} isLast={i === app.messages.length - 1} />
					{/each}
				</div>
			{/if}
		</div>

		<PromptBox />
	</main>

	{#if app.avatarOpen}
		<div class="hidden lg:block">
			<AvatarPanel />
		</div>
	{/if}
</div>

{#if app.avatarMode}
	<AvatarMode />
{/if}

<SettingsModal bind:open={settingsOpen} />
<SetupDialog bind:open={app.setupOpen} />

{#if app.toast}
	<div
		class="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-xl px-4 py-2.5 text-sm shadow-lg {app.toast.kind === 'error'
			? 'bg-red-600 text-white'
			: 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'}"
		role="status"
	>
		{app.toast.text}
	</div>
{/if}
