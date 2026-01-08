<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { browser } from '$app/environment';
	import type uPlot from 'uplot';
	import type { AlignedData } from 'uplot';
	import { getSamples } from '$lib/state/ecg-data.svelte';
	import { getWsState, ConnectionState } from '$lib/state/websocket.svelte';
	import type { BufferedECGSample } from '$lib/types/api';

	let plotContainer: HTMLDivElement;
	let chart: uPlot | null = null;
	let uPlotLib = $state<typeof uPlot | null>(null);
	let createDeviceSeries: ((deviceIds: string[]) => uPlot.Series[]) | null = null;
	let createAxes: (() => uPlot.Axis[]) | null = null;

	// Get reactive samples from WebSocket
	const samples = $derived(getSamples());
	const wsState = $derived(getWsState());
	const isStreaming = $derived(wsState === ConnectionState.CONNECTED && samples.size > 0);

	// Track the start time of the session (first sample received)
	let sessionStartTime = $state<number | null>(null);

	// Prepare data for uPlot from live samples
	function prepareChartData(sampleMap: Map<string, BufferedECGSample[]>): {
		data: AlignedData;
		devices: string[];
	} {
		const devices = Array.from(sampleMap.keys());

		if (devices.length === 0 || sampleMap.size === 0) {
			return { data: [[], []], devices: [] };
		}

		// Single device case
		if (devices.length === 1) {
			const deviceSamples = sampleMap.get(devices[0])!;
			if (deviceSamples.length === 0) {
				return { data: [[], []], devices };
			}

			// Set session start time from first sample if not set
			if (sessionStartTime === null && deviceSamples.length > 0) {
				sessionStartTime = deviceSamples[0].global_time;
			}

			// Use absolute time (seconds from session start)
			const timestamps = deviceSamples.map((s) => s.global_time - sessionStartTime!);
			const values = deviceSamples.map((s) => s.raw_value);

			return {
				data: [timestamps, values],
				devices
			};
		}

		// Multiple devices - align by timestamp
		// Find the device with the most samples to use as time base
		let maxDevice = devices[0];
		let maxLength = 0;
		for (const deviceId of devices) {
			const len = sampleMap.get(deviceId)!.length;
			if (len > maxLength) {
				maxLength = len;
				maxDevice = deviceId;
			}
		}

		const baseSamples = sampleMap.get(maxDevice)!;
		if (baseSamples.length === 0) {
			return { data: [[], []], devices: [] };
		}

		// Set session start time from first sample if not set
		if (sessionStartTime === null && baseSamples.length > 0) {
			sessionStartTime = baseSamples[0].global_time;
		}

		// Use absolute time (seconds from session start)
		const timestamps = baseSamples.map((s) => s.global_time - sessionStartTime!);

		// Create value arrays for each device
		const seriesData = devices.map((deviceId) => {
			const deviceSamples = sampleMap.get(deviceId)!;
			return deviceSamples.map((s) => s.raw_value);
		});

		return {
			data: [timestamps, ...seriesData],
			devices
		};
	}

	// Create the chart
	function createChart() {
		if (!plotContainer || !uPlotLib) return;

		const { data, devices } = prepareChartData(samples);

		if (devices.length === 0) {
			// No data yet, skip chart creation
			return;
		}

		const opts: uPlot.Options = {
			width: plotContainer.clientWidth,
			height: 400,
			series: createDeviceSeries(devices),
			axes: createAxes(),
			scales: {
				x: {
					time: false
				}
			},
			legend: {
				show: true
			}
		};

		if (chart) {
			chart.destroy();
		}

		chart = new uPlotLib(opts, data, plotContainer);
	}

	// Update chart when samples change
	$effect(() => {
		if (!plotContainer || !uPlotLib) {
			console.log('[ECGWaveform] Waiting for plotContainer or uPlotLib', {
				plotContainer: !!plotContainer,
				uPlotLib: !!uPlotLib
			});
			return;
		}

		const { data, devices } = prepareChartData(samples);

		console.log('[ECGWaveform] Data prepared', {
			deviceCount: devices.length,
			sampleCount: data[0]?.length || 0
		});

		if (devices.length === 0) {
			// No data yet
			return;
		}

		if (!chart) {
			// Create chart on first data
			console.log('[ECGWaveform] Creating chart for first time');
			createChart();
		} else {
			// Update existing chart
			console.log('[ECGWaveform] Updating chart data');
			chart.setData(data);
		}
	});

	// Handle window resize
	function handleResize() {
		if (chart && plotContainer) {
			chart.setSize({
				width: plotContainer.clientWidth,
				height: 400
			});
		}
	}

	onMount(async () => {
		if (!browser) return;

		console.log('[ECGWaveform] Loading uPlot...');

		// Dynamically import uPlot and utilities only in browser
		const [uPlotModule, utilsModule] = await Promise.all([
			import('uplot'),
			import('$lib/utils/uplot')
		]);

		uPlotLib = uPlotModule.default;
		createDeviceSeries = utilsModule.createDeviceSeries;
		createAxes = utilsModule.createAxes;

		console.log('[ECGWaveform] uPlot loaded successfully');

		window.addEventListener('resize', handleResize);
	});

	onDestroy(() => {
		if (browser) {
			window.removeEventListener('resize', handleResize);
		}
		if (chart) {
			chart.destroy();
		}
	});
</script>

<svelte:head>
	<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/uplot@1.6.32/dist/uPlot.min.css" />
</svelte:head>

<div class="bg-white border border-gray-200 rounded-xl shadow-lg p-6">
	<div class="flex items-center justify-between mb-4">
		<h2 class="text-lg font-semibold text-gray-900">Live Waveforms</h2>
		{#if isStreaming}
			<div class="flex items-center gap-2 text-xs text-gray-500">
				<div class="w-2 h-2 bg-status-success-fg rounded-full animate-pulse"></div>
				<span>Streaming</span>
			</div>
		{:else}
			<div class="flex items-center gap-2 text-xs text-gray-500">
				<div class="w-2 h-2 bg-status-neutral-fg rounded-full"></div>
				<span>No data</span>
			</div>
		{/if}
	</div>

	<div bind:this={plotContainer} class="border border-gray-200 rounded-lg">
		{#if samples.size === 0}
			<div class="bg-gray-50 p-12 text-center">
				<p class="text-gray-500">Waiting for ECG data...</p>
			</div>
		{/if}
	</div>
</div>
