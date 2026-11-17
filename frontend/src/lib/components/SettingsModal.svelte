<script lang="ts">
	import { api } from '$lib/api';
	import { app } from '$lib/state.svelte';
	import Icon from './Icon.svelte';

	let { open = $bindable(false) }: { open: boolean } = $props();

	let systemPrompt = $state('');
	let temperature = $state(0.7);
	let defaultModel = $state('');
	let ttsVoice = $state('');
	let ttsSpeed = $state(1);
	let ttsModel = $state('');
	let autoSend = $state(true);
	let sttLanguage = $state('');
	let autoStopMs = $state(1500);
	let voices = $state<{ id: string; name: string; language?: string | null }[]>([]);
	let saving = $state(false);

	$effect(() => {
		if (open && app.settings) {
			systemPrompt = app.settings.system_prompt;
			temperature = app.settings.temperature;
			defaultModel = app.settings.default_model;
			ttsVoice = app.settings.tts_voice;
			ttsSpeed = app.settings.tts_speed;
			ttsModel = app.settings.tts_model;
			autoSend = app.settings.auto_send;
			sttLanguage = app.settings.stt_language;
			autoStopMs = app.settings.auto_stop_ms;
			if (app.voiceAvailable) {
				api
					.voices()
					.then((r) => (voices = r.voices))
					.catch(() => (voices = []));
			}
		}
	});

	async function save() {
		saving = true;
		try {
			await app.saveSettings({
				system_prompt: systemPrompt,
				temperature,
				default_model: defaultModel,
				tts_voice: ttsVoice.trim() || 'alloy',
				tts_speed: ttsSpeed,
				tts_model: ttsModel.trim() || 'tts-1',
				auto_send: autoSend,
				stt_language: sttLanguage.trim().toLowerCase(),
				auto_stop_ms: autoStopMs
			});
			open = false;
		} catch (e) {
			app.notify(`Could not save settings: ${(e as Error).message}`);
		} finally {
			saving = false;
		}
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4" onclick={() => (open = false)}>
		<div
			class="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl dark:bg-gray-850"
			role="dialog"
			aria-modal="true"
			aria-labelledby="settings-title"
			tabindex="-1"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => e.key === 'Escape' && (open = false)}
		>
			<div class="mb-5 flex items-center justify-between">
				<h2 id="settings-title" class="text-lg font-semibold">Settings</h2>
				<button class="rounded-lg p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800" onclick={() => (open = false)} aria-label="Close">
					<Icon name="x" />
				</button>
			</div>

			<div class="space-y-5 text-sm">
				<div class="flex items-center gap-3 rounded-xl border border-indigo-200 bg-indigo-50 p-4 dark:border-indigo-900/60 dark:bg-indigo-950/30">
					<Icon name="wrench" class="size-5 shrink-0 text-indigo-500" />
					<div class="flex-1">
						<p class="font-medium">Initial setup</p>
						<p class="text-xs text-gray-600 dark:text-gray-400">
							Install, configure and test Ollama, VoiceStudio, your mic and speakers. Safe to run again at any time.
						</p>
					</div>
					<button
						class="shrink-0 rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
						onclick={() => (app.setupOpen = true)}
					>
						Initial setup
					</button>
				</div>

				<label class="block">
					<span class="mb-1.5 block font-medium">Default model</span>
					<select bind:value={defaultModel} class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 dark:border-gray-700">
						{#each app.models as m (m.name)}
							<option value={m.name} class="dark:bg-gray-850">{m.name}{m.parameter_size ? ` (${m.parameter_size})` : ''}</option>
						{/each}
						{#if !app.models.some((m) => m.name === defaultModel)}
							<option value={defaultModel}>{defaultModel}</option>
						{/if}
					</select>
				</label>

				<label class="block">
					<span class="mb-1.5 block font-medium">System prompt / persona</span>
					<textarea
						bind:value={systemPrompt}
						rows="5"
						class="w-full resize-y rounded-lg border border-gray-200 bg-transparent px-3 py-2 dark:border-gray-700"
					></textarea>
				</label>

				<label class="block">
					<span class="mb-1.5 flex justify-between font-medium">
						Temperature <span class="font-normal text-gray-500">{temperature.toFixed(1)}</span>
					</span>
					<input type="range" min="0" max="2" step="0.1" bind:value={temperature} class="w-full accent-gray-900 dark:accent-white" />
				</label>

				<fieldset class="space-y-4 rounded-xl border border-gray-200 p-4 dark:border-gray-700">
					<legend class="px-1 font-medium">Voice (VoiceStudio)</legend>
					{#if !app.voiceAvailable}
						<p class="text-xs text-amber-600 dark:text-amber-400">
							VoiceStudio is not reachable on :3900. These settings apply once it is running.
						</p>
					{/if}
					<label class="block">
						<span class="mb-1.5 block">Voice</span>
						{#if voices.length}
							<select bind:value={ttsVoice} class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 dark:border-gray-700">
								{#each voices as v (v.id)}
									<option value={v.id} class="dark:bg-gray-850">{v.name}{v.language ? ` · ${v.language}` : ''}</option>
								{/each}
								{#if !voices.some((v) => v.id === ttsVoice)}
									<option value={ttsVoice}>{ttsVoice}</option>
								{/if}
							</select>
						{:else}
							<input bind:value={ttsVoice} placeholder="alloy" class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 dark:border-gray-700" />
						{/if}
					</label>
					<label class="block">
						<span class="mb-1.5 flex justify-between">Speed <span class="text-gray-500">{ttsSpeed.toFixed(2)}×</span></span>
						<input type="range" min="0.5" max="2" step="0.05" bind:value={ttsSpeed} class="w-full accent-gray-900 dark:accent-white" />
					</label>
					<label class="block">
						<span class="mb-1.5 block">TTS engine / model id</span>
						<input bind:value={ttsModel} placeholder="tts-1" class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 dark:border-gray-700" />
						<span class="mt-1 block text-xs text-gray-500">"tts-1" maps to VoiceStudio's active engine.</span>
					</label>
				</fieldset>

				<fieldset class="space-y-4 rounded-xl border border-gray-200 p-4 dark:border-gray-700">
					<legend class="px-1 font-medium">Voice input (push-to-talk)</legend>
					<label class="flex items-start gap-3">
						<input type="checkbox" bind:checked={autoSend} class="mt-0.5 size-4 accent-gray-900 dark:accent-white" />
						<span>
							Send automatically when I click Done
							<span class="block text-xs text-gray-500">Off: the transcript stays in the box so you can edit it before sending.</span>
						</span>
					</label>
					<label class="block">
						<span class="mb-1.5 block">Stop listening automatically</span>
						<select bind:value={autoStopMs} class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 dark:border-gray-700">
							<option value={0} class="dark:bg-gray-850">Off (click Done when finished)</option>
							<option value={1000} class="dark:bg-gray-850">After 1 second of silence</option>
							<option value={1500} class="dark:bg-gray-850">After 1.5 seconds of silence</option>
							<option value={2500} class="dark:bg-gray-850">After 2.5 seconds of silence</option>
							<option value={4000} class="dark:bg-gray-850">After 4 seconds of silence</option>
						</select>
					</label>
					<label class="block">
						<span class="mb-1.5 block">Spoken language</span>
						<input
							bind:value={sttLanguage}
							placeholder="auto-detect (or e.g. en, hi, ta)"
							maxlength="12"
							class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 dark:border-gray-700"
						/>
					</label>
				</fieldset>

				<fieldset class="rounded-xl border border-gray-200 p-4 dark:border-gray-700">
					<legend class="px-1 font-medium">Avtaar images</legend>
					<p class="mb-3 text-xs text-gray-500">
						Square images work best. The talking image is shown only while Avtaar's voice is playing, so use an
						animated GIF (or WebP) for it. PNG, JPEG, GIF or WebP, up to 8 MB.
					</p>
					<div class="grid grid-cols-2 gap-4">
						{#each [{ kind: 'idle' as const, label: 'Idle (static)' }, { kind: 'talking' as const, label: 'Talking (animated)' }] as slot (slot.kind)}
							<div class="flex flex-col items-center gap-2">
								<img
									src={app.avatarImages[slot.kind]}
									alt="{slot.label} preview"
									class="size-24 rounded-full bg-gray-100 object-cover ring-2 ring-gray-200 dark:bg-gray-800 dark:ring-gray-700"
								/>
								<span class="text-xs font-medium">{slot.label}</span>
								<label
									class="flex cursor-pointer items-center gap-1.5 rounded-full border border-gray-200 px-3 py-1 text-xs hover:bg-gray-100 dark:border-gray-700 dark:hover:bg-gray-800"
								>
									<Icon name="upload" class="size-3.5" /> Choose…
									<input
										type="file"
										accept="image/png,image/jpeg,image/gif,image/webp"
										class="sr-only"
										onchange={(e) => {
											const input = e.currentTarget as HTMLInputElement;
											const f = input.files?.[0];
											if (f) app.uploadAvatar(slot.kind, f);
											input.value = '';
										}}
									/>
								</label>
								{#if app.avatarImages.custom[slot.kind]}
									<button class="text-xs text-gray-500 underline-offset-2 hover:underline" onclick={() => app.resetAvatar(slot.kind)}>
										Use default
									</button>
								{/if}
							</div>
						{/each}
					</div>
				</fieldset>
			</div>

			<div class="mt-6 flex justify-end gap-2 text-sm">
				<button class="rounded-full px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-800" onclick={() => (open = false)}>Cancel</button>
				<button
					class="rounded-full bg-gray-900 px-4 py-2 font-medium text-white disabled:opacity-50 dark:bg-white dark:text-gray-900"
					onclick={save}
					disabled={saving}
				>
					{saving ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}
