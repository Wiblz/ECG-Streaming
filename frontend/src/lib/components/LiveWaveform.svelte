<script lang="ts" generics="T extends PlottableSample">
	import { onDestroy, onMount } from 'svelte';
	import type uPlot from 'uplot';
	import type { AlignedData } from 'uplot';
	import { browser } from '$app/environment';
	import type { PlottableSample } from '$lib/types/api';
	import { isPaused } from '$lib/state/pause.svelte';
	import { alignSamplesToTimestamps } from '$lib/utils/samples';
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
		/**
		 * Map of device IDs to nicknames for display
		 */
		deviceNicknames?: Map<string, string>;
		maxGapSeconds?: number;
	}

	let {
		samples,
		getValue,
		yAxisLabel,
		title,
		emptyMessage = 'Waiting for data...',
		wsState,
		standalone = true,
		showVerifiedPoints = false,
		deviceNicknames,
		maxGapSeconds = 0.1
	}: Props = $props();

	let plotContainer: HTMLDivElement;
	let chart = $state<uPlot | null>(null);
	let uPlotLib = $state<typeof uPlot | null>(null);
	let createDeviceSeries: ((deviceIds: string[], getVerifiedIndices?: (deviceId: string) => number[], deviceNicknames?: Map<string, string>, spanGaps?: boolean) => uPlot.Series[]) | null = null;
	let createAxes: ((yLabel: string) => uPlot.Axis[]) | null = null;
	let tooltipsPlugin: ReturnType<typeof import('$lib/utils/uplot-tooltips').tooltipsPlugin> | null =
		null;
	let animationFrameId: number | null = null;
	let lastUpdateTime = 0;

	let deviceOrder: string[] = $state([]);
	let sampleByDeviceAndTime = new Map<string, Map<number, T>>();
	let verifiedIndicesByDevice = new Map<string, number[]>();

	// Cache for aligned data to avoid re-aligning on every frame
	let alignmentCache = $state<{
		deviceOrder: string[];
		deviceSampleCounts: Map<string, number>;
		timestamps: number[];
		seriesData: (number | null)[][];
		sampleByDeviceAndTime: Map<string, Map<number, T>>;
		sessionStartTime: number;
		baseDeviceId: string;
	} | null>(null);

	import { ConnectionState } from '$lib/state/websocket.svelte';

	const isStreaming = $derived(
		wsState === ConnectionState.CONNECTED && samples.size > 0 && !isPaused()
	);

	// Time window configuration
	const WINDOW_DURATION = 7.5; // seconds to display
	const UPDATE_INTERVAL_MS = 33; // update every 33ms (~30 FPS)

	// Track if samples are fresh (updated in animation loop)
	let samplesAreFresh = $state(false);

	// Check freshness when samples change
	$effect(() => {
		if (samples.size === 0) {
			samplesAreFresh = false;
			return;
		}

		const now = Date.now() / 1000;
		const STALE_THRESHOLD = 15 + 5;

		for (const deviceSamples of samples.values()) {
			const newestSample = deviceSamples[deviceSamples.length - 1];
			const age = now - newestSample.global_time;
			if (age < STALE_THRESHOLD) {
				samplesAreFresh = true;
				return;
			}
		}

		samplesAreFresh = false;
	});

	// Show plot only if samples are fresh
	const shouldShowPlot = $derived(samplesAreFresh);

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

	// Check if alignment cache is valid
	function isCacheValid(sampleMap: Map<string, T[]>): boolean {
		if (!alignmentCache) return false;

		const devices = Array.from(sampleMap.keys()).sort();
		const currentStartTime = sessionStartTime;

		// Check if session start time changed
		if (currentStartTime !== null && alignmentCache.sessionStartTime !== currentStartTime) {
			return false;
		}

		// Check if device list changed
		if (devices.length !== alignmentCache.deviceOrder.length) {
			return false;
		}
		if (!devices.every((d, idx) => alignmentCache!.deviceOrder[idx] === d)) {
			return false;
		}

		// Check if any device has different sample count OR different timestamps
		for (const deviceId of devices) {
			const currentSamples = sampleMap.get(deviceId) ?? [];
			const cachedCount = alignmentCache.deviceSampleCounts.get(deviceId) ?? 0;

			// Count changed - cache invalid
			if (currentSamples.length !== cachedCount) {
				return false;
			}

			// Count same but check if timestamps changed (samples dropped and added)
			if (currentSamples.length > 0) {
				const cachedDeviceSamples = alignmentCache.sampleByDeviceAndTime.get(deviceId);
				if (!cachedDeviceSamples) return false;

				// Check first and last sample timestamps
				const firstCurrentTime = currentSamples[0].global_time - currentStartTime!;
				const lastCurrentTime = currentSamples[currentSamples.length - 1].global_time - currentStartTime!;

				const cachedTimes = Array.from(cachedDeviceSamples.keys()).sort((a, b) => a - b);
				if (cachedTimes.length === 0) return false;

				const firstCachedTime = cachedTimes[0];
				const lastCachedTime = cachedTimes[cachedTimes.length - 1];

				// If first or last timestamp changed, samples have shifted
				if (Math.abs(firstCurrentTime - firstCachedTime) > 0.001 ||
				    Math.abs(lastCurrentTime - lastCachedTime) > 0.001) {
					return false;
				}
			}
		}

		return true;
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
		const devices = Array.from(sampleMap.keys()).sort();

		if (devices.length === 0 || sampleMap.size === 0) {
			alignmentCache = null;
			deviceOrder = [];
			sampleByDeviceAndTime = new Map();
			verifiedIndicesByDevice = new Map();
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

			deviceOrder = devices;
			const lookup = new Map<number, T>();
			const verifiedIndices: number[] = [];
			for (let i = 0; i < filteredSamples.length; i += 1) {
				const relTime = timestamps[i];
				const sample = filteredSamples[i];
				lookup.set(relTime, sample);
				if (sample.time_verified) {
					verifiedIndices.push(i);
				}
			}
			sampleByDeviceAndTime = new Map([[devices[0], lookup]]);
			verifiedIndicesByDevice = new Map([[devices[0], verifiedIndices]]);

			return {
				data: [timestamps, values],
				devices,
				samples: filteredSamples
			};
		}

		// Multiple devices - align by timestamp
		const currentStartTime = sessionStartTime ?? 0;

		// Check if we can use cached alignment
		const useCachedAlignment = isCacheValid(sampleMap);

		if (!useCachedAlignment) {
			// Need to rebuild alignment cache
			// console.log(`[${title}] Rebuilding alignment cache for ${devices.length} devices`);

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
				alignmentCache = null;
				deviceOrder = [];
				sampleByDeviceAndTime = new Map();
				verifiedIndicesByDevice = new Map();
				return { data: [[], []], devices: [], samples: [] };
			}

			// Set session start time from first sample if not set
			if (sessionStartTime === null && baseSamples.length > 0) {
				setSessionStartTime(baseSamples[0].global_time);
			}

			const startTime = sessionStartTime ?? baseSamples[0].global_time;

			// Build full alignment (no time window filtering)
			const allTimestamps = baseSamples.map((s) => s.global_time - startTime);
			const aligned = alignSamplesToTimestamps(
				sampleMap,
				devices,
				allTimestamps,
				startTime,
				getValue,
				maxGapSeconds
			);

			// Update cache
			alignmentCache = {
				deviceOrder: [...devices],
				deviceSampleCounts: new Map(devices.map((d) => [d, sampleMap.get(d)!.length])),
				timestamps: allTimestamps,
				seriesData: aligned.data.slice(1) as (number | null)[][],
				sampleByDeviceAndTime: aligned.sampleByDeviceAndTime,
				sessionStartTime: startTime,
				baseDeviceId: maxDevice
			};
		}

		// Now filter by time window if provided
		const cachedTimestamps = alignmentCache!.timestamps;
		const cachedSeriesData = alignmentCache!.seriesData;
		const cachedBaseSamples = sampleMap.get(alignmentCache!.baseDeviceId) ?? [];
		const cachedSampleByDevice = alignmentCache!.sampleByDeviceAndTime;

		if (!timeWindow) {
			deviceOrder = alignmentCache!.deviceOrder;
			sampleByDeviceAndTime = cachedSampleByDevice;
			const nextVerified = new Map<string, number[]>();
			for (const deviceId of alignmentCache!.deviceOrder) {
				const deviceSamples = cachedSampleByDevice.get(deviceId);
				const indices: number[] = [];
				if (deviceSamples) {
					for (let i = 0; i < cachedTimestamps.length; i += 1) {
						const sample = deviceSamples.get(cachedTimestamps[i]);
						if (sample?.time_verified) {
							indices.push(i);
						}
					}
				}
				nextVerified.set(deviceId, indices);
			}
			verifiedIndicesByDevice = nextVerified;

			return {
				data: [cachedTimestamps, ...cachedSeriesData],
				devices,
				samples: cachedBaseSamples
			};
		}

		// Filter cached data by time window
		const filteredIndices: number[] = [];
		for (let i = 0; i < cachedTimestamps.length; i++) {
			const relTime = cachedTimestamps[i];
			if (relTime >= timeWindow.minTime && relTime <= timeWindow.maxTime) {
				filteredIndices.push(i);
			}
		}

		const filteredTimestamps = filteredIndices.map((i) => cachedTimestamps[i]);
		const filteredSeriesData = cachedSeriesData.map((series) =>
			filteredIndices.map((i) => series[i])
		);
		const filteredSamples = filteredIndices.map((i) => cachedBaseSamples[i]);

		deviceOrder = alignmentCache!.deviceOrder;
		sampleByDeviceAndTime = cachedSampleByDevice;
		const nextVerified = new Map<string, number[]>();
		for (const deviceId of alignmentCache!.deviceOrder) {
			const deviceSamples = cachedSampleByDevice.get(deviceId);
			const indices: number[] = [];
			if (deviceSamples) {
				for (let i = 0; i < filteredTimestamps.length; i += 1) {
					const sample = deviceSamples.get(filteredTimestamps[i]);
					if (sample?.time_verified) {
						indices.push(i);
					}
				}
			}
			nextVerified.set(deviceId, indices);
		}
		verifiedIndicesByDevice = nextVerified;

		return {
			data: [filteredTimestamps, ...filteredSeriesData],
			devices,
			samples: filteredSamples
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
			series: createDeviceSeries(
				devices,
				showVerifiedPoints ? (deviceId) => verifiedIndicesByDevice.get(deviceId) ?? [] : undefined,
				deviceNicknames,
				true
			),
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

	// Update function for time-based chart updates using requestAnimationFrame
	function updateChart(currentTime: number) {
		if (!chart || !isStreaming) {
			animationFrameId = null;
			samplesAreFresh = false;
			return;
		}

		// Check if samples are fresh
		const now = Date.now() / 1000;
		const STALE_THRESHOLD = 15 + 5; // MAX_DURATION + 5s margin
		let hasFreshSamples = false;

		for (const deviceSamples of samples.values()) {
			const newestSample = deviceSamples[deviceSamples.length - 1];
			const age = now - newestSample.global_time;
			if (age < STALE_THRESHOLD) {
				hasFreshSamples = true;
				break;
			}
		}

		samplesAreFresh = hasFreshSamples;

		if (!hasFreshSamples) {
			// Samples are stale, stop updating
			animationFrameId = null;
			return;
		}

		// Throttle based on UPDATE_INTERVAL_MS for configurable frame rate
		const deltaTime = currentTime - lastUpdateTime;
		if (deltaTime < UPDATE_INTERVAL_MS) {
			// Schedule next frame
			animationFrameId = requestAnimationFrame(updateChart);
			return;
		}

		lastUpdateTime = currentTime;

		const timeWindow = getCurrentTimeWindow();
		if (!timeWindow) {
			// Schedule next frame
			animationFrameId = requestAnimationFrame(updateChart);
			return;
		}

		const { data } = prepareChartData(samples, timeWindow);

		// Update the range array (chart will use function to read it)
		xAxisRange[0] = timeWindow.minTime;
		xAxisRange[1] = timeWindow.maxTime;

		// Periodic logging every 30 updates (disabled)
		// updateCounter++;
		// if (updateCounter % 30 === 0) {
		// 	const wallTime = Date.now() / 1000;
		// 	const devices = Array.from(samples.keys());
		// 	const bufferInfo = devices.map((deviceId) => {
		// 		const deviceSamples = samples.get(deviceId)!;
		// 		const lastSample = deviceSamples[deviceSamples.length - 1];
		// 		if (!lastSample) return `${deviceId}: none`;
		// 		const relTime = lastSample.global_time - (sessionStartTime ?? 0);
		// 		return `${deviceId}: rel=${relTime.toFixed(2)}s`;
		// 	}).join(', ');

		// 	console.log(
		// 		`[${title}] window=[${timeWindow.minTime.toFixed(2)}, ${timeWindow.maxTime.toFixed(2)}], sessionStart=${sessionStartTime?.toFixed(2)}, buffer: ${bufferInfo}, dataPoints=${data[0].length}`
		// 	);
		// }

		// setData will now use the updated range via the function
		chart.setData(data);

		// Schedule next frame
		animationFrameId = requestAnimationFrame(updateChart);
	}


	// Start/stop animation loop based on streaming state
	$effect(() => {
		if (isStreaming && chart) {
			// Start animation loop
			if (animationFrameId === null) {
				// console.log(`[${title}] Starting animation loop`);
				lastUpdateTime = performance.now();
				animationFrameId = requestAnimationFrame(updateChart);
			}
		} else {
			// Stop animation loop
			if (animationFrameId !== null) {
				// console.log(`[${title}] Stopping animation loop`);
				cancelAnimationFrame(animationFrameId);
				animationFrameId = null;
			}
		}

		// Cleanup on effect disposal
		return () => {
			if (animationFrameId !== null) {
				cancelAnimationFrame(animationFrameId);
				animationFrameId = null;
			}
		};
	});

	// Create/destroy chart based on shouldShowPlot
	$effect(() => {
		if (!shouldShowPlot) {
			// Destroy chart when not showing plot
			if (chart) {
				chart.destroy();
				chart = null;
			}
			return;
		}

		if (!uPlotLib) {
			return;
		}

		// Wait for plotContainer to exist and have dimensions
		if (!plotContainer || plotContainer.clientWidth === 0) {
			// Defer until next frame when layout is calculated
			const rafId = requestAnimationFrame(() => {
				if (plotContainer && plotContainer.clientWidth > 0 && !chart) {
					createChart();
				}
			});
			return () => cancelAnimationFrame(rafId);
		}

		if (!chart) {
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
				const deviceId = deviceOrder[seriesIdx - 1];
				const sample = deviceId ? sampleByDeviceAndTime.get(deviceId)?.get(xVal) : undefined;
				if (sample) {
					const verified = sample.time_verified ? ' ✓' : '';
					return `
						<table style="border-collapse: collapse;">
							<tr><td style="padding: 1px 4px 1px 0;">ID:</td><td style="padding: 1px 0;">${sample.id}</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Value:</td><td style="padding: 1px 0;">${yVal.toFixed(0)}</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Time:</td><td style="padding: 1px 0;">${xVal.toFixed(4)}s</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Polar:</td><td style="padding: 1px 0;">${(sample.polar_clock_us / 1_000_000).toFixed(3)}s${verified}</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Receiver:</td><td style="padding: 1px 0;">${(sample.receiver_clock_us / 1_000_000).toFixed(3)}s</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Wall:</td><td style="padding: 1px 0;">${(sample.wall_clock_us / 1_000_000).toFixed(3)}s</td></tr>
						</table>
					`;
				}
				return `
					<table style="border-collapse: collapse;">
						<tr><td style="padding: 1px 4px 1px 0;">Time:</td><td style="padding: 1px 0;">${xVal.toFixed(4)}s</td></tr>
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
		if (animationFrameId !== null) {
			cancelAnimationFrame(animationFrameId);
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

		<div class="border border-gray-200 rounded-lg">
			{#if shouldShowPlot}
				<div bind:this={plotContainer} class="w-full h-[400px]"></div>
			{:else}
				<div class="bg-gray-50 p-12 text-center">
					<p class="text-gray-500">{emptyMessage}</p>
				</div>
			{/if}
		</div>
	</Card>
{:else}
	<div class="border border-gray-200 rounded-lg">
		{#if shouldShowPlot}
			<div bind:this={plotContainer} class="w-full h-[400px]"></div>
		{:else}
			<div class="bg-gray-50 p-12 text-center">
				<p class="text-gray-500">{emptyMessage}</p>
			</div>
		{/if}
	</div>
{/if}
