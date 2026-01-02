<script lang="ts">
	import { onMount } from 'svelte';
	import { getSessions } from '$lib/api/client';
	import type { Session } from '$lib/types/api';

	let sessions = $state<Session[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			const response = await getSessions();
			sessions = response.sessions;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load sessions';
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
		if (mins > 0) {
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
					href="/"
					class="text-gray-500 hover:text-gray-700 transition-colors"
					aria-label="Back to dashboard"
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
				<div>
					<h1 class="text-2xl font-bold text-gray-900">Recording Sessions</h1>
					<p class="text-sm text-gray-500">Browse and view past ECG recordings</p>
				</div>
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
					<p class="text-sm text-gray-500 mt-4">Loading sessions...</p>
				</div>
			</div>
		{:else if error}
			<div class="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
				<p class="text-red-800 font-medium">Error loading sessions</p>
				<p class="text-red-600 text-sm mt-1">{error}</p>
			</div>
		{:else if sessions.length === 0}
			<div class="bg-white border border-gray-200 rounded-xl shadow-sm p-12 text-center">
				<div class="text-6xl mb-4">📊</div>
				<h3 class="text-lg font-semibold text-gray-900 mb-2">No sessions found</h3>
				<p class="text-sm text-gray-500">Start recording to create your first session</p>
			</div>
		{:else}
			<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
				{#each sessions as session (session.id)}
					<a
						href="/sessions/{session.id}"
						class="bg-white border border-gray-200 rounded-xl shadow-sm hover:shadow-lg transition-shadow p-6 block"
					>
						<div class="flex items-start justify-between mb-4">
							<div>
								<h3 class="text-lg font-semibold text-gray-900">Session #{session.id}</h3>
								<p class="text-xs text-gray-500 mt-1">
									{formatDate(session.start_time)}
								</p>
							</div>
							<div
								class="bg-green-100 text-green-700 text-xs font-medium px-2 py-1 rounded-full"
							>
								{session.sample_count.toLocaleString()} samples
							</div>
						</div>

						<div class="space-y-3">
							<div class="flex items-center justify-between text-sm">
								<span class="text-gray-500">Duration</span>
								<span class="font-medium text-gray-900">
									{formatDuration(session.duration_seconds)}
								</span>
							</div>

							<div class="flex items-center justify-between text-sm">
								<span class="text-gray-500">Devices</span>
								<span class="font-medium text-gray-900">{session.device_count}</span>
							</div>

							{#if session.devices.length > 0}
								<div class="pt-3 border-t border-gray-100">
									<div class="flex flex-wrap gap-2">
										{#each session.devices as device}
											<span
												class="bg-gray-100 text-gray-700 text-xs px-2 py-1 rounded-md font-mono"
											>
												{device.split(' ').slice(-1)[0]}
											</span>
										{/each}
									</div>
								</div>
							{/if}
						</div>

						<div class="mt-4 pt-4 border-t border-gray-100">
							<span class="text-sm text-blue-600 font-medium hover:text-blue-700">
								View Recording →
							</span>
						</div>
					</a>
				{/each}
			</div>

			<div class="mt-8 text-center text-sm text-gray-500">
				Showing {sessions.length} session{sessions.length === 1 ? '' : 's'}
			</div>
		{/if}
	</main>
</div>
