<script lang="ts" generics="T extends PlottableSample">
	import { onDestroy, onMount, untrack } from 'svelte';
	import type uPlot from 'uplot';
	import type { AlignedData } from 'uplot';
	import { browser } from '$app/environment';
	import type { PlottableSample } from '$lib/types/api';
	import { isPaused } from '$lib/state/pause.svelte';
	import type { AlignMode } from '$lib/utils/samples';
	import {
		prepareChartData as prepareChartDataUtil,
		extractVerifiedIndices
	} from '$lib/waveforms/chart-data-transformer';
	import { RenderCache } from '$lib/waveforms/render-cache';
	import { calculateTimeWindow } from '$lib/waveforms/time-window';
	import {
		isCacheValid as checkCacheValid,
		findBaseDevice,
		type AlignmentCache
	} from '$lib/waveforms/alignment-cache';
	import { updateAlignmentCache } from '$lib/waveforms/incremental-alignment';
	import {
		getCurrentPlaybackTime,
		getSessionStartTime,
		setSessionStartTime
	} from '$lib/state/session-time.svelte';
	import type { ConnectionStateType } from '$lib/state/websocket.svelte';
	import Button from './buttons/Button.svelte';
	import Card from './Card.svelte';
	import WaveformPlot, {
		type WaveformPlotOptions,
		type WaveformPlotApi
	} from './WaveformPlot.svelte';
	import { buildPlotOptions } from '$lib/waveforms/plot-configuration';
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
		alignMode = 'exact'
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
	// Reuse array references to avoid forcing uPlot to redraw from scratch
	let plotData: AlignedData = $state([[], []]);
	let plotOptions: WaveformPlotOptions | null = $state(null);
	let plotReady = $state(false);
	let chartApi: WaveformPlotApi | null = null;
	let animationFrameId: number | null = null;
	let lastUpdateTime = 0;
	let frameCount = 0;
	let lastFpsLog = 0;

	let deviceOrder: string[] = $state([]);
	let samplesByDevice: (T | null)[][] = $state([]);
	// eslint-disable-next-line svelte/prefer-svelte-reactivity
	let verifiedIndicesByDevice = new Map<string, number[]>();

	// Cache for aligned data to avoid re-aligning on every frame
	// Note: Not reactive - this is an internal optimization that doesn't need reactivity
	let alignmentCache: AlignmentCache<T> | null = null;

	// Render cache - reuses arrays to eliminate GC pressure
	const renderCache = new RenderCache<T>();

	import { ConnectionState } from '$lib/state/websocket.svelte';

	// Time window configuration
	const WINDOW_DURATION = 7.5; // seconds to display
	const UPDATE_INTERVAL_MS = 33; // update every 33ms (30 FPS)

	// State computed via polling instead of reactivity
	let isStreaming = $state(false);
	let samplesAreFresh = $state(false);

	// Show plot only if samples are fresh
	const shouldShowPlot = $derived(samplesAreFresh);

	// Poll for streaming status and freshness inside animation loop
	function pollStreamingStatus(): void {
		const totalSamples = Array.from(samples.values()).reduce((sum, arr) => sum + arr.length, 0);

		if (totalSamples === 0) {
			samplesAreFresh = false;
			isStreaming = false;
			console.log(`[${title}] Poll: no samples`);
			return;
		}

		const now = Date.now() / 1000;
		const STALE_THRESHOLD = 30; // Increased from 20 to handle 8 devices + network jitter

		let hasFreshData = false;
		let oldestAge = Infinity;
		for (const deviceSamples of samples.values()) {
			if (deviceSamples.length === 0) continue;
			const newestSample = deviceSamples[deviceSamples.length - 1];
			const age = now - newestSample.global_time;
			if (age < oldestAge) oldestAge = age;
			if (age < STALE_THRESHOLD) {
				hasFreshData = true;
				break;
			}
		}

		const wasStreaming = isStreaming;
		const wasFresh = samplesAreFresh;
		samplesAreFresh = hasFreshData;
		isStreaming = wsState === ConnectionState.CONNECTED && hasFreshData && !isPaused();

		if (wasStreaming !== isStreaming || wasFresh !== samplesAreFresh) {
			console.log(
				`[${title}] Poll: devices=${samples.size}, samples=${totalSamples}, fresh=${hasFreshData}, streaming=${isStreaming}, oldestAge=${oldestAge.toFixed(1)}s`
			);
		}
	}

	// Initialize plot options when devices become available
	// This effect runs when shouldShowPlot becomes true, which happens when fresh data arrives
	// Uses untrack() to read samples without creating ongoing subscription
	$effect(() => {
		// Only run when plot helpers are loaded and we have fresh data to show
		if (!shouldShowPlot || !createDeviceSeries || !createAxes) {
			return;
		}

		// Only initialize if not already done
		if (plotOptions !== null) {
			return;
		}

		// Use untrack to read samples once without subscribing to future updates
		untrack(() => {
			// Initialize with initial data preparation
			const { data, devices } = prepareChartData(samples);
			if (devices.length > 0) {
				// Set initial data and options to make plot render
				plotData = data;
				rebuildPlotOptions(devices);
			}
		});
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

	let lastWindowLog = 0;

	// Get current time window based on wall-clock progression (shared across all waveforms)
	function getCurrentTimeWindow(): { minTime: number; maxTime: number } | null {
		const currentTime = getCurrentPlaybackTime();
		const window = calculateTimeWindow(currentTime, WINDOW_DURATION);

		// Debug logging disabled (was causing performance issues by reading samples every frame)

		return window;
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
		const perfStart = performance.now();
		const devices = Array.from(sampleMap.keys()).sort();
		const t1 = performance.now();

		if (devices.length === 0 || sampleMap.size === 0) {
			alignmentCache = null;
			deviceOrder = [];
			samplesByDevice = [];
			verifiedIndicesByDevice.clear();
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

			// Debug: Log currentStartTime to understand time reference
			const now = Date.now();
			if (now - lastWindowLog > 5000) {
				console.log(
					`[${title}] Single-device path: currentStartTime=${currentStartTime.toFixed(3)}, ` +
						`sessionStartTime=${sessionStartTime?.toFixed(3) ?? 'null'}, ` +
						`firstSample=${deviceSamples[0].global_time.toFixed(3)}`
				);
			}

			// Filter samples by time window if provided using binary search
			let filteredSamples = deviceSamples;
			if (timeWindow) {
				const beforeFilterCount = deviceSamples.length;

				// Binary search for start index
				let left = 0;
				let right = deviceSamples.length;
				while (left < right) {
					const mid = Math.floor((left + right) / 2);
					const relTime = deviceSamples[mid].global_time - currentStartTime;
					if (relTime < timeWindow.minTime) {
						left = mid + 1;
					} else {
						right = mid;
					}
				}
				const startIdx = left;

				// Binary search for end index
				left = startIdx;
				right = deviceSamples.length;
				while (left < right) {
					const mid = Math.floor((left + right) / 2);
					const relTime = deviceSamples[mid].global_time - currentStartTime;
					if (relTime <= timeWindow.maxTime) {
						left = mid + 1;
					} else {
						right = mid;
					}
				}
				const endIdx = left;

				filteredSamples = deviceSamples.slice(startIdx, endIdx);
				const afterFilterCount = filteredSamples.length;

				if (now - lastWindowLog > 5000) {
					if (afterFilterCount > 0) {
						const firstRelTime = filteredSamples[0].global_time - currentStartTime;
						const lastRelTime =
							filteredSamples[filteredSamples.length - 1].global_time - currentStartTime;
						console.log(
							`[${title}] Filter: ${beforeFilterCount} -> ${afterFilterCount}, ` +
								`relTime: [${firstRelTime.toFixed(1)}, ${lastRelTime.toFixed(1)}], ` +
								`window: [${timeWindow.minTime.toFixed(1)}, ${timeWindow.maxTime.toFixed(1)}]`
						);
					} else if (beforeFilterCount > 0) {
						const sampleRelTimes = deviceSamples.map((s) => s.global_time - currentStartTime);
						const minRelTime = Math.min(...sampleRelTimes);
						const maxRelTime = Math.max(...sampleRelTimes);
						console.error(
							`[${title}] FILTERED ALL ${beforeFilterCount} SAMPLES! ` +
								`Sample relTime: [${minRelTime.toFixed(1)}, ${maxRelTime.toFixed(1)}], ` +
								`window: [${timeWindow.minTime.toFixed(1)}, ${timeWindow.maxTime.toFixed(1)}], ` +
								`currentPlaybackTime: ${getCurrentPlaybackTime()?.toFixed(1)}`
						);
					}
				}
			}

			const timestamps = filteredSamples.map((s) => s.global_time - currentStartTime);
			const values = filteredSamples.map((s) => getValue(s));

			deviceOrder = devices;
			const verifiedIndices: number[] = [];
			for (let i = 0; i < filteredSamples.length; i += 1) {
				const sample = filteredSamples[i];
				if (sample.time_verified) {
					verifiedIndices.push(i);
				}
			}
			samplesByDevice = [filteredSamples];
			verifiedIndicesByDevice.clear();
			verifiedIndicesByDevice.set(devices[0], verifiedIndices);

			return {
				data: [timestamps, values],
				devices,
				samples: filteredSamples
			};
		}

		// Multiple devices - align by timestamp
		// Check if we can use cached alignment
		const cacheIsValid = isCacheValid(sampleMap);
		const t2 = performance.now();

		if (cacheIsValid && alignmentCache && sessionStartTime !== null) {
			// Try incremental update
			const updateSuccess = updateAlignmentCache(
				alignmentCache,
				sampleMap,
				getValue,
				sessionStartTime,
				maxGapSeconds,
				alignMode
			);

			if (!updateSuccess) {
				// Incremental update failed - need full rebuild
				console.log(`[${title}] Incremental update failed, forcing full rebuild`);
				alignmentCache = null;
			}
		}
		const t3 = performance.now();

		if (!cacheIsValid || !alignmentCache) {
			// Need to rebuild alignment cache
			const rebuildStart = performance.now();
			console.log(`[${title}] Rebuilding alignment cache for ${devices.length} devices`);

			// Find the device with the most samples to use as time base
			const maxDevice = findBaseDevice(sampleMap);
			if (!maxDevice) {
				alignmentCache = null;
				deviceOrder = [];
				samplesByDevice = [];
				verifiedIndicesByDevice.clear();
				return { data: [[], []], devices: [], samples: [] };
			}

			const baseSamples = sampleMap.get(maxDevice)!;
			if (baseSamples.length === 0) {
				alignmentCache = null;
				deviceOrder = [];
				samplesByDevice = [];
				verifiedIndicesByDevice.clear();
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

			// Calculate timestamp range for cache
			const timestampRange =
				aligned.timestamps.length > 0
					? {
							min: aligned.timestamps[0],
							max: aligned.timestamps[aligned.timestamps.length - 1]
						}
					: { min: 0, max: 0 };

			// Update cache
			alignmentCache = {
				deviceOrder: aligned.deviceOrder,
				deviceSampleCounts: new Map(devices.map((d) => [d, sampleMap.get(d)!.length])),
				timestamps: aligned.timestamps,
				seriesData: aligned.data.slice(1) as (number | null)[][],
				samplesByDevice: aligned.samplesByDevice,
				sessionStartTime: alignStartTime,
				baseDeviceId: maxDevice,
				timestampRange
			};

			// Extract verified indices ONCE when cache is rebuilt (not every frame)
			const verifiedEntries = extractVerifiedIndices(aligned);
			verifiedIndicesByDevice.clear();
			for (const [key, value] of verifiedEntries) {
				verifiedIndicesByDevice.set(key, value);
			}

			const rebuildDuration = performance.now() - rebuildStart;
			console.log(`[${title}] Rebuild took ${rebuildDuration.toFixed(1)}ms`);
		}
		const t4 = performance.now();

		// Now filter by time window if provided
		const cachedTimestamps = alignmentCache!.timestamps;
		const cachedSeriesData = alignmentCache!.seriesData;
		const cachedBaseSamples = sampleMap.get(alignmentCache!.baseDeviceId) ?? [];
		const cachedSamplesByDevice = alignmentCache!.samplesByDevice;

		if (!timeWindow) {
			deviceOrder = alignmentCache!.deviceOrder;
			samplesByDevice = cachedSamplesByDevice;
			// verifiedIndicesByDevice already set when cache was built

			return {
				data: [cachedTimestamps, ...cachedSeriesData],
				devices,
				samples: cachedBaseSamples
			};
		}

		// Use render cache to filter by time window without creating new arrays
		renderCache.updateFromAlignmentCache(
			cachedTimestamps,
			cachedSeriesData,
			cachedSamplesByDevice,
			alignmentCache!.deviceOrder,
			timeWindow
		);

		deviceOrder = alignmentCache!.deviceOrder;
		samplesByDevice = renderCache.samplesByDevice;

		// Don't extract verified indices every frame - they don't change during streaming
		// and extracting them creates new arrays. Only extract when cache is rebuilt.

		const t5 = performance.now();
		const perfDuration = performance.now() - perfStart;
		if (perfDuration > 5) {
			console.log(
				`[${title}] prepare: ${perfDuration.toFixed(1)}ms | setup=${(t1 - perfStart).toFixed(1)}ms, cacheCheck=${(t2 - t1).toFixed(1)}ms, incremental=${(t3 - t2).toFixed(1)}ms, rebuild=${(t4 - t3).toFixed(1)}ms, filter=${(t5 - t4).toFixed(1)}ms, verified=${(perfDuration - t5).toFixed(1)}ms`
			);
		}

		return {
			data: renderCache.toUPlotData(),
			devices,
			samples: [] // Not used in time-windowed path
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

	let lastRafTime = 0;
	let rafGaps: number[] = [];

	// Update function for time-based chart updates using requestAnimationFrame
	function updateChart(currentTime: number) {
		const frameStart = performance.now();
		const t0 = performance.now();

		// Poll streaming status instead of using reactive derived
		pollStreamingStatus();
		const t0b = performance.now();

		// Track RAF callback timing to detect scheduling delays
		if (lastRafTime > 0) {
			const rafGap = frameStart - lastRafTime;
			rafGaps.push(rafGap);
			if (rafGaps.length > 100) rafGaps.shift();
		}
		lastRafTime = frameStart;

		const t1 = performance.now();

		if (!plotReady || !isStreaming) {
			animationFrameId = null;
			return;
		}

		if (!samplesAreFresh) {
			console.log(`[${title}] Animation stopped: samples not fresh`);
			animationFrameId = null;
			return;
		}
		const t2 = performance.now();

		// Throttle based on UPDATE_INTERVAL_MS for configurable frame rate
		const deltaTime = currentTime - lastUpdateTime;
		if (deltaTime < UPDATE_INTERVAL_MS) {
			// Schedule next frame
			animationFrameId = requestAnimationFrame(updateChart);
			return;
		}

		lastUpdateTime = currentTime;
		const t3 = performance.now();

		const timeWindow = getCurrentTimeWindow();
		const t4 = performance.now();
		if (!timeWindow) {
			// Schedule next frame
			animationFrameId = requestAnimationFrame(updateChart);
			return;
		}

		const prepareStart = performance.now();
		const { data, devices } = prepareChartData(samples, timeWindow);
		const prepareEnd = performance.now();
		const t5 = performance.now();

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

		// Call uPlot API directly instead of using Svelte reactivity
		const setDataStart = performance.now();

		if (chartApi) {
			chartApi.setData(data);
		}

		const setDataEnd = performance.now();
		const t6 = performance.now();

		if (devices.length === 0) {
			plotOptions = null;
		}
		const t7 = performance.now();

		const frameEnd = performance.now();
		const frameDuration = frameEnd - frameStart;

		// Detailed frame breakdown
		console.log(
			`[${title}] FRAME: ${frameDuration.toFixed(1)}ms | ` +
				`poll=${(t0b - t0).toFixed(1)}ms, init=${(t1 - t0b).toFixed(1)}ms, checks=${(t2 - t1).toFixed(1)}ms, throttle=${(t3 - t2).toFixed(1)}ms, ` +
				`window=${(t4 - t3).toFixed(1)}ms, prepare=${(t5 - t4).toFixed(1)}ms, setData=${(t6 - t5).toFixed(1)}ms, ` +
				`cleanup=${(t7 - t6).toFixed(1)}ms, logging=${(frameEnd - t7).toFixed(1)}ms`
		);

		frameCount++;
		const now = performance.now();
		if (now - lastFpsLog > 2000) {
			const fps = frameCount / ((now - lastFpsLog) / 1000);
			const maxRafGap = rafGaps.length > 0 ? Math.max(...rafGaps) : 0;
			const jankFrames = rafGaps.filter((gap) => gap > 50).length;

			console.log(
				`[${title}] FPS: ${fps.toFixed(1)}, frames: ${frameCount}, max RAF gap: ${maxRafGap.toFixed(0)}ms, jank: ${jankFrames}`
			);
			frameCount = 0;
			lastFpsLog = now;
			rafGaps = [];
		}

		if (frameDuration > 20) {
			console.log(
				`[${title}] SLOW: ${frameDuration.toFixed(1)}ms (prepare=${(prepareEnd - prepareStart).toFixed(1)}ms, setData=${(setDataEnd - setDataStart).toFixed(1)}ms)`
			);
		}

		// Measure time until next frame actually starts
		const beforeSchedule = performance.now();
		animationFrameId = requestAnimationFrame((time) => {
			const afterSchedule = performance.now();
			const schedulingDelay = afterSchedule - beforeSchedule;
			if (schedulingDelay > 50) {
				console.log(
					`[${title}] DELAY: ${schedulingDelay.toFixed(1)}ms between end of frame and start of next RAF`
				);
			}
			updateChart(time);
		});
	}

	// Start/stop animation loop based on streaming state
	$effect(() => {
		if (isStreaming && plotReady) {
			// Start animation loop
			if (animationFrameId === null) {
				console.log(`[${title}] Starting animation loop`);
				lastUpdateTime = performance.now();
				animationFrameId = requestAnimationFrame(updateChart);
			}
		} else {
			// Stop animation loop
			if (animationFrameId !== null) {
				console.log(
					`[${title}] Stopping animation loop (isStreaming=${isStreaming}, plotReady=${plotReady})`
				);
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

	let statusInterval: ReturnType<typeof setInterval> | null = null;

	onMount(async () => {
		if (!browser) return;

		// Poll streaming status on an interval (independent of animation loop)
		// This ensures samplesAreFresh gets updated even when animation isn't running
		statusInterval = setInterval(() => {
			pollStreamingStatus();
		}, 500); // Poll every 500ms

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
			formatValue: (xVal, yVal, seriesIdx, dataIdx) => {
				const deviceIdx = seriesIdx - 1;
				const sample = samplesByDevice[deviceIdx]?.[dataIdx];
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
		if (statusInterval !== null) {
			clearInterval(statusInterval);
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
					onReady={(api) => {
						chartApi = api;
						plotReady = true;
					}}
					onChartDestroy={() => {
						chartApi = null;
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
				onReady={(api) => {
					chartApi = api;
					plotReady = true;
				}}
				onChartDestroy={() => {
					chartApi = null;
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
