<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api/client';
	import type { Session } from '$lib/types/api';
	import Header from '$lib/components/Header.svelte';
	import HistoricalWaveform from '$lib/components/HistoricalWaveform.svelte';
	import { formatFullTimestamp, formatDuration } from '$lib/utils/format';

	let session = $state<Session | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let deleting = $state(false);

	const sessionId = $derived(parseInt(page.url.pathname.split('/').pop() || '0'));

	onMount(async () => {
		try {
			// Load session details (waveform component will load samples dynamically)
			session = await api.getSession(sessionId);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load session';
		} finally {
			loading = false;
		}
	});

	function handleExport() {
		if (!session) return;
		const exportUrl = api.getSessionExportUrl(session.id);
		window.open(exportUrl, '_blank');
	}

	async function handleDelete() {
		if (!session) return;

		if (
			!confirm(`Are you sure you want to delete session #${session.id}? This cannot be undone.`)
		) {
			return;
		}

		deleting = true;

		try {
			const result = await api.deleteSession(session.id);
			if (result.success) {
				// Navigate back to sessions list
				await goto('/sessions');
			} else {
				alert('Failed to delete session');
				deleting = false;
			}
		} catch (e) {
			alert(e instanceof Error ? e.message : 'Delete failed');
			deleting = false;
		}
	}
</script>

<svelte:head>
	<title>{session ? `Session #${session.id}` : 'Loading...'} - ECG Streaming</title>
</svelte:head>

<div class="min-h-screen bg-linear-to-br from-gray-50 to-gray-100">
	<Header>
		{#if session}
			<button
				onclick={handleExport}
				class="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
			>
				<svg
					class="w-4 h-4"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
					xmlns="http://www.w3.org/2000/svg"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
					/>
				</svg>
				Export CSV
			</button>
			<button
				onclick={handleDelete}
				disabled={deleting}
				class="flex items-center gap-2 px-4 py-2 bg-status-error-fg hover:bg-status-error-border disabled:bg-gray-400 text-white text-sm font-medium rounded-lg transition-colors disabled:cursor-not-allowed"
			>
				{#if deleting}
					<div
						class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"
					></div>
				{:else}
					<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
						/>
					</svg>
				{/if}
				Delete
			</button>
		{/if}
	</Header>

	<main class="container mx-auto px-6 py-8 max-w-7xl">
		{#if loading}
			<div class="flex items-center justify-center py-16">
				<div class="text-center">
					<div
						class="inline-block w-12 h-12 border-4 border-gray-200 border-t-gray-600 rounded-full animate-spin"
					></div>
					<p class="text-sm text-gray-500 mt-4">Loading session...</p>
				</div>
			</div>
		{:else if error}
			<div class="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
				<p class="text-red-800 font-medium">Error loading session</p>
				<p class="text-red-600 text-sm mt-1">{error}</p>
			</div>
		{:else if session}
			<div class="space-y-6">
				<!-- Session Stats -->
				<div class="bg-white border border-gray-200 rounded-xl shadow-lg p-6">
					<h2 class="text-lg font-semibold text-gray-900 mb-4">Session Information</h2>
					<dl class="grid grid-cols-2 md:grid-cols-4 gap-4">
						<div class="bg-gray-50 rounded-lg p-4">
							<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
								Duration
							</dt>
							<dd class="text-xl font-bold text-gray-900">
								{formatDuration(session.duration_seconds)}
							</dd>
						</div>
						<div class="bg-gray-50 rounded-lg p-4">
							<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
								Samples
							</dt>
							<dd class="text-xl font-bold text-gray-900">
								{session.sample_count.toLocaleString()}
							</dd>
						</div>
						<div class="bg-gray-50 rounded-lg p-4">
							<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
								Devices
							</dt>
							<dd class="text-xl font-bold text-gray-900">{session.device_count}</dd>
						</div>
						<div class="bg-gray-50 rounded-lg p-4">
							<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
								Started
							</dt>
							<dd class="text-xl font-bold text-gray-900">
								{formatFullTimestamp(session.start_time)}
							</dd>
						</div>
					</dl>

					{#if session.devices.length > 0}
						<div class="mt-6 pt-6 border-t border-gray-200">
							<h3 class="text-sm font-semibold text-gray-700 mb-3">Connected Devices</h3>
							<div class="flex flex-wrap gap-2">
								{#each session.devices as device (device)}
									<span
										class="bg-status-info text-status-info-fg text-sm px-3 py-1.5 rounded-lg font-mono border border-status-info-border"
									>
										{device}
									</span>
								{/each}
							</div>
						</div>
					{/if}
				</div>

				<!-- Waveform Visualization -->
				{#if session}
					<HistoricalWaveform {session} loading={false} />
				{/if}
			</div>
		{/if}
	</main>
</div>
