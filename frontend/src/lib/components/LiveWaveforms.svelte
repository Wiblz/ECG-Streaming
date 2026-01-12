<script lang="ts">
	import Card from './Card.svelte';
	import Waveform from './Waveform.svelte';
	import PauseButton from './PauseButton.svelte';
	import { getSamples as getEcgSamples } from '$lib/state/ecg-data.svelte';
	import { getSamples as getAccSamples } from '$lib/state/acc-data.svelte';
	import { getWsState, getAccWsState, ConnectionState } from '$lib/state/websocket.svelte';

	// Get samples and connection states
	const ecgSamples = $derived(getEcgSamples());
	const accSamples = $derived(getAccSamples());
	const ecgWsState = $derived(getWsState());
	const accWsState = $derived(getAccWsState());

	// Determine streaming status
	const ecgStreaming = $derived(ecgWsState === ConnectionState.CONNECTED && ecgSamples.size > 0);
	const accStreaming = $derived(accWsState === ConnectionState.CONNECTED && accSamples.size > 0);
</script>

<svelte:head>
	<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/uplot@1.6.32/dist/uPlot.min.css" />
</svelte:head>

<Card title="Live Waveforms">
	{#snippet headerActions()}
		<PauseButton />
	{/snippet}

	<div class="space-y-6">
		<!-- ECG Waveform -->
		<div>
			<div class="flex items-center justify-between mb-3">
				<h3 class="text-sm font-semibold text-gray-900">ECG</h3>
				{#if ecgStreaming}
					<div class="flex items-center gap-1.5 text-xs text-gray-500">
						<div class="w-1.5 h-1.5 bg-status-success-fg rounded-full animate-pulse"></div>
						<span>Active</span>
					</div>
				{:else}
					<div class="flex items-center gap-1.5 text-xs text-gray-400">
						<div class="w-1.5 h-1.5 bg-status-neutral-fg rounded-full"></div>
						<span>Idle</span>
					</div>
				{/if}
			</div>
			<Waveform
				samples={ecgSamples}
				wsState={ecgWsState}
				getValue={(s) => s.raw_value}
				yAxisLabel="Amplitude (mV)"
				title="ECG"
				emptyMessage="Waiting for ECG data..."
				standalone={false}
			/>
		</div>

		<!-- Divider -->
		<div class="border-t border-gray-200"></div>

		<!-- Accelerometer Waveform -->
		<div>
			<div class="flex items-center justify-between mb-3">
				<h3 class="text-sm font-semibold text-gray-900">Accelerometer</h3>
				{#if accStreaming}
					<div class="flex items-center gap-1.5 text-xs text-gray-500">
						<div class="w-1.5 h-1.5 bg-status-success-fg rounded-full animate-pulse"></div>
						<span>Active</span>
					</div>
				{:else}
					<div class="flex items-center gap-1.5 text-xs text-gray-400">
						<div class="w-1.5 h-1.5 bg-status-neutral-fg rounded-full"></div>
						<span>Idle</span>
					</div>
				{/if}
			</div>
			<Waveform
				samples={accSamples}
				wsState={accWsState}
				getValue={(s) => s.magnitude}
				yAxisLabel="Magnitude (g)"
				title="Accelerometer"
				emptyMessage="Waiting for accelerometer data..."
				standalone={false}
			/>
		</div>
	</div>
</Card>
