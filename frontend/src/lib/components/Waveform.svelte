<script lang="ts" generics="T extends PlottableSample">
	import { onDestroy, onMount } from 'svelte';
	import type uPlot from 'uplot';
	import { browser } from '$app/environment';
	import type { PlottableSample, Session } from '$lib/types/api';
	import type { AlignMode } from '$lib/utils/samples';
	import { flattenGroupedSamples } from '$lib/utils/samples';
	import { SvelteMap } from 'svelte/reactivity';
	import WaveformPlot, {
		type WaveformPlotApi,
		type WaveformPlotOptions
	} from './WaveformPlot.svelte';
	import { buildPlotOptions } from '$lib/waveforms/plot-configuration';
	import { prepareChartData, extractVerifiedIndices } from '$lib/waveforms/chart-data-transformer';
	let createDeviceSeries = $state<
		| ((
				deviceIds: string[],
				getVerifiedIndices?: (deviceId: string) => number[],
				deviceNicknames?: Map<string, string>,
				spanGaps?: boolean
		  ) => uPlot.Series[])
		| null
	>(null);
	let createAxes = $state<((yLabel: string) => uPlot.Axis[]) | null>(null);
	let tooltipsPlugin = $state<ReturnType<
		typeof import('$lib/utils/uplot-tooltips').tooltipsPlugin
	> | null>(null);

	interface Props {
		session: Session;
		loading?: boolean;
		showVerifiedPoints?: boolean;
		deviceNicknames?: Map<string, string>;
		timeSyncEnabled?: boolean;
		sharedTimeWindow?: { minTime: number; maxTime: number } | null;
		onTimeWindowChange?: (window: { minTime: number; maxTime: number }) => void;
		maxGapSeconds?: number;
		alignMode?: AlignMode;
		/**
		 * Function to fetch samples from API
		 */
		fetchSamples: (
			sessionId: number,
			params: { start_time: number; end_time: number }
		) => Promise<{ devices: Record<string, Omit<T, 'device_id'>[]> }>;
		/**
		 * Function to extract the value from a sample for plotting
		 */
		getValue: (sample: T) => number;
		/**
		 * Y-axis label
		 */
		yAxisLabel: string;
		/**
		 * Custom tooltip formatter for sample-specific data
		 */
		formatTooltip?: (sample: T, xVal: number, yVal: number) => string;
	}

	let {
		session,
		loading = false,
		showVerifiedPoints = false,
		deviceNicknames,
		timeSyncEnabled = false,
		sharedTimeWindow = null,
		onTimeWindowChange,
		maxGapSeconds = 0.1,
		alignMode = 'linear',
		fetchSamples,
		getValue,
		yAxisLabel,
		formatTooltip
	}: Props = $props();

	let chartApi: WaveformPlotApi | null = null;
	let loadedSamples: T[] = $state([]);
	let isLoadingData = $state(false);
	let plotData: uPlot.AlignedData = $state([[], []]);
	let plotDevices: string[] = $state([]);
	let plotOptions: WaveformPlotOptions | null = $state(null);
	let plotOptionsKey = $state('');

	let samplesByDevice: (T | null)[][] = $state([]);
	let verifiedIndicesByDevice = new SvelteMap<string, number[]>();

	// Track the currently loaded time range
	let loadedTimeRange = $state<{ start: number; end: number } | null>(null);

	// Track current viewport for display
	let currentViewport = $state<{ start: number; end: number; sampleCount: number } | null>(null);

	const INITIAL_WINDOW_SECONDS = 30;
	const MAX_WINDOW_SECONDS = 30; // Maximum zoom out window

	// Debounce for fetching data
	let fetchTimeout: ReturnType<typeof setTimeout> | null = null;
	const FETCH_DEBOUNCE_MS = 300;

	// Flag to prevent setScale hook from triggering during programmatic updates
	let programmaticUpdate = false;

	const loadTimeRange = async (startTime: number, endTime: number) => {
		// Skip if already loading or if we have this range
		if (isLoadingData) return;

		if (
			loadedTimeRange &&
			Math.abs(loadedTimeRange.start - startTime) < 0.001 &&
			Math.abs(loadedTimeRange.end - endTime) < 0.001
		) {
			return;
		}

		console.log(
			`[Waveform] Loading time range: ${new Date(startTime * 1000).toISOString()} to ${new Date(endTime * 1000).toISOString()}`
		);
		isLoadingData = true;

		try {
			// Don't request limit - let server return all samples in the time range
			// This ensures we get complete data even for large windows
			const response = await fetchSamples(session.id, {
				start_time: startTime,
				end_time: endTime
			});

			// Flatten grouped data back into samples array with device_id
			const samples = flattenGroupedSamples<T>(response.devices);

			console.log(`[Waveform] Loaded ${samples.length} samples`);
			loadedSamples = samples;
			loadedTimeRange = { start: startTime, end: endTime };

			const chartData = prepareChartDataLocal(loadedSamples);
			plotData = chartData.data;
			plotDevices = chartData.devices;
			rebuildPlotOptions(chartData.devices);

			if (chartApi) {
				programmaticUpdate = true;
				chartApi.setDataPreserveScale(chartData.data, 'x');
				setTimeout(() => {
					programmaticUpdate = false;
				}, 0);
			}
		} catch (error) {
			console.error('[Waveform] Error loading samples:', error);
		} finally {
			isLoadingData = false;
		}
	};

	// Prepare data for uPlot (convert to relative session time)
	const prepareChartDataLocal = (samples: T[]): { data: uPlot.AlignedData; devices: string[] } => {
		if (samples.length === 0) {
			samplesByDevice = [];
			verifiedIndicesByDevice = new SvelteMap();
			return { data: [[], []], devices: [] };
		}

		const inferredDevices = [...new Set(samples.map((s) => s.device_id))];
		const stableDeviceOrder = session.devices?.length ? session.devices : inferredDevices.sort();

		const chartData = prepareChartData({
			samples,
			getValue,
			referenceTime: session.start_time,
			maxGapSeconds,
			alignMode,
			deviceOrder: stableDeviceOrder
		});

		// Update component state
		samplesByDevice = chartData.samplesByDevice;
		verifiedIndicesByDevice = new SvelteMap(extractVerifiedIndices(chartData));

		return {
			data: chartData.data,
			devices: chartData.deviceOrder
		};
	};

	// Plugin for wheel zoom and middle-click pan
	function wheelZoomPlugin() {
		return {
			hooks: {
				ready: [
					(u: uPlot) => {
						const over = u.over;

						// Middle-click drag to pan
						over.addEventListener('mousedown', (e) => {
							if (e.button === 1) {
								e.preventDefault();
								const left0 = e.clientX;
								const scXMin0 = u.scales.x.min!;
								const scXMax0 = u.scales.x.max!;
								const xUnitsPerPx = u.posToVal(1, 'x') - u.posToVal(0, 'x');

								const onMove = (e2: MouseEvent) => {
									e2.preventDefault();
									const left1 = e2.clientX;
									const dx = xUnitsPerPx * (left1 - left0);

									// Clamp to session bounds (relative time: 0 to session duration)
									let newMin = scXMin0 - dx;
									let newMax = scXMax0 - dx;
									const range = newMax - newMin;

									const sessionDuration = session.duration_seconds ?? INITIAL_WINDOW_SECONDS;

									if (newMin < 0) {
										newMin = 0;
										newMax = range;
									}
									if (newMax > sessionDuration) {
										newMax = sessionDuration;
										newMin = sessionDuration - range;
									}

									u.setScale('x', { min: newMin, max: newMax });
								};

								const onUp = () => {
									document.removeEventListener('mousemove', onMove);
									document.removeEventListener('mouseup', onUp);
								};

								document.addEventListener('mousemove', onMove);
								document.addEventListener('mouseup', onUp);
							}
						});

						// Wheel zoom
						over.addEventListener('wheel', (e) => {
							e.preventDefault();
							const { left } = u.cursor;
							const leftPct = left! / u.bbox.width;
							const xVal = u.posToVal(left!, 'x');
							const oxRange = u.scales.x.max! - u.scales.x.min!;
							const factor = 0.75;
							let nxRange = e.deltaY < 0 ? oxRange * factor : oxRange / factor;

							// If trying to zoom out beyond max window, ignore the event
							if (e.deltaY > 0 && oxRange >= MAX_WINDOW_SECONDS) {
								return;
							}

							// Limit maximum zoom out to MAX_WINDOW_SECONDS
							if (nxRange > MAX_WINDOW_SECONDS) {
								nxRange = MAX_WINDOW_SECONDS;
							}

							let nxMin = xVal - leftPct * nxRange;
							let nxMax = nxMin + nxRange;

							// Clamp to session bounds (relative time: 0 to session duration)
							const sessionDuration = session.duration_seconds ?? INITIAL_WINDOW_SECONDS;

							if (nxMin < 0) {
								nxMin = 0;
								nxMax = nxRange;
							}
							if (nxMax > sessionDuration) {
								nxMax = sessionDuration;
								nxMin = sessionDuration - nxRange;
							}
							// Don't allow zooming out beyond session bounds
							if (nxMin < 0) {
								nxMin = 0;
							}
							if (nxMax > sessionDuration) {
								nxMax = sessionDuration;
							}

							u.setScale('x', { min: nxMin, max: nxMax });
						});
					}
				]
			}
		};
	}

	function rebuildPlotOptions(devices: string[]) {
		if (!createDeviceSeries || !createAxes) {
			plotOptions = null;
			plotOptionsKey = '';
			return;
		}

		const nextKey = [
			devices.join('|'),
			showVerifiedPoints ? 'v1' : 'v0',
			yAxisLabel,
			deviceNicknames ? `n${deviceNicknames.size}` : 'n0',
			tooltipsPlugin ? 't1' : 't0'
		].join('|');

		if (nextKey === plotOptionsKey) {
			return;
		}
		plotOptionsKey = nextKey;

		plotOptions = buildPlotOptions({
			devices,
			yAxisLabel,
			height: 400,
			showVerifiedPoints,
			getVerifiedIndices: (deviceId) => verifiedIndicesByDevice.get(deviceId) ?? [],
			deviceNicknames,
			spanGaps: true,
			plugins: tooltipsPlugin ? [wheelZoomPlugin(), tooltipsPlugin] : [wheelZoomPlugin()],
			scales: {
				x: {
					time: false
				}
			},
			hooks: {
				setScale: [
					(u) => {
						const xScale = u.scales.x;
						if (!xScale || xScale.min === undefined || xScale.max === undefined) return;

						// Scale values are in relative time (seconds from session start)
						const relativeStart = xScale.min;
						const relativeEnd = xScale.max;

						// Update viewport info for display (use relative time)
						currentViewport = {
							start: relativeStart,
							end: relativeEnd,
							sampleCount: loadedSamples.length
						};

						// If time sync is enabled, notify parent of time window change
						if (timeSyncEnabled && onTimeWindowChange && !programmaticUpdate) {
							onTimeWindowChange({ minTime: relativeStart, maxTime: relativeEnd });
						}

						// Skip data loading if this is a programmatic update
						if (programmaticUpdate) return;

						// Convert relative time to global time for API requests
						const globalStart = session.start_time + relativeStart;
						const globalEnd = session.start_time + relativeEnd;

						// Clamp to session bounds (global time)
						const sessionEnd = session.end_time ?? session.start_time + INITIAL_WINDOW_SECONDS;
						const clampedStart = Math.max(globalStart, session.start_time);
						const clampedEnd = Math.min(globalEnd, sessionEnd);

						// Check if we need to load new data (10% threshold)
						const currentWindow = relativeEnd - relativeStart;
						const threshold = currentWindow * 0.1;

						if (
							!loadedTimeRange ||
							Math.abs(loadedTimeRange.start - clampedStart) > threshold ||
							Math.abs(loadedTimeRange.end - clampedEnd) > threshold
						) {
							// Debounce the fetch
							if (fetchTimeout) {
								clearTimeout(fetchTimeout);
							}
							fetchTimeout = setTimeout(() => {
								loadTimeRange(clampedStart, clampedEnd);
								fetchTimeout = null;
							}, FETCH_DEBOUNCE_MS);
						}
					}
				]
			},
			legend: {
				show: true
			},
			createDeviceSeries,
			createAxes
		});
	}

	// Initialize: load first window of data
	const initialize = async () => {
		if (loading || !session) return;

		const sessionDuration = session.duration_seconds ?? INITIAL_WINDOW_SECONDS;
		const windowSize = Math.min(INITIAL_WINDOW_SECONDS, sessionDuration);

		// Load data using global time for API
		const globalStart = session.start_time;
		const globalEnd = session.start_time + windowSize;

		await loadTimeRange(globalStart, globalEnd);
	};

	// Initialize once when component is ready
	let initialized = false;
	$effect(() => {
		if (!loading && session && !initialized) {
			initialized = true;
			initialize();
		}
	});

	// Rebuild plot options once plotting helpers are ready
	$effect(() => {
		if (!plotDevices.length) return;
		if (!createDeviceSeries || !createAxes) return;
		rebuildPlotOptions(plotDevices);
	});

	// Sync with shared time window when time sync is enabled
	$effect(() => {
		if (timeSyncEnabled && sharedTimeWindow && chartApi) {
			// Set programmatic update flag to prevent triggering setScale hook
			programmaticUpdate = true;
			chartApi.setScale('x', {
				min: sharedTimeWindow.minTime,
				max: sharedTimeWindow.maxTime
			});
			programmaticUpdate = false;
		}
	});

	onMount(async () => {
		if (!browser) return;

		// Dynamically import uPlot and utilities only in browser
		const [utilsModule, tooltipsModule] = await Promise.all([
			import('$lib/utils/uplot'),
			import('$lib/utils/uplot-tooltips')
		]);
		createDeviceSeries = utilsModule.createDeviceSeries;
		createAxes = (yLabel: string) => utilsModule.createAxes(yLabel);
		tooltipsPlugin = tooltipsModule.tooltipsPlugin({
			showSeriesPoints: true,
			showCursorPosition: false,
			formatValue: (xVal, yVal, seriesIdx, dataIdx) => {
				const deviceIdx = seriesIdx - 1;
				const sample = samplesByDevice[deviceIdx]?.[dataIdx];
				if (sample && formatTooltip) {
					return formatTooltip(sample, xVal, yVal);
				} else if (sample) {
					// Default tooltip
					const verified = sample.time_verified ? ' ✓' : '';
					return `
						<table style="border-collapse: collapse;">
							<tr><td style="padding: 1px 4px 1px 0;">ID:</td><td style="padding: 1px 0;">${sample.id}</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Value:</td><td style="padding: 1px 0;">${yVal.toFixed(3)}</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Time:</td><td style="padding: 1px 0;">${xVal.toFixed(4)}s</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Global:</td><td style="padding: 1px 0;">${sample.global_time.toFixed(3)}s</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Polar:</td><td style="padding: 1px 0;">${(sample.polar_clock_us / 1_000_000).toFixed(3)}s${verified}</td></tr>
						</table>
					`;
				}
				return `
					<table style="border-collapse: collapse;">
						<tr><td style="padding: 1px 4px 1px 0;">Time:</td><td style="padding: 1px 0;">${xVal.toFixed(4)}s</td></tr>
						<tr><td style="padding: 1px 4px 1px 0;">Value:</td><td style="padding: 1px 0;">${yVal.toFixed(3)}</td></tr>
					</table>
				`;
			}
		});

		rebuildPlotOptions(plotDevices);
	});

	onDestroy(() => {
		if (fetchTimeout) {
			clearTimeout(fetchTimeout);
		}
	});
</script>

<div>
	<div class="flex items-center justify-end mb-4 gap-4">
		{#if isLoadingData}
			<div class="flex items-center gap-2 text-xs text-status-info-fg">
				<div class="w-2 h-2 bg-status-info-fg rounded-full animate-pulse"></div>
				<span>Loading data...</span>
			</div>
		{/if}
		{#if !loading}
			<div class="flex flex-col items-end gap-1">
				{#if currentViewport}
					<div class="text-xs font-mono text-gray-600">
						Loaded: {currentViewport.sampleCount.toLocaleString()} / {session.ecg_sample_count.toLocaleString()}
						samples
					</div>
					<div class="text-xs text-gray-500">
						Window: {(currentViewport.end - currentViewport.start).toFixed(1)}s ({currentViewport.start.toFixed(
							1
						)}s - {currentViewport.end.toFixed(1)}s)
					</div>
				{/if}
			</div>
		{/if}
	</div>

	{#if loadedSamples.length === 0 && !loading && !isLoadingData}
		<div class="border border-gray-200 rounded-lg bg-gray-50 p-12 text-center">
			<p class="text-gray-500">No data to display</p>
		</div>
	{:else}
		<WaveformPlot
			data={plotData}
			options={plotOptions}
			plotClass="border border-gray-200 rounded-lg"
			onReady={(api) => {
				chartApi = api;
			}}
			onChartDestroy={() => {
				chartApi = null;
			}}
		/>
	{/if}
</div>
