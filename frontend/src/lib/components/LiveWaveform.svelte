<script lang="ts" generics="T extends PlottableSample">
	import { onDestroy, onMount } from 'svelte';
	import type uPlot from 'uplot';
	import type { AlignedData } from 'uplot';
	import { browser } from '$app/environment';
	import type { PlottableSample } from '$lib/types/api';
	import { isPaused } from '$lib/state/pause.svelte';
	import type { AlignMode } from '$lib/utils/samples';
	import { SvelteMap } from 'svelte/reactivity';
	import {
		prepareChartData as prepareChartDataUtil,
		extractVerifiedIndices
	} from '$lib/waveforms/chart-data-transformer';
	import { calculateTimeWindow } from '$lib/waveforms/time-window';
	import {
		isCacheValid as checkCacheValid,
		findBaseDevice,
		type AlignmentCache
	} from '$lib/waveforms/alignment-cache';
	import {
		getCurrentPlaybackTime,
		getSessionStartTime,
		setSessionStartTime
	} from '$lib/state/session-time.svelte';
	import type { ConnectionStateType } from '$lib/state/websocket.svelte';
	import Button from './buttons/Button.svelte';
	import Card from './Card.svelte';
	import WaveformPlot, { type WaveformPlotOptions } from './WaveformPlot.svelte';
	import { buildPlotOptions } from '$lib/waveforms/plot-configuration';
	import 'uplot/dist/uPlot.min.css';

	interface Props {
		samples: SvelteMap<string, T[]> | Map<string, T[]>;
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
		alignMode?: AlignMode;
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
		maxGapSeconds = 0.1,
		alignMode = 'linear'
	}: Props = $props();

	let createDeviceSeries:
		| ((
				deviceIds: string[],
				getVerifiedIndices?: (deviceId: string) => number[],
				deviceNicknames?: Map<string, string>,
				spanGaps?: boolean
		  ) => uPlot.Series[])
		| null = null;
	let createAxes: ((yLabel: string) => uPlot.Axis[]) | null = null;
	let tooltipsPlugin: ReturnType<typeof import('$lib/utils/uplot-tooltips').tooltipsPlugin> | null =
		null;
	let plotData: AlignedData = $state([[], []]);
	let plotOptions: WaveformPlotOptions | null = $state(null);
	let plotReady = $state(false);
	let animationFrameId: number | null = null;
	let lastUpdateTime = 0;

	let deviceOrder: string[] = $state([]);
	let sampleByDeviceAndTime: Map<string, Map<number, T>> = new Map();
	let verifiedIndicesByDevice = new SvelteMap<string, number[]>();

	// Cache for aligned data to avoid re-aligning on every frame
	let alignmentCache = $state<AlignmentCache<T> | null>(null);

	import { ConnectionState } from '$lib/state/websocket.svelte';

	const isStreaming = $derived(
		wsState === ConnectionState.CONNECTED && samples.size > 0 && !isPaused()
	);

	// Time window configuration
	const WINDOW_DURATION = 7.5; // seconds to display
	const UPDATE_INTERVAL_MS = 33; // update every 33ms (~30 FPS)

	// Track if samples are fresh (updated when samples change)
	let samplesAreFresh = $state(false);

	// Check freshness when samples change
	$effect(() => {
		// Must read into the SvelteMap contents to track it as a dependency.
		// Array.from(samples.values()) forces reading the map's values.
		const allDeviceSamples = Array.from(samples.values());
		// Reading nested array lengths ensures Svelte tracks changes to array contents.
		const totalSamples = allDeviceSamples.reduce((sum, arr) => sum + arr.length, 0);

		if (totalSamples === 0) {
			samplesAreFresh = false;
			return;
		}

		const now = Date.now() / 1000;
		const STALE_THRESHOLD = 15 + 5;

		for (const deviceSamples of allDeviceSamples) {
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

	// Initialize plot options and data once dependencies are ready
	$effect(() => {
		if (!shouldShowPlot || plotOptions || !createDeviceSeries || !createAxes) {
			return;
		}

		const { data, devices } = prepareChartData(samples);
		plotData = data;

		if (devices.length > 0) {
			rebuildPlotOptions(devices);
		} else {
			plotOptions = null;
		}
	});

	// Rebuild plot options when device order changes
	$effect(() => {
		if (!createDeviceSeries || !createAxes) return;
		if (deviceOrder.length === 0) return;
		rebuildPlotOptions(deviceOrder);
	});

	// X-axis range controlled by function (prevents setData from resetting scale)
	let xAxisRange: [number, number] = [0, WINDOW_DURATION];

	// Use shared session start time for synchronization across all waveforms
	const sessionStartTime = $derived(getSessionStartTime());

	// Get current time window based on wall-clock progression (shared across all waveforms)
	function getCurrentTimeWindow(): { minTime: number; maxTime: number } | null {
		const currentTime = getCurrentPlaybackTime();
		return calculateTimeWindow(currentTime, WINDOW_DURATION);
	}

	// Check if alignment cache is valid
	function isCacheValid(sampleMap: Map<string, T[]>): boolean {
		return checkCacheValid(alignmentCache, sampleMap, sessionStartTime);
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
			sampleByDeviceAndTime = new SvelteMap();
			verifiedIndicesByDevice = new SvelteMap();
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
			const lookup = new SvelteMap<number, T>();
			const verifiedIndices: number[] = [];
			for (let i = 0; i < filteredSamples.length; i += 1) {
				const relTime = timestamps[i];
				const sample = filteredSamples[i];
				lookup.set(relTime, sample);
				if (sample.time_verified) {
					verifiedIndices.push(i);
				}
			}
			sampleByDeviceAndTime = new SvelteMap([[devices[0], lookup]]);
			verifiedIndicesByDevice = new SvelteMap([[devices[0], verifiedIndices]]);

			return {
				data: [timestamps, values],
				devices,
				samples: filteredSamples
			};
		}

		// Multiple devices - align by timestamp
		// Check if we can use cached alignment
		const useCachedAlignment = isCacheValid(sampleMap);

		if (!useCachedAlignment) {
			// Need to rebuild alignment cache
			// console.log(`[${title}] Rebuilding alignment cache for ${devices.length} devices`);

			// Find the device with the most samples to use as time base
			const maxDevice = findBaseDevice(sampleMap);
			if (!maxDevice) {
				alignmentCache = null;
				deviceOrder = [];
				sampleByDeviceAndTime = new SvelteMap();
				verifiedIndicesByDevice = new SvelteMap();
				return { data: [[], []], devices: [], samples: [] };
			}

			const baseSamples = sampleMap.get(maxDevice)!;
			if (baseSamples.length === 0) {
				alignmentCache = null;
				deviceOrder = [];
				sampleByDeviceAndTime = new SvelteMap();
				verifiedIndicesByDevice = new SvelteMap();
				return { data: [[], []], devices: [], samples: [] };
			}

			// Set session start time from first sample if not set
			if (sessionStartTime === null && baseSamples.length > 0) {
				setSessionStartTime(baseSamples[0].global_time);
			}

			const alignStartTime = sessionStartTime ?? baseSamples[0].global_time;

			// Build full alignment (no time window filtering)
			const aligned = prepareChartDataUtil({
				samples: sampleMap,
				getValue,
				referenceTime: alignStartTime,
				maxGapSeconds,
				alignMode,
				deviceOrder: devices
			});

			// Update cache
			alignmentCache = {
				deviceOrder: aligned.deviceOrder,
				deviceSampleCounts: new Map(devices.map((d) => [d, sampleMap.get(d)!.length])),
				timestamps: aligned.timestamps,
				seriesData: aligned.data.slice(1) as (number | null)[][],
				sampleByDeviceAndTime: aligned.sampleByDeviceAndTime,
				sessionStartTime: alignStartTime,
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
			verifiedIndicesByDevice = new SvelteMap(
				extractVerifiedIndices({
					data: [cachedTimestamps, ...cachedSeriesData],
					deviceOrder: alignmentCache!.deviceOrder,
					sampleByDeviceAndTime: cachedSampleByDevice,
					timestamps: cachedTimestamps
				})
			);

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
		verifiedIndicesByDevice = new SvelteMap(
			extractVerifiedIndices({
				data: [filteredTimestamps, ...filteredSeriesData],
				deviceOrder: alignmentCache!.deviceOrder,
				sampleByDeviceAndTime: cachedSampleByDevice,
				timestamps: filteredTimestamps
			})
		);

		return {
			data: [filteredTimestamps, ...filteredSeriesData],
			devices,
			samples: filteredSamples
		};
	}

	function rebuildPlotOptions(devices: string[]) {
		if (!createDeviceSeries || !createAxes) {
			plotOptions = null;
			return;
		}

		plotOptions = buildPlotOptions({
			devices,
			yAxisLabel,
			height: 400,
			showVerifiedPoints,
			getVerifiedIndices: (deviceId) => verifiedIndicesByDevice.get(deviceId) ?? [],
			deviceNicknames,
			spanGaps: true,
			plugins: tooltipsPlugin ? [tooltipsPlugin] : [],
			scales: {
				x: {
					time: false,
					auto: false,
					range: () => xAxisRange
				}
			},
			legend: {
				show: true
			},
			createDeviceSeries,
			createAxes
		});
	}

	// Update function for time-based chart updates using requestAnimationFrame
	function updateChart(currentTime: number) {
		if (!plotReady || !isStreaming) {
			animationFrameId = null;
			return;
		}

		if (!samplesAreFresh) {
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

		const { data, devices } = prepareChartData(samples, timeWindow);

		// Update the range array (plot will use function to read it)
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
		plotData = data;
		if (devices.length === 0) {
			plotOptions = null;
		}

		// Schedule next frame
		animationFrameId = requestAnimationFrame(updateChart);
	}

	// Start/stop animation loop based on streaming state
	$effect(() => {
		if (isStreaming && plotReady) {
			// Start animation loop
			if (animationFrameId === null) {
				lastUpdateTime = performance.now();
				animationFrameId = requestAnimationFrame(updateChart);
			}
		} else {
			// Stop animation loop
			if (animationFrameId !== null) {
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

	onMount(async () => {
		if (!browser) return;

		// Dynamically import utilities only in browser
		const [utilsModule, tooltipsModule] = await Promise.all([
			import('$lib/utils/uplot'),
			import('$lib/utils/uplot-tooltips')
		]);
		createDeviceSeries = utilsModule.createDeviceSeries;
		createAxes = utilsModule.createAxes;
		tooltipsPlugin = tooltipsModule.tooltipsPlugin({
			showSeriesPoints: true,
			showCursorPosition: false,
			formatValue: (xVal, yVal, seriesIdx) => {
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

		rebuildPlotOptions(deviceOrder);
	});

	onDestroy(() => {
		if (animationFrameId !== null) {
			cancelAnimationFrame(animationFrameId);
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
					rebuildPlotOptions(deviceOrder);
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
				<WaveformPlot
					data={plotData}
					options={plotOptions}
					plotClass="w-full h-[400px]"
					onReady={() => {
						plotReady = true;
					}}
					onChartDestroy={() => {
						plotReady = false;
					}}
				/>
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
			<WaveformPlot
				data={plotData}
				options={plotOptions}
				plotClass="w-full h-[400px]"
				onReady={() => {
					plotReady = true;
				}}
				onChartDestroy={() => {
					plotReady = false;
				}}
			/>
		{:else}
			<div class="bg-gray-50 p-12 text-center">
				<p class="text-gray-500">{emptyMessage}</p>
			</div>
		{/if}
	</div>
{/if}
