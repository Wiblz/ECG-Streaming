<script lang="ts">
	import Waveform from './Waveform.svelte';
	import { getSamples } from '$lib/state/acc-data.svelte';
	import { getAccWsState } from '$lib/state/websocket.svelte';

	const samples = $derived(getSamples());
	const wsState = $derived(getAccWsState());
</script>

<Waveform
	{samples}
	{wsState}
	getValue={(s) => s.magnitude}
	yAxisLabel="Magnitude (g)"
	title="Live Accelerometer"
	emptyMessage="Waiting for accelerometer data..."
/>
