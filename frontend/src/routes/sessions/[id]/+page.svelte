<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { getSession } from '$lib/api/client';
	import type { Session } from '$lib/types/api';
	import HistoricalWaveform from '$lib/components/HistoricalWaveform.svelte';

	let session = $state<Session | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	const sessionId = $derived(parseInt($page.url.pathname.split('/').pop() || '0'));

	onMount(async () => {
		try {
			// Load session details (waveform component will load samples dynamically)
			session = await getSession(sessionId);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load session';
		} finally {
			loading = false;
		}
	});

	function formatDate(timestamp: number): string {
		return new Date(timestamp * 1000).toLocaleString();
	}

	function formatDuration(seconds: number | null): string {
		if (seconds === null || seconds === 0) return '0s';
		const mins = Math.floor(seconds / 60);
		const secs = Math.floor(seconds % 60);
		const hours = Math.floor(mins / 60);
		const remainingMins = mins % 60;

		if (hours > 0) {
			return `${hours}h ${remainingMins}m ${secs}s`;
		} else if (mins > 0) {
			return `${mins}m ${secs}s`;
		}
		return `${secs}s`;
	}
</script>

<div class="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
	<!-- Header -->
	<header class="border-b border-gray-200 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
		<div class="container mx-auto px-6 py-4 max-w-7xl">
			<div class="flex items-center gap-4">
				<a
					href="/sessions"
					class="text-gray-500 hover:text-gray-700 transition-colors"
					aria-label="Back to sessions"
				>
					<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M10 19l-7-7m0 0l7-7m-7 7h18"
						/>
					</svg>
				</a>
				<div class="flex-1">
					{#if session}
						<h1 class="text-2xl font-bold text-gray-900">Session #{session.id}</h1>
						<p class="text-sm text-gray-500">{formatDate(session.start_time)}</p>
					{:else}
						<h1 class="text-2xl font-bold text-gray-900">Loading...</h1>
					{/if}
				</div>
				<a
					href="/"
					class="text-sm text-gray-600 hover:text-gray-900 transition-colors font-medium"
				>
					Live Dashboard →
				</a>
			</div>
		</div>
	</header>

	<!-- Main Content -->
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
								Start Time
							</dt>
							<dd class="text-sm font-medium text-gray-900">
								{new Date(session.start_time * 1000).toLocaleTimeString()}
							</dd>
						</div>
					</dl>

					{#if session.devices.length > 0}
						<div class="mt-6 pt-6 border-t border-gray-200">
							<h3 class="text-sm font-semibold text-gray-700 mb-3">Connected Devices</h3>
							<div class="flex flex-wrap gap-2">
								{#each session.devices as device}
									<span
										class="bg-blue-50 text-blue-700 text-sm px-3 py-1.5 rounded-lg font-mono border border-blue-200"
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
