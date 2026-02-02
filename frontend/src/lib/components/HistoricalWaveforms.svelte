<script lang="ts">
	import type { Session } from '$lib/types/api';
	import Button from './buttons/Button.svelte';
	import Card from './Card.svelte';
	import HistoricalAccelerometerWaveform from './HistoricalAccelerometerWaveform.svelte';
	import HistoricalWaveform from './HistoricalWaveform.svelte';
	import 'uplot/dist/uPlot.min.css';

	interface Props {
		session: Session;
		loading?: boolean;
		deviceNicknames?: Map<string, string>;
	}

	let { session, loading = false, deviceNicknames }: Props = $props();

	// Shared state for verified points toggle
	let showVerifiedPoints = $state(false);
</script>


<Card title="Session Waveforms">
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
	{/snippet}

	<div class="space-y-6">
		<!-- ECG Waveform -->
		<div>
			<div class="flex items-center justify-between mb-3">
				<h3 class="text-sm font-semibold text-gray-900">ECG</h3>
			</div>
			{#key showVerifiedPoints}
				<HistoricalWaveform {session} {loading} {showVerifiedPoints} {deviceNicknames} />
			{/key}
		</div>

		<!-- Divider -->
		<div class="border-t border-gray-200"></div>

		<!-- Accelerometer Waveform -->
		<div>
			<div class="flex items-center justify-between mb-3">
				<h3 class="text-sm font-semibold text-gray-900">Accelerometer</h3>
			</div>
			{#key showVerifiedPoints}
				<HistoricalAccelerometerWaveform {session} {loading} {showVerifiedPoints} {deviceNicknames} />
			{/key}
		</div>
	</div>
</Card>
