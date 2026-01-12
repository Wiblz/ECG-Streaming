<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { ECGWebSocket } from '$lib/api/websocket';
	import { AccelerometerWebSocket } from '$lib/api/accelerometerWebsocket';
	import { getDevices } from '$lib/state/devices.svelte';
	import Header from '$lib/components/Header.svelte';
	import Card from '$lib/components/Card.svelte';
	import LiveWaveforms from '$lib/components/LiveWaveforms.svelte';
	import DeviceCard from '$lib/components/DeviceCard.svelte';
	import StatsPanel from '$lib/components/StatsPanel.svelte';
	import ConnectionStatus from '$lib/components/ConnectionStatus.svelte';
	import DeviceStatusPanel from '$lib/components/DeviceStatusPanel.svelte';

	let ecgWs: ECGWebSocket;
	let accWs: AccelerometerWebSocket;

	// Reactive derived devices
	const devices = $derived(Array.from(getDevices().values()));

	onMount(() => {
		ecgWs = new ECGWebSocket();
		ecgWs.connect();

		accWs = new AccelerometerWebSocket();
		accWs.connect();
	});

	onDestroy(() => {
		ecgWs?.disconnect();
		accWs?.disconnect();
	});
</script>

<svelte:head>
	<title>Live Dashboard - ECG Streaming</title>
</svelte:head>

<div class="min-h-screen bg-linear-to-br from-gray-50 to-gray-100">
	<Header>
		<ConnectionStatus />
	</Header>

	<main class="container mx-auto px-6 py-8 max-w-7xl">
		<div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
			<!-- Waveforms (2/3 width) -->
			<div class="lg:col-span-2">
				<LiveWaveforms />
			</div>

			<!-- Sidebar (1/3 width) -->
			<div class="space-y-6">
				<StatsPanel />

				<DeviceStatusPanel />

				<Card title="Streaming Devices" badge={devices.length}>
					{#if devices.length === 0}
						<div class="text-center py-8">
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
				</Card>
			</div>
		</div>
	</main>
</div>
