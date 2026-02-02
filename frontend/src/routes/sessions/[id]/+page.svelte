<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '$lib/api/client';
	import Header from '$lib/components/Header.svelte';
	import HistoricalWaveforms from '$lib/components/HistoricalWaveforms.svelte';
	import { formatDuration, formatFullTimestamp } from '$lib/utils/format';
	import { createDeviceNicknameMap, getDisplayNameFromMap } from '$lib/utils/device-names';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const deviceNicknameMap = $derived(createDeviceNicknameMap(data.devices));

	let deleting = $state(false);

	function handleExport() {
		const exportUrl = api.getSessionExportUrl(data.session.id);
		window.open(exportUrl, '_blank');
	}

	async function handleDelete() {
		if (
			!confirm(
				`Are you sure you want to delete session #${data.session.id}? This cannot be undone.`
			)
		) {
			return;
		}

		deleting = true;

		try {
			const result = await api.deleteSession(data.session.id);
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
	<title>Session #{data.session.id} - ECG Streaming</title>
</svelte:head>

<div class="min-h-screen bg-linear-to-br from-gray-50 to-gray-100">
	<Header>
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
	</Header>

	<main class="container mx-auto px-6 py-8 max-w-7xl">
		<div class="space-y-6">
			<!-- Session Stats -->
			<div class="bg-white border border-gray-200 rounded-xl shadow-lg p-6">
				<h2 class="text-lg font-semibold text-gray-900 mb-4">Session Information</h2>
				<dl class="grid grid-cols-2 md:grid-cols-4 gap-4">
					<div class="bg-gray-50 rounded-lg p-4">
						<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Duration</dt>
						<dd class="text-xl font-bold text-gray-900">
							{formatDuration(data.session.duration_seconds)}
						</dd>
					</div>
					<div class="bg-gray-50 rounded-lg p-4">
						<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Samples</dt>
						<dd class="text-xl font-bold text-gray-900">
							{data.session.sample_count.toLocaleString()}
						</dd>
					</div>
					<div class="bg-gray-50 rounded-lg p-4">
						<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Devices</dt>
						<dd class="text-xl font-bold text-gray-900">{data.session.device_count}</dd>
					</div>
					<div class="bg-gray-50 rounded-lg p-4">
						<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Started</dt>
						<dd class="text-xl font-bold text-gray-900">
							{formatFullTimestamp(data.session.start_time)}
						</dd>
					</div>
				</dl>

				{#if data.session.notes}
					<div class="mt-6 pt-6 border-t border-gray-200">
						<h3 class="text-sm font-semibold text-gray-700 mb-2">Notes</h3>
						<p class="text-gray-900 text-sm">{data.session.notes}</p>
					</div>
				{/if}

				{#if data.session.devices.length > 0}
					<div class="mt-6 pt-6 border-t border-gray-200">
						<h3 class="text-sm font-semibold text-gray-700 mb-3">Connected Devices</h3>
						<div class="flex flex-wrap gap-2">
							{#each data.session.devices as deviceId (deviceId)}
								{@const displayName = getDisplayNameFromMap(deviceId, deviceNicknameMap)}
								<span
									class="bg-status-info text-status-info-fg text-sm px-3 py-1.5 rounded-lg border border-status-info-border"
									title={deviceId !== displayName ? deviceId : undefined}
								>
									{displayName}
								</span>
							{/each}
						</div>
					</div>
				{/if}
			</div>

			<!-- Waveform Visualization -->
			<HistoricalWaveforms session={data.session} loading={false} deviceNicknames={deviceNicknameMap} />
		</div>
	</main>
</div>
