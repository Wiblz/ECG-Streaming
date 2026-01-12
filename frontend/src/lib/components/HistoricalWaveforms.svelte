<script lang="ts">
	import type { Session } from '$lib/types/api';
	import Card from './Card.svelte';
	import HistoricalWaveform from './HistoricalWaveform.svelte';
	import HistoricalAccelerometerWaveform from './HistoricalAccelerometerWaveform.svelte';

	interface Props {
		session: Session;
		loading?: boolean;
	}

	let { session, loading = false }: Props = $props();
</script>

<svelte:head>
	<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/uplot@1.6.32/dist/uPlot.min.css" />
</svelte:head>

<Card title="Session Waveforms">
	<div class="space-y-6">
		<!-- ECG Waveform -->
		<div>
			<div class="flex items-center justify-between mb-3">
				<h3 class="text-sm font-semibold text-gray-900">ECG</h3>
			</div>
			<HistoricalWaveform {session} {loading} />
		</div>

		<!-- Divider -->
		<div class="border-t border-gray-200"></div>

		<!-- Accelerometer Waveform -->
		<div>
			<div class="flex items-center justify-between mb-3">
				<h3 class="text-sm font-semibold text-gray-900">Accelerometer</h3>
			</div>
			<HistoricalAccelerometerWaveform {session} {loading} />
		</div>
	</div>
</Card>
