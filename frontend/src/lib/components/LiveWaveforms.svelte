<script lang="ts">
	import { getSamples as getAccSamples } from '$lib/state/acc-data.svelte';
	import { getSamples as getEcgSamples } from '$lib/state/ecg-data.svelte';
	import { getDevices } from '$lib/state/devices.svelte';
	import { ConnectionState, getAccWsState, getWsState } from '$lib/state/websocket.svelte';
	import { createDeviceNicknameMap } from '$lib/utils/device-names';
	import Button from './buttons/Button.svelte';
	import Card from './Card.svelte';
	import PauseButton from './PauseButton.svelte';
	import LiveWaveform from './LiveWaveform.svelte';
	import 'uplot/dist/uPlot.min.css';

	// Get samples and connection states
	const ecgSamples = $derived(getEcgSamples());
	const accSamples = $derived(getAccSamples());
	const ecgWsState = $derived(getWsState());
	const accWsState = $derived(getAccWsState());

	// Get devices for nicknames
	const devices = $derived(getDevices());
	const deviceNicknames = $derived(createDeviceNicknameMap(Array.from(devices.values())));

	// Determine streaming status
	const ecgStreaming = $derived(ecgWsState === ConnectionState.CONNECTED && ecgSamples.size > 0);
	const accStreaming = $derived(accWsState === ConnectionState.CONNECTED && accSamples.size > 0);

	// Shared state for verified points toggle
	let showVerifiedPoints = $state(false);
</script>


<Card title="Live Waveforms">
	{#snippet headerActions()}
		<Button
			variant={showVerifiedPoints ? 'success' : 'ghost'}
			size="sm"
			onclick={() => {
				showVerifiedPoints = !showVerifiedPoints;
			}}
			title="Toggle verified sample points (samples with direct Polar timestamps)"
		>
			Verified Points
		</Button>
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
			{#key `${showVerifiedPoints}-${deviceNicknames.size}`}
				<LiveWaveform
					samples={ecgSamples}
					wsState={ecgWsState}
					{deviceNicknames}
					getValue={(s) => s.raw_value}
					yAxisLabel="Amplitude (mV)"
					title="ECG"
					emptyMessage="Waiting for ECG data..."
					standalone={false}
					{showVerifiedPoints}
				/>
			{/key}
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
			{#key `${showVerifiedPoints}-${deviceNicknames.size}`}
				<LiveWaveform
					samples={accSamples}
					wsState={accWsState}
					{deviceNicknames}
					getValue={(s) => s.magnitude}
					yAxisLabel="Magnitude (g)"
					title="Accelerometer"
					emptyMessage="Waiting for accelerometer data..."
					standalone={false}
					{showVerifiedPoints}
				/>
			{/key}
		</div>
	</div>
</Card>
