<script lang="ts" generics="T extends PlottableSample">
	import { onDestroy, onMount } from 'svelte';
	import type { PlottableSample } from '$lib/types/api';
	import ActivityMonitor from './ActivityMonitor.svelte';
	import { calculateTimeWindow } from '$lib/waveforms/time-window';
	import { getCurrentPlaybackTime, getSessionStartTime } from '$lib/state/session-time.svelte';
	import { filterSingleDeviceSamples } from '$lib/waveforms/chart-data-transformer';

	interface Props {
		/** Function that returns sample array for single device */
		getSamples: () => T[];
		/** Function to extract value from sample */
		getValue: (sample: T) => number;
		/** Label for the monitor */
		label: string;
		/** Monitor height in pixels */
		height?: number;
		/** Line color */
		color?: string;
		/** Time window duration in seconds */
		windowDuration?: number;
		/** Width in pixels (determines resolution) */
		width?: number;
		/** Pixels per time bucket (lower = more detail) */
		pixelsPerBucket?: number;
	}

	let {
		getSamples,
		getValue,
		label,
		height = 60,
		color = '#10b981',
		windowDuration = 30,
		width = 200,
		pixelsPerBucket = 3
	}: Props = $props();

	// State for rendered samples with timestamps (updated every second)
	let displaySamples = $state<Array<{ timestamp: number; value: number }>>([]);
	let samplingRate = $state<number | null>(null);
	let updateIntervalId: number | null = null;

	// Update display samples (called every second)
	function updateDisplayValues() {
		// Call the getter to get current samples
		const samples = getSamples();

		if (!samples || samples.length === 0) {
			displaySamples = [];
			samplingRate = null;
			return;
		}

		// Get current time window
		const currentTime = getCurrentPlaybackTime();
		const timeWindow = calculateTimeWindow(currentTime, windowDuration);

		if (!timeWindow) {
			displaySamples = [];
			samplingRate = null;
			return;
		}

		// Get session start time from shared session state
		const sessionStartTime = getSessionStartTime();
		if (sessionStartTime === null) {
			displaySamples = [];
			samplingRate = null;
			return;
		}

		// Use shared utility for filtering and decimation
		const result = filterSingleDeviceSamples(samples, sessionStartTime, timeWindow, {
			maxSamples: 500,
			maxSamplesToProcess: 5000
		});

		samplingRate = result.samplingRate;

		// Extract timestamp and value for rendering
		displaySamples = result.samples.map((s) => ({
			timestamp: s.global_time - sessionStartTime,
			value: getValue(s)
		}));
	}

	// Start update interval when component mounts
	onMount(() => {
		// Initial update
		updateDisplayValues();

		// Update every 1 second
		updateIntervalId = window.setInterval(updateDisplayValues, 1000);
	});

	onDestroy(() => {
		if (updateIntervalId !== null) {
			clearInterval(updateIntervalId);
		}
	});
</script>

<ActivityMonitor
	samples={displaySamples}
	{label}
	{height}
	{color}
	{width}
	{pixelsPerBucket}
	{samplingRate}
/>
