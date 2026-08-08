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
  import Button from '../ui/Button.svelte';
  import Card from '../layout/Card.svelte';
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
  let tooltipsPlugin: ReturnType<typeof import('$lib/utils/uplot-tooltips').tooltipsPlugin> | null =
    null;
  // Reuse array references to avoid forcing uPlot to redraw from scratch
  let plotData: AlignedData = $state([[], []]);
  let plotOptions: WaveformPlotOptions | null = $state(null);
  let plotReady = $state(false);
  let chartApi: WaveformPlotApi | null = null;
  let animationFrameId: number | null = null;
  let lastUpdateTime = 0;

  let deviceOrder: string[] = $state([]);
  let samplesByDevice: (T | null)[][] = $state([]);
  // eslint-disable-next-line svelte/prefer-svelte-reactivity
  let verifiedIndicesByDevice = new Map<string, number[]>();

  /**
   * Assign deviceOrder only when the device list actually changed.
   *
   * prepareChartData runs every animation frame and produces a fresh array each
   * time. Assigning it unconditionally dirties the $state on every frame, which
   * retriggers the rebuildPlotOptions effect and recreates the uPlot instance
   * ~30x/second, so the chart never renders past its first frames.
   */
  function setDeviceOrder(next: string[]): void {
    if (deviceOrder.length === next.length && deviceOrder.every((d, i) => d === next[i])) {
      return;
    }
    deviceOrder = next;
  }

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
      return;
    }

    const now = Date.now() / 1000;
    const STALE_THRESHOLD = 30;

    let hasFreshData = false;
    for (const deviceSamples of samples.values()) {
      if (deviceSamples.length === 0) continue;
      const newestSample = deviceSamples[deviceSamples.length - 1];
      if (now - newestSample.global_time < STALE_THRESHOLD) {
        hasFreshData = true;
        break;
      }
    }

    samplesAreFresh = hasFreshData;
    isStreaming = wsState === ConnectionState.CONNECTED && hasFreshData && !isPaused();
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

  // Get current time window based on wall-clock progression (shared across all waveforms)
  function getCurrentTimeWindow(): { minTime: number; maxTime: number } | null {
    return calculateTimeWindow(getCurrentPlaybackTime(), WINDOW_DURATION);
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
      setDeviceOrder([]);
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

      // Filter samples by time window if provided using binary search
      let filteredSamples = deviceSamples;
      if (timeWindow) {
        // Binary search for start index
        let left = 0;
        let right = deviceSamples.length;
        while (left < right) {
          const mid = Math.floor((left + right) / 2);
          if (deviceSamples[mid].global_time - currentStartTime < timeWindow.minTime) {
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
          if (deviceSamples[mid].global_time - currentStartTime <= timeWindow.maxTime) {
            left = mid + 1;
          } else {
            right = mid;
          }
        }

        filteredSamples = deviceSamples.slice(startIdx, left);
      }

      const timestamps = filteredSamples.map((s) => s.global_time - currentStartTime);
      const values = filteredSamples.map((s) => getValue(s));

      setDeviceOrder(devices);
      const verifiedIndices: number[] = [];
      for (let i = 0; i < filteredSamples.length; i++) {
        if (filteredSamples[i].time_verified) verifiedIndices.push(i);
      }
      samplesByDevice = [filteredSamples];
      verifiedIndicesByDevice.clear();
      verifiedIndicesByDevice.set(devices[0], verifiedIndices);

      return { data: [timestamps, values], devices, samples: filteredSamples };
    }

    // Multiple devices - align by timestamp
    // Check if we can use cached alignment
    const cacheIsValid = isCacheValid(sampleMap);

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
        alignmentCache = null;
      }
    }

    if (!cacheIsValid || !alignmentCache) {
      // Need to rebuild alignment cache
      // Find the device with the most samples to use as time base
      const maxDevice = findBaseDevice(sampleMap);
      if (!maxDevice) {
        alignmentCache = null;
        setDeviceOrder([]);
        samplesByDevice = [];
        verifiedIndicesByDevice.clear();
        return { data: [[], []], devices: [], samples: [] };
      }

      const baseSamples = sampleMap.get(maxDevice)!;
      if (baseSamples.length === 0) {
        alignmentCache = null;
        setDeviceOrder([]);
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
          ? { min: aligned.timestamps[0], max: aligned.timestamps[aligned.timestamps.length - 1] }
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
    }

    // Now filter by time window if provided
    const cachedTimestamps = alignmentCache!.timestamps;
    const cachedSeriesData = alignmentCache!.seriesData;
    const cachedBaseSamples = sampleMap.get(alignmentCache!.baseDeviceId) ?? [];
    const cachedSamplesByDevice = alignmentCache!.samplesByDevice;

    if (!timeWindow) {
      setDeviceOrder(alignmentCache!.deviceOrder);
      samplesByDevice = cachedSamplesByDevice;
      // verifiedIndicesByDevice already set when cache was built

      return { data: [cachedTimestamps, ...cachedSeriesData], devices, samples: cachedBaseSamples };
    }

    // Use render cache to filter by time window without creating new arrays
    renderCache.updateFromAlignmentCache(
      cachedTimestamps,
      cachedSeriesData,
      cachedSamplesByDevice,
      alignmentCache!.deviceOrder,
      timeWindow
    );

    setDeviceOrder(alignmentCache!.deviceOrder);
    samplesByDevice = renderCache.samplesByDevice;

    // Don't extract verified indices every frame - they don't change during streaming
    // and extracting them creates new arrays. Only extract when cache is rebuilt.

    return { data: renderCache.toUPlotData(), devices, samples: [] };
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
        x: { time: false, auto: false, range: () => xAxisRange }
      },
      legend: { show: true },
      createDeviceSeries,
      createAxes
    });
  }

  // Update function for time-based chart updates using requestAnimationFrame
  function updateChart(currentTime: number) {
    // Poll streaming status instead of using reactive derived
    pollStreamingStatus();

    if (!plotReady || !isStreaming || !samplesAreFresh) {
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

    // Call uPlot API directly instead of using Svelte reactivity
    if (chartApi) {
      chartApi.setData(data);
    }

    if (devices.length === 0) {
      plotOptions = null;
    }

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

    themeObserver = new MutationObserver(() => rebuildPlotOptions(deviceOrder));
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme']
    });
  });

  let themeObserver: MutationObserver | null = null;

  onDestroy(() => {
    if (animationFrameId !== null) {
      cancelAnimationFrame(animationFrameId);
    }
    if (statusInterval !== null) {
      clearInterval(statusInterval);
    }
    themeObserver?.disconnect();
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
        <div class="flex items-center gap-2 text-xs text-text-secondary">
          <div class="w-2 h-2 bg-status-success-fg rounded-full animate-pulse"></div>
          <span>Streaming</span>
        </div>
      {:else}
        <div class="flex items-center gap-2 text-xs text-text-secondary">
          <div class="w-2 h-2 bg-status-neutral-fg rounded-full"></div>
          <span>No data</span>
        </div>
      {/if}
    {/snippet}

    <div class="border border-border rounded-lg overflow-hidden">
      {#if shouldShowPlot}
        <WaveformPlot
          data={plotData}
          options={plotOptions}
          plotClass="w-full"
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
        <div class="bg-surface-muted p-12 text-center">
          <p class="text-text-secondary">{emptyMessage}</p>
        </div>
      {/if}
    </div>
  </Card>
{:else}
  <div class="border border-border rounded-lg overflow-hidden">
    {#if shouldShowPlot}
      <WaveformPlot
        data={plotData}
        options={plotOptions}
        plotClass="w-full"
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
      <div class="bg-surface-muted p-12 text-center">
        <p class="text-text-secondary">{emptyMessage}</p>
      </div>
    {/if}
  </div>
{/if}
