<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { ECGWebSocket } from '$lib/api/websocket';
	import { getDevices } from '$lib/state/devices.svelte';
	import ECGWaveform from '$lib/components/ECGWaveform.svelte';
	import DeviceCard from '$lib/components/DeviceCard.svelte';
	import StatsPanel from '$lib/components/StatsPanel.svelte';
	import ConnectionStatus from '$lib/components/ConnectionStatus.svelte';
	import DeviceStatusPanel from '$lib/components/DeviceStatusPanel.svelte';

	let ws: ECGWebSocket;

	// Reactive derived devices
	const devices = $derived(Array.from(getDevices().values()));

	onMount(() => {
		ws = new ECGWebSocket();
		ws.connect();
	});

	onDestroy(() => {
		ws?.disconnect();
	});
</script>

<div class="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
	<!-- Header -->
	<header class="border-b border-gray-200 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
		<div class="container mx-auto px-6 py-4 max-w-7xl">
			<div class="flex justify-between items-center">
				<div>
					<h1 class="text-2xl font-bold text-gray-900">ECG Streaming</h1>
					<p class="text-sm text-gray-500">Real-time cardiac monitoring</p>
				</div>
				<div class="flex items-center gap-4">
					<a
						href="/sessions"
						class="text-sm text-gray-600 hover:text-gray-900 transition-colors font-medium"
					>
						Sessions
					</a>
					<ConnectionStatus />
				</div>
			</div>
		</div>
	</header>

	<!-- Main Content -->
	<main class="container mx-auto px-6 py-8 max-w-7xl">
		<div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
			<!-- ECG Waveforms (2/3 width) -->
			<div class="lg:col-span-2">
				<ECGWaveform />
			</div>

			<!-- Sidebar (1/3 width) -->
			<div class="space-y-6">
				<StatsPanel />

				<DeviceStatusPanel />

				<div class="space-y-4">
					<div class="flex items-center justify-between">
						<h2 class="text-lg font-semibold text-gray-900">Streaming Devices</h2>
						<span class="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded-full">
							{devices.length}
						</span>
					</div>
					{#if devices.length === 0}
						<div class="bg-white border border-gray-200 rounded-xl shadow-sm p-8 text-center">
							<div class="text-4xl mb-2">📡</div>
							<p class="text-sm font-medium text-gray-900 mb-1">No devices streaming</p>
							<p class="text-xs text-gray-500">Waiting for ECG data...</p>
						</div>
					{:else}
						<div class="space-y-3">
							{#each devices as device (device.device_id)}
								<DeviceCard {device} />
							{/each}
						</div>
					{/if}
				</div>
			</div>
		</div>
	</main>
</div>
