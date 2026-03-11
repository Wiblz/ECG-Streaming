<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { AccelerometerWebSocket } from '$lib/api/accelerometerWebsocket';
	import { ECGWebSocket } from '$lib/api/websocket';
	import { api } from '$lib/api/client';
	import Card from '$lib/components/Card.svelte';
	import ConnectionStatus from '$lib/components/ConnectionStatus.svelte';
	import DeviceCard from '$lib/components/DeviceCard.svelte';
	import DeviceStatusPanel from '$lib/components/DeviceStatusPanel.svelte';
	import Header from '$lib/components/Header.svelte';
	import LiveWaveforms from '$lib/components/LiveWaveforms.svelte';
	import SessionControl from '$lib/components/SessionControl.svelte';
	import StatsPanel from '$lib/components/StatsPanel.svelte';
	import LiveActivityMonitor from '$lib/components/LiveActivityMonitor.svelte';
	import { getDevices, setDevices } from '$lib/state/devices.svelte';
	import { samples as ecgSamples } from '$lib/state/ecg-data.svelte';
	import { samples as accSamples } from '$lib/state/acc-data.svelte';

	let ecgWs: ECGWebSocket;
	let accWs: AccelerometerWebSocket;

	// Reactive derived devices
	const devices = $derived(Array.from(getDevices().values()));

	// Get first device samples for activity monitors
	// Create stable getters that LiveActivityMonitor can poll
	function getFirstEcgSamples() {
		const deviceIds = Array.from(ecgSamples.keys());
		if (deviceIds.length === 0) return [];
		return ecgSamples.get(deviceIds[0]) ?? [];
	}

	function getFirstAccSamples() {
		const deviceIds = Array.from(accSamples.keys());
		if (deviceIds.length === 0) return [];
		return accSamples.get(deviceIds[0]) ?? [];
	}

	onMount(async () => {
		// Load device info with nicknames
		try {
			const response = await api.getAllDevices();
			setDevices(response.devices);
		} catch (e) {
			console.error('Failed to load device info:', e);
		}

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
				<SessionControl />

				<Card title="Activity Monitor">
					<div class="space-y-4">
						<LiveActivityMonitor
							getSamples={getFirstEcgSamples}
							getValue={(s) => s.raw_value}
							label="ECG"
							height={50}
							color="#ef4444"
							windowDuration={30}
						/>
						<LiveActivityMonitor
							getSamples={getFirstAccSamples}
							getValue={(s) => s.magnitude}
							label="Accelerometer"
							height={50}
							color="#3b82f6"
							windowDuration={30}
						/>
					</div>
				</Card>

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
