<script lang="ts">
	import { getSamples } from '$lib/state/ecg-data.svelte';
	import { getWsState } from '$lib/state/websocket.svelte';
	import Waveform from './Waveform.svelte';

	const samples = $derived(getSamples());
	const wsState = $derived(getWsState());
</script>

<Waveform
	{samples}
	{wsState}
	getValue={(s) => s.raw_value}
	yAxisLabel="Raw Value"
	title="Live ECG Waveforms"
	emptyMessage="Waiting for ECG data..."
/>
