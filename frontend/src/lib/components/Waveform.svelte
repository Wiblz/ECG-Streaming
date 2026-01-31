<script lang="ts" generics="T extends { device_id: string; global_time: number; id: string; wall_clock_us: number; receiver_clock_us: number; polar_clock_us: number; time_verified: boolean }">
	import { onDestroy, onMount } from 'svelte';
	import type uPlot from 'uplot';
	import type { AlignedData } from 'uplot';
	import { browser } from '$app/environment';
	import { isPaused } from '$lib/state/pause.svelte';
	import {
		getCurrentPlaybackTime, 
		getSessionStartTime,
		setSessionStartTime
	} from '$lib/state/session-time.svelte';
	import type { ConnectionStateType } from '$lib/state/websocket.svelte';
	import Button from './buttons/Button.svelte';
	import Card from './Card.svelte';
	import 'uplot/dist/uPlot.min.css';

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
		/**
		 * Whether to show verified sample points
		 * @default false
		 */
		showVerifiedPoints?: boolean;
	}

	let {
		samples,
		getValue,
		yAxisLabel,
		title,
		emptyMessage = 'Waiting for data...',
		wsState,
		standalone = true,
		showVerifiedPoints = false
	}: Props = $props();

	let plotContainer: HTMLDivElement;
	let chart = $state<uPlot | null>(null);
	let uPlotLib = $state<typeof uPlot | null>(null);
	let createDeviceSeries: ((deviceIds: string[], getVerifiedIndices?: () => number[]) => uPlot.Series[]) | null = null;
	let createAxes: ((yLabel: string) => uPlot.Axis[]) | null = null;
	let tooltipsPlugin: ReturnType<typeof import('$lib/utils/uplot-tooltips').tooltipsPlugin> | null =
		null;
	let updateIntervalId: number | null = null;

	// Sample lookup for efficient tooltip access - maps chart data index to original sample
	let sampleLookup: T[] = [];
	// Pre-computed indices of verified samples for efficient filtering
	let verifiedIndices: number[] = [];

	import { ConnectionState } from '$lib/state/websocket.svelte';

	const isStreaming = $derived(
		wsState === ConnectionState.CONNECTED && samples.size > 0 && !isPaused()
	);

	// Time window configuration
	const WINDOW_DURATION = 7.5; // seconds to display
	const UPDATE_INTERVAL_MS = 20; // update every 20ms (50Hz)

	// X-axis range controlled by function (prevents setData from resetting scale)
	let xAxisRange: [number, number] = [0, WINDOW_DURATION];

	// Use shared session start time for synchronization across all waveforms
	const sessionStartTime = $derived(getSessionStartTime());

	// Get current time window based on wall-clock progression (shared across all waveforms)
	function getCurrentTimeWindow(): { minTime: number; maxTime: number } | null {
		const currentTime = getCurrentPlaybackTime();

		if (currentTime === null) {
			return null;
		}

		// Always show a fixed WINDOW_DURATION window, even if it starts in the past
		const window = {
			minTime: currentTime - WINDOW_DURATION,
			maxTime: currentTime
		};
		return window;
	}

	// Prepare data for uPlot from live samples, filtered by time window
	function prepareChartData(
		sampleMap: Map<string, T[]>,
		timeWindow?: { minTime: number; maxTime: number } | null
	): {
		data: AlignedData;
		devices: string[];
		samples: T[];
	} {
		const devices = Array.from(sampleMap.keys());

		if (devices.length === 0 || sampleMap.size === 0) {
			return { data: [[], []], devices: [], samples: [] };
		}

		// Single device case
		if (devices.length === 1) {
			const deviceSamples = sampleMap.get(devices[0])!;
			if (deviceSamples.length === 0) {
				return { data: [[], []], devices, samples: [] };
			}

			// Set session start time from first sample if not set
			if (sessionStartTime === null && deviceSamples.length > 0) {
				setSessionStartTime(deviceSamples[0].global_time);
			}

			// Use absolute time (seconds from session start)
			const currentStartTime = sessionStartTime ?? deviceSamples[0].global_time;

			// Filter samples by time window if provided
			let filteredSamples = deviceSamples;
			if (timeWindow) {
				filteredSamples = deviceSamples.filter((s) => {
					const relTime = s.global_time - currentStartTime;
					return relTime >= timeWindow.minTime && relTime <= timeWindow.maxTime;
				});
			}

			const timestamps = filteredSamples.map((s) => s.global_time - currentStartTime);
			const values = filteredSamples.map((s) => getValue(s));

			return {
				data: [timestamps, values],
				devices,
				samples: filteredSamples
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
			return { data: [[], []], devices: [], samples: [] };
		}

		// Set session start time from first sample if not set
		if (sessionStartTime === null && baseSamples.length > 0) {
			setSessionStartTime(baseSamples[0].global_time);
		}

		// Use absolute time (seconds from session start)
		const currentStartTime = sessionStartTime ?? baseSamples[0].global_time;

		// Filter base samples by time window if provided
		let filteredBaseSamples = baseSamples;
		if (timeWindow) {
			filteredBaseSamples = baseSamples.filter((s) => {
				const relTime = s.global_time - currentStartTime;
				return relTime >= timeWindow.minTime && relTime <= timeWindow.maxTime;
			});
		}

		const timestamps = filteredBaseSamples.map((s) => s.global_time - currentStartTime);

		// Create value arrays for each device, ALIGNED to the base timestamps
		const seriesData = devices.map((deviceId) => {
			const deviceSamples = sampleMap.get(deviceId)!;
			let filtered = deviceSamples;
			if (timeWindow) {
				filtered = deviceSamples.filter((s) => {
					const relTime = s.global_time - currentStartTime;
					return relTime >= timeWindow.minTime && relTime <= timeWindow.maxTime;
				});
			}

			// Align device samples to base timestamps using nearest neighbor
			return timestamps.map((baseTimestamp) => {
				const baseAbsTime = baseTimestamp + currentStartTime;

				// Find the closest sample from this device
				let closestSample = filtered[0];
				let minDiff = Math.abs(filtered[0]?.global_time - baseAbsTime);

				for (let i = 1; i < filtered.length; i++) {
					const diff = Math.abs(filtered[i].global_time - baseAbsTime);
					if (diff < minDiff) {
						minDiff = diff;
						closestSample = filtered[i];
					} else {
						// Samples are time-ordered, so we can stop searching
						break;
					}
				}

				// Use null if no sample within reasonable tolerance (0.1s)
				if (minDiff > 0.1) {
					return null;
				}

				return getValue(closestSample);
			});
		});

		return {
			data: [timestamps, ...seriesData],
			devices,
			samples: filteredBaseSamples
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
			series: createDeviceSeries(devices, showVerifiedPoints ? () => verifiedIndices : undefined),
			axes: createAxes(yAxisLabel),
			scales: {
				x: {
					time: false,
					auto: false,
					range: () => xAxisRange
				}
			},
			plugins: tooltipsPlugin ? [tooltipsPlugin] : [],
			legend: {
				show: true
			}
		};

		if (chart) {
			chart.destroy();
		}

		chart = new uPlotLib(opts, data, plotContainer);
	}

	// Debug logging counter
	let updateCounter = 0;

	// Update function for time-based chart updates
	function updateChart() {
		if (!chart || !isStreaming) {
			return;
		}

		const timeWindow = getCurrentTimeWindow();
		if (!timeWindow) {
			return;
		}

		const { data, samples: chartSamples } = prepareChartData(samples, timeWindow);
		sampleLookup = chartSamples;
		// Pre-compute verified indices for performance
		verifiedIndices = chartSamples.reduce((acc, sample, i) => {
			if (sample.time_verified) acc.push(i);
			return acc;
		}, [] as number[]);

		// Update the range array (chart will use function to read it)
		xAxisRange[0] = timeWindow.minTime;
		xAxisRange[1] = timeWindow.maxTime;

		// Periodic logging every 10 updates (~1 second at 100ms interval)
		updateCounter++;
		if (updateCounter % 10 === 0) {
			const wallTime = Date.now() / 1000;
			const devices = Array.from(samples.keys());
			const bufferInfo = devices.map((deviceId) => {
				const deviceSamples = samples.get(deviceId)!;
				const lastSample = deviceSamples[deviceSamples.length - 1];
				if (!lastSample) return `${deviceId}: none`;
				const delta = lastSample.global_time - wallTime;
				return `${deviceId}: Δ${delta.toFixed(2)}s`;
			}).join(', ');

			console.log(
				`[${title}] window.maxTime=${timeWindow.maxTime.toFixed(2)}, wall=${wallTime.toFixed(2)}, buffer: ${bufferInfo}`
			);
		}

		// setData will now use the updated range via the function
		chart.setData(data);
	}


	// Start/stop update interval based on streaming state
	$effect(() => {
		if (isStreaming && chart) {
			// Start update interval
			if (updateIntervalId === null) {
				console.log(`[${title}] Starting update interval`);
				updateIntervalId = window.setInterval(updateChart, UPDATE_INTERVAL_MS);
			}
		} else {
			// Stop update interval
			if (updateIntervalId !== null) {
				console.log(`[${title}] Stopping update interval`);
				clearInterval(updateIntervalId);
				updateIntervalId = null;
			}
		}

		// Cleanup on effect disposal
		return () => {
			if (updateIntervalId !== null) {
				clearInterval(updateIntervalId);
				updateIntervalId = null;
			}
		};
	});

	// Create chart when samples first arrive
	$effect(() => {
		if (!plotContainer || !uPlotLib) {
			return;
		}

		const { data, devices, samples: chartSamples } = prepareChartData(samples);
		sampleLookup = chartSamples;
		// Pre-compute verified indices for performance
		verifiedIndices = chartSamples.reduce((acc, sample, i) => {
			if (sample.time_verified) acc.push(i);
			return acc;
		}, [] as number[]);

		if (devices.length === 0) {
			// No data yet
			return;
		}

		if (!chart) {
			// Create chart on first data
			createChart();
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
		const [uPlotModule, utilsModule, tooltipsModule] = await Promise.all([
			import('uplot'),
			import('$lib/utils/uplot'),
			import('$lib/utils/uplot-tooltips')
		]);

		uPlotLib = uPlotModule.default;
		createDeviceSeries = utilsModule.createDeviceSeries;
		createAxes = utilsModule.createAxes;
		tooltipsPlugin = tooltipsModule.tooltipsPlugin({
			showSeriesPoints: true,
			showCursorPosition: false,
			formatValue: (xVal, yVal, seriesIdx, dataIdx) => {
				// Use direct lookup - O(1) instead of O(n)
				const sample = sampleLookup[dataIdx];
				if (sample) {
					const verified = sample.time_verified ? ' ✓' : '';
					return `
						<table style="border-collapse: collapse;">
							<tr><td style="padding: 1px 4px 1px 0;">ID:</td><td style="padding: 1px 0;">${sample.id}</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Value:</td><td style="padding: 1px 0;">${yVal.toFixed(0)}</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Time:</td><td style="padding: 1px 0;">${xVal.toFixed(2)}s</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Polar:</td><td style="padding: 1px 0;">${(sample.polar_clock_us / 1_000_000).toFixed(3)}s${verified}</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Receiver:</td><td style="padding: 1px 0;">${(sample.receiver_clock_us / 1_000_000).toFixed(3)}s</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Wall:</td><td style="padding: 1px 0;">${(sample.wall_clock_us / 1_000_000).toFixed(3)}s</td></tr>
						</table>
					`;
				}
				return `
					<table style="border-collapse: collapse;">
						<tr><td style="padding: 1px 4px 1px 0;">Time:</td><td style="padding: 1px 0;">${xVal.toFixed(2)}s</td></tr>
						<tr><td style="padding: 1px 4px 1px 0;">Value:</td><td style="padding: 1px 0;">${yVal.toFixed(0)}</td></tr>
					</table>
				`;
			}
		});

		// console.log(`[${title}] uPlot loaded successfully`);

		window.addEventListener('resize', handleResize);
	});

	onDestroy(() => {
		if (browser) {
			window.removeEventListener('resize', handleResize);
		}
		if (updateIntervalId !== null) {
			clearInterval(updateIntervalId);
		}
		if (chart) {
			chart.destroy();
		}
	});
</script>


{#if standalone}
	<Card {title}>
		{#snippet headerActions()}
			<Button
				variant={showVerifiedPoints ? 'success' : 'ghost'}
				size="sm"
				onclick={() => {
					showVerifiedPoints = !showVerifiedPoints;
					createChart();
				}}
				title="Toggle verified sample points (samples with direct Polar timestamps)"
			>
				Verified Points
			</Button>
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
