<script lang="ts" generics="T extends { device_id: string; global_time: number }">
	import { onDestroy, onMount } from 'svelte';
	import type uPlot from 'uplot';
	import type { AlignedData } from 'uplot';
	import { browser } from '$app/environment';
	import { getSessionStartTime, setSessionStartTime } from '$lib/state/session-time.svelte';
	import type { ConnectionStateType } from '$lib/state/websocket.svelte';
	import Card from './Card.svelte';

	interface Props {
		samples: Map<string, T[]>;
		getValue: (sample: T) => number;
		yAxisLabel: string;
		title: string;
		emptyMessage?: string;
		wsState: ConnectionStateType;
		/**
		 * Whether to render the Card wrapper
		 * @default true
		 */
		standalone?: boolean;
	}

	let {
		samples,
		getValue,
		yAxisLabel,
		title,
		emptyMessage = 'Waiting for data...',
		wsState,
		standalone = true
	}: Props = $props();

	let plotContainer: HTMLDivElement;
	let chart: uPlot | null = null;
	let uPlotLib = $state<typeof uPlot | null>(null);
	let createDeviceSeries: ((deviceIds: string[]) => uPlot.Series[]) | null = null;
	let createAxes: ((yLabel: string) => uPlot.Axis[]) | null = null;

	import { ConnectionState } from '$lib/state/websocket.svelte';

	const isStreaming = $derived(wsState === ConnectionState.CONNECTED && samples.size > 0);

	// Use shared session start time for synchronization across all waveforms
	const sessionStartTime = $derived(getSessionStartTime());

	// Prepare data for uPlot from live samples
	function prepareChartData(sampleMap: Map<string, T[]>): {
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
				setSessionStartTime(deviceSamples[0].global_time);
			}

			// Use absolute time (seconds from session start)
			const currentStartTime = sessionStartTime ?? deviceSamples[0].global_time;
			const timestamps = deviceSamples.map((s) => s.global_time - currentStartTime);
			const values = deviceSamples.map((s) => getValue(s));

			// Log buffer state
			const timeRange =
				timestamps.length > 0
					? `${timestamps[0].toFixed(2)}s - ${timestamps[timestamps.length - 1].toFixed(2)}s`
					: 'empty';
			// console.log(`[${title}] Buffer: ${deviceSamples.length} samples, time range: ${timeRange}`);

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
			setSessionStartTime(baseSamples[0].global_time);
		}

		// Use absolute time (seconds from session start)
		const currentStartTime = sessionStartTime ?? baseSamples[0].global_time;
		const timestamps = baseSamples.map((s) => s.global_time - currentStartTime);

		// Create value arrays for each device
		const seriesData = devices.map((deviceId) => {
			const deviceSamples = sampleMap.get(deviceId)!;
			return deviceSamples.map((s) => getValue(s));
		});

		return {
			data: [timestamps, ...seriesData],
			devices
		};
	}

	// Create the chart
	function createChart() {
		if (!plotContainer || !uPlotLib || !createDeviceSeries || !createAxes) return;

		const { data, devices } = prepareChartData(samples);

		if (devices.length === 0) {
			// No data yet, skip chart creation
			return;
		}

		const opts: uPlot.Options = {
			width: plotContainer.clientWidth,
			height: 400,
			series: createDeviceSeries(devices),
			axes: createAxes(yAxisLabel),
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
			// console.log(`[${title}] Waiting for plotContainer or uPlotLib`, {
			// 	plotContainer: !!plotContainer,
			// 	uPlotLib: !!uPlotLib
			// });
			return;
		}

		const { data, devices } = prepareChartData(samples);

		// console.log(`[${title}] Data prepared`, {
		// 	deviceCount: devices.length,
		// 	sampleCount: data[0]?.length || 0
		// });

		if (devices.length === 0) {
			// No data yet
			return;
		}

		if (!chart) {
			// Create chart on first data
			// console.log(`[${title}] Creating chart for first time`);
			createChart();
		} else {
			// Update existing chart
			// console.log(`[${title}] Updating chart data`);
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

		// console.log(`[${title}] Loading uPlot...`);

		// Dynamically import uPlot and utilities only in browser
		const [uPlotModule, utilsModule] = await Promise.all([
			import('uplot'),
			import('$lib/utils/uplot')
		]);

		uPlotLib = uPlotModule.default;
		createDeviceSeries = utilsModule.createDeviceSeries;
		createAxes = utilsModule.createAxes;

		// console.log(`[${title}] uPlot loaded successfully`);

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

{#if standalone}
	<Card {title}>
		{#snippet headerActions()}
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
		{/snippet}

		<div bind:this={plotContainer} class="border border-gray-200 rounded-lg">
			{#if samples.size === 0}
				<div class="bg-gray-50 p-12 text-center">
					<p class="text-gray-500">{emptyMessage}</p>
				</div>
			{/if}
		</div>
	</Card>
{:else}
	<div bind:this={plotContainer} class="border border-gray-200 rounded-lg">
		{#if samples.size === 0}
			<div class="bg-gray-50 p-12 text-center">
				<p class="text-gray-500">{emptyMessage}</p>
			</div>
		{/if}
	</div>
{/if}
