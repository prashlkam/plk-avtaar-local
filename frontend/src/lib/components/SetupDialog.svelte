<script lang="ts">
	import { readSSE } from '$lib/api';
	import { app } from '$lib/state.svelte';
	import Icon from './Icon.svelte';

	let { open = $bindable(false) }: { open: boolean } = $props();

	type Status = 'pending' | 'running' | 'ok' | 'warn' | 'fail' | 'skip';
	interface Row {
		id: string;
		title: string;
		status: Status;
		message?: string;
		hint?: string;
		logs: string[];
		browser?: boolean;
	}

	let rows = $state<Row[]>([]);
	let running = $state(false);
	let finished = $state(false);
	let hasRunBefore = $state(false);
	let expanded = $state<Record<string, boolean>>({});

	const BROWSER_ROWS: Row[] = [
		{ id: 'mic', title: 'Microphone (this browser)', status: 'pending', logs: [], browser: true },
		{ id: 'speakers', title: 'Speakers (this browser)', status: 'pending', logs: [], browser: true }
	];

	const counts = $derived(
		rows.reduce<Record<string, number>>((acc, r) => ((acc[r.status] = (acc[r.status] ?? 0) + 1), acc), {})
	);

	// On open: show the last report, and re-attach if a run is still going.
	$effect(() => {
		if (!open) return;
		void (async () => {
			try {
				const st = await fetch('/api/setup/status').then((r) => r.json());
				if (st.report?.steps?.length && !running) {
					hasRunBefore = true;
					rows = st.report.steps.map((s: Row) => ({ ...s, logs: [] }));
					finished = st.report.done;
				}
				if (st.running && !running) attach(fetch('/api/setup/stream'));
			} catch {
				/* gateway down: the Run button will report it */
			}
		})();
	});

	function row(id: string) {
		return rows.find((r) => r.id === id);
	}

	async function attach(resPromise: Promise<Response>) {
		running = true;
		finished = false;
		try {
			const res = await resPromise;
			if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? `HTTP ${res.status}`);
			await readSSE(res, (event, d) => {
				const data = d as Record<string, unknown>;
				if (event === 'plan') {
					rows = [
						...(data.steps as { id: string; title: string }[]).map((s) => ({ ...s, status: 'pending' as Status, logs: [] })),
						...BROWSER_ROWS.map((r) => ({ ...r, logs: [] }))
					];
				} else if (event === 'step') {
					const r = row(data.id as string);
					if (!r) return;
					r.status = data.status as Status;
					r.message = data.message as string;
					r.hint = data.hint as string | undefined;
					if (r.status === 'fail' || r.status === 'warn') expanded[r.id] = true;
				} else if (event === 'log') {
					const r = row(data.id as string);
					if (r) r.logs = [...r.logs.slice(-40), data.line as string];
				}
			});
			await browserChecks();
		} catch (e) {
			app.notify(`Setup could not run: ${(e as Error).message}`);
		} finally {
			running = false;
			finished = true;
			hasRunBefore = true;
			// Pick up whatever setup changed (models, settings, VoiceStudio).
			await app.recheck();
			await Promise.allSettled([app.loadSettings(), app.refreshModels()]);
		}
	}

	function start() {
		app.speaker.unlock(); // inside the click, so the speaker test can play audio
		expanded = {};
		attach(fetch('/api/setup/run', { method: 'POST' }));
	}

	async function browserChecks() {
		// Microphone: permission + is any sound coming in?
		const mic = row('mic');
		if (mic) {
			mic.status = 'running';
			mic.message = 'Asking for microphone access…';
			try {
				const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
				const ctx = new AudioContext();
				const an = ctx.createAnalyser();
				ctx.createMediaStreamSource(stream).connect(an);
				const buf = new Uint8Array(an.fftSize);
				let peak = 0;
				mic.message = 'Listening for 1.5 s…';
				const end = performance.now() + 1500;
				while (performance.now() < end) {
					await new Promise((r) => setTimeout(r, 50));
					an.getByteTimeDomainData(buf);
					for (const v of buf) peak = Math.max(peak, Math.abs(v - 128) / 128);
				}
				stream.getTracks().forEach((t) => t.stop());
				void ctx.close();
				const label = stream.getAudioTracks()[0]?.label || 'default microphone';
				if (peak < 0.002) {
					mic.status = 'warn';
					mic.message = `Access granted (${label}), but it picked up complete silence.`;
					mic.hint = 'Check that the microphone is not muted and is the selected input device.';
				} else {
					mic.status = 'ok';
					mic.message = `Microphone works (${label}).`;
				}
			} catch (e) {
				const err = e as DOMException;
				mic.status = err.name === 'NotAllowedError' ? 'fail' : 'warn';
				mic.message =
					err.name === 'NotAllowedError' ? 'Microphone access was denied.' : `No usable microphone (${err.name}).`;
				mic.hint = 'Allow microphone access for this page (address-bar permissions), then run setup again.';
			}
		}

		// Speakers: play the phrase VoiceStudio just spoke.
		const spk = row('speakers');
		if (spk) {
			if (row('tts-test')?.status !== 'ok') {
				spk.status = 'skip';
				spk.message = 'Skipped because the text-to-speech test did not pass.';
			} else {
				spk.status = 'running';
				spk.message = 'Playing the test phrase…';
				const played = await playTest();
				spk.status = played ? 'ok' : 'warn';
				spk.message = played
					? 'Played “Hello! Your local avatar is ready to talk.” You should have heard it.'
					: 'The browser blocked or failed to play the test audio.';
				if (!played) spk.hint = 'Click “Play test phrase” below, and check your output device and volume.';
			}
		}
		// Open the fix hints of any browser check that didn't pass.
		for (const r of [mic, spk]) if (r && (r.status === 'fail' || r.status === 'warn')) expanded[r.id] = true;
	}

	async function playTest(): Promise<boolean> {
		try {
			const a = new Audio(`/api/setup/test-audio?t=${Date.now()}`);
			await a.play();
			await new Promise<void>((r) => {
				a.onended = () => r();
				a.onerror = () => r();
			});
			return true;
		} catch {
			return false;
		}
	}

	const icon: Record<Status, { name: string; cls: string }> = {
		pending: { name: 'circle', cls: 'text-gray-300 dark:text-gray-600' },
		running: { name: '', cls: '' },
		ok: { name: 'check', cls: 'text-emerald-500' },
		warn: { name: 'alert', cls: 'text-amber-500' },
		fail: { name: 'x', cls: 'text-red-500' },
		skip: { name: 'minus', cls: 'text-gray-400' }
	};
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onclick={() => (open = false)}>
		<div
			class="flex max-h-[90dvh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-2xl dark:bg-gray-850"
			role="dialog"
			aria-modal="true"
			aria-labelledby="setup-title"
			tabindex="-1"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => e.key === 'Escape' && (open = false)}
		>
			<div class="flex items-start justify-between gap-4 border-b border-gray-100 p-5 dark:border-gray-800">
				<div>
					<h2 id="setup-title" class="text-lg font-semibold">Initial setup</h2>
					<p class="mt-1 text-sm text-gray-500">
						Installs, configures and tests everything Avtaar needs: Ollama and its model, VoiceStudio (speech), and your
						microphone and speakers. If something is already installed, it's reconfigured and tested again.
					</p>
				</div>
				<button class="rounded-lg p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800" onclick={() => (open = false)} aria-label="Close">
					<Icon name="x" />
				</button>
			</div>

			<div class="min-h-0 flex-1 overflow-y-auto p-5">
				{#if !rows.length}
					<div class="rounded-xl bg-gray-50 p-4 text-sm text-gray-600 dark:bg-gray-900 dark:text-gray-300">
						<p class="font-medium">What will happen</p>
						<ul class="mt-2 list-disc space-y-1 pl-5">
							<li>Checks Ollama, starts it if needed, downloads the selected model if it's missing, and tests a reply.</li>
							<li>
								Uses VoiceStudio if it's running. If it isn't installed, installs it as a local Podman/Docker container
								(a download of several GB). The first voice test can download speech models (~2.4 GB).
							</li>
							<li>Tests text-to-speech, speech-to-text and live transcription, then your microphone and speakers.</li>
							<li>Everything stays on this computer. Steps that need administrator rights tell you the exact command to run.</li>
						</ul>
					</div>
				{:else}
					<ol class="space-y-1">
						{#each rows as r (r.id)}
							<li class="rounded-xl px-2 py-2 {r.status === 'running' ? 'bg-gray-50 dark:bg-gray-900' : ''}">
								<div class="flex items-start gap-3">
									<span class="mt-0.5 flex size-5 shrink-0 items-center justify-center">
										{#if r.status === 'running'}
											<span class="size-4 animate-spin rounded-full border-2 border-gray-400 border-t-transparent"></span>
										{:else if r.status === 'pending'}
											<span class="size-3.5 rounded-full border-2 border-gray-300 dark:border-gray-600"></span>
										{:else}
											<Icon name={icon[r.status].name} class="size-4 {icon[r.status].cls}" stroke={2.5} />
										{/if}
									</span>
									<div class="min-w-0 flex-1">
										<div class="flex items-center gap-2">
											<span class="text-sm font-medium {r.status === 'pending' || r.status === 'skip' ? 'text-gray-400' : ''}">{r.title}</span>
											{#if r.hint || r.logs.length}
												<button
													class="ml-auto text-xs text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
													onclick={() => (expanded[r.id] = !expanded[r.id])}
												>
													{expanded[r.id] ? 'Less' : 'Details'}
												</button>
											{/if}
										</div>
										{#if r.message && r.status !== 'pending'}
											<p class="mt-0.5 text-xs break-words text-gray-500 dark:text-gray-400">{r.message}</p>
										{/if}
										{#if expanded[r.id]}
											{#if r.hint}
												<p
													class="mt-1.5 rounded-lg px-2.5 py-1.5 text-xs break-words whitespace-pre-wrap {r.status === 'fail'
														? 'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300'
														: 'bg-amber-50 text-amber-800 dark:bg-amber-950/30 dark:text-amber-200'}"
												>
													{r.hint}
												</p>
											{/if}
											{#if r.logs.length}
												<pre class="mt-1.5 max-h-32 overflow-auto rounded-lg bg-gray-900 p-2 text-[11px] leading-snug text-gray-300">{r.logs.join('\n')}</pre>
											{/if}
										{/if}
									</div>
								</div>
							</li>
						{/each}
					</ol>
				{/if}
			</div>

			<div class="flex flex-wrap items-center gap-2 border-t border-gray-100 p-4 text-sm dark:border-gray-800">
				{#if finished && rows.length}
					<span class="mr-auto text-xs text-gray-500">
						{#if counts.fail}
							<span class="font-medium text-red-500">{counts.fail} failed</span> ·
						{/if}
						{#if counts.warn}
							<span class="font-medium text-amber-500">{counts.warn} with warnings</span> ·
						{/if}
						{counts.ok ?? 0} passed{counts.skip ? ` · ${counts.skip} skipped` : ''}
					</span>
				{:else if running}
					<span class="mr-auto text-xs text-gray-500">Setup keeps running if you close this window.</span>
				{:else}
					<span class="mr-auto"></span>
				{/if}
				{#if finished && row('tts-test')?.status === 'ok'}
					<button class="rounded-full px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800" onclick={playTest}>Play test phrase</button>
				{/if}
				<button class="rounded-full px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-800" onclick={() => (open = false)}>
					{running ? 'Hide' : 'Close'}
				</button>
				<button
					class="flex items-center gap-2 rounded-full bg-gray-900 px-4 py-2 font-medium text-white disabled:opacity-50 dark:bg-white dark:text-gray-900"
					onclick={start}
					disabled={running}
				>
					{#if running}
						<span class="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"></span> Running…
					{:else}
						{hasRunBefore ? 'Run again (reconfigure & retest)' : 'Start setup'}
					{/if}
				</button>
			</div>
		</div>
	</div>
{/if}
