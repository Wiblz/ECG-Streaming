<script lang="ts" generics="T extends PlottableSample">
  import { onDestroy, onMount, untrack } from 'svelte';
  import type uPlot from 'uplot';
  import type { AlignedData } from 'uplot';
  import { browser } from '$app/environment';
  import type { PlottableSample } from '$lib/types/api';
  import { isPaused } from '$lib/state/pause.svelte';
  import { calculateTimeWindow } from '$lib/waveforms/time-window';
  import { FacetDataBuilder, toAlignedData, type DeviceWindow } from '$lib/waveforms/facet-data';
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
    deviceNicknames
  }: Props = $props();

  let createFacetDeviceSeries = $state<
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
  let plotData: AlignedData = $state(toAlignedData([null]));
  let plotOptions: WaveformPlotOptions | null = $state(null);
  let plotReady = $state(false);
  let chartApi: WaveformPlotApi | null = null;
  let animationFrameId: number | null = null;
  let lastUpdateTime = 0;

  let deviceOrder: string[] = $state([]);

  // Per-frame lookups read from uPlot callbacks. Deliberately non-reactive:
  // rewriting them every frame must not retrigger the options effect.
  let deviceWindows: DeviceWindow<T>[] = [];
  // eslint-disable-next-line svelte/prefer-svelte-reactivity
  let verifiedIndicesByDevice = new Map<string, number[]>();

  const facetBuilder = new FacetDataBuilder<T>();

  // Sorted device list, recomputed only when a device appears (keys are never removed)
  let cachedDevices: string[] = [];

  /**
   * Assign deviceOrder only when the device list actually changed.
   *
   * The device list is recomputed every animation frame as a fresh array.
   * Assigning it unconditionally dirties the $state on every frame, which
   * retriggers the rebuildPlotOptions effect and recreates the uPlot instance
   * ~30x/second, so the chart never renders past its first frames.
   */
  function setDeviceOrder(next: string[]): void {
    if (deviceOrder.length === next.length && deviceOrder.every((d, i) => d === next[i])) {
      return;
    }
    deviceOrder = next;
  }

  import { ConnectionState } from '$lib/state/websocket.svelte';

  // Time window configuration
  const WINDOW_DURATION = 7.5; // seconds to display
  const UPDATE_INTERVAL_MS = 33; // update every 33ms (30 FPS)
  const CURSOR_MAX_DISTANCE = 0.25; // seconds; beyond this a series reports no sample

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
    if (!shouldShowPlot || !createFacetDeviceSeries || !createAxes) {
      return;
    }

    // Only initialize if not already done
    if (plotOptions !== null) {
      return;
    }

    // Use untrack to read samples once without subscribing to future updates
    untrack(() => {
      const { data, devices } = refreshFrameData(getCurrentTimeWindow());
      if (devices.length > 0) {
        // Set initial data and options to make plot render
        plotData = data;
        rebuildPlotOptions(devices);
      }
    });
  });

  // Rebuild plot options when device order changes
  $effect(() => {
    if (!createFacetDeviceSeries || !createAxes) return;
    if (deviceOrder.length === 0) return;
    rebuildPlotOptions(deviceOrder);
  });

  /**
   * Republish plotData for the current device list.
   *
   * A device joining or leaving recreates the chart, and mode 2 throws at
   * construction unless every series has a matching facet pair.
   */
  $effect(() => {
    if (deviceOrder.length === 0) return;
    untrack(() => {
      plotData = refreshFrameData(getCurrentTimeWindow()).data;
    });
  });

  // X-axis range controlled by function (prevents setData from resetting scale)
  let xAxisRange: [number, number] = [0, WINDOW_DURATION];

  // Y-axis range read by the scale's range function. Updated from the copy pass
  // in build(), so uPlot's own per-redraw min/max scan is skipped (series auto: false).
  let yAxisRange: [number, number] = [0, 1];

  // Use shared session start time for synchronization across all waveforms
  const sessionStartTime = $derived(getSessionStartTime());

  // Get current time window based on wall-clock progression (shared across all waveforms)
  function getCurrentTimeWindow(): { minTime: number; maxTime: number } | null {
    return calculateTimeWindow(getCurrentPlaybackTime(), WINDOW_DURATION);
  }

  const EMPTY_FACET = new Float64Array(0);

  /**
   * Rebuild this frame's faceted plot data and the per-frame lookups that uPlot
   * callbacks read (tooltip window offsets, verified-point indices).
   */
  function refreshFrameData(timeWindow: { minTime: number; maxTime: number } | null): {
    data: AlignedData;
    devices: string[];
  } {
    if (samples.size !== cachedDevices.length) {
      cachedDevices = Array.from(samples.keys()).sort();
    }
    const devices = cachedDevices;

    if (devices.length === 0) {
      setDeviceOrder([]);
      deviceWindows = [];
      verifiedIndicesByDevice.clear();
      return { data: toAlignedData([null]), devices: [] };
    }

    // Anchor relative time to the first sample seen, shared across all waveforms.
    // The time window is derived from this origin, so it must be set before the
    // window check below or playback never starts.
    let startTime = sessionStartTime;
    if (startTime === null) {
      for (const deviceId of devices) {
        const deviceSamples = samples.get(deviceId)!;
        if (deviceSamples.length > 0) {
          startTime = deviceSamples[0].global_time;
          setSessionStartTime(startTime);
          break;
        }
      }
    }
    if (startTime === null) {
      return { data: toAlignedData([null]), devices: [] };
    }

    // Empty facets still let the chart construct with its real series list,
    // which mode 2 requires
    if (!timeWindow) {
      setDeviceOrder(devices);
      deviceWindows = [];
      verifiedIndicesByDevice.clear();
      devices.forEach((deviceId) => verifiedIndicesByDevice.set(deviceId, []));
      return {
        data: toAlignedData([
          null,
          ...devices.map(() => [EMPTY_FACET, EMPTY_FACET] as [Float64Array, Float64Array])
        ]),
        devices
      };
    }

    const frame = facetBuilder.build({
      samples,
      deviceOrder: devices,
      getValue,
      sessionStartTime: startTime,
      timeWindow,
      collectVerified: showVerifiedPoints
    });

    setDeviceOrder(devices);
    deviceWindows = frame.deviceWindows;
    verifiedIndicesByDevice.clear();
    devices.forEach((deviceId, idx) => {
      verifiedIndicesByDevice.set(deviceId, frame.verifiedIndices[idx]);
    });

    if (frame.yRange) {
      const [yMin, yMax] = frame.yRange;
      const pad = (yMax - yMin) * 0.1 || 1;
      yAxisRange[0] = yMin - pad;
      yAxisRange[1] = yMax + pad;
    }

    return { data: toAlignedData(frame.data), devices };
  }

  /**
   * Resolve the sample each series should report under the cursor.
   *
   * uPlot's default dataIdx is mode 1 only; in mode 2 it receives no usable
   * cursor index or x value, so both are derived here.
   */
  function facetDataIdx(u: uPlot, seriesIdx: number): number | null {
    if (seriesIdx === 0) return null;

    const left = u.cursor.left;
    if (left === undefined || left === null || left < 0) return null;

    const xs = (u.data[seriesIdx] as unknown as [number[], number[]] | undefined)?.[0];
    if (!xs || xs.length === 0) return null;

    const xVal = u.posToVal(left, 'x');

    let lo = 0;
    let hi = xs.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (xs[mid] < xVal) {
        lo = mid + 1;
      } else {
        hi = mid;
      }
    }

    // Compare against the previous point too - the search lands on the first
    // x >= xVal, which may be the farther of the two neighbours
    let nearest = lo;
    if (lo > 0 && Math.abs(xs[lo - 1] - xVal) <= Math.abs(xs[lo] - xVal)) {
      nearest = lo - 1;
    }

    // Ignore samples too far from the cursor to be what the user is pointing at
    return Math.abs(xs[nearest] - xVal) > CURSOR_MAX_DISTANCE ? null : nearest;
  }

  function rebuildPlotOptions(devices: string[]) {
    if (!createFacetDeviceSeries || !createAxes) {
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
        x: { time: false, auto: false, range: () => xAxisRange },
        y: { auto: false, range: () => yAxisRange }
      },
      // uPlot's single-value live legend misreads faceted series; the tooltip shows values
      legend: { show: true, live: false },
      mode: 2,
      cursor: {
        dataIdx: facetDataIdx,
        drag: { x: false, y: false, setScale: false }
      },
      createDeviceSeries: createFacetDeviceSeries,
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

    const { data, devices } = refreshFrameData(timeWindow);

    // Chart re-creation reads this closure once, at construction
    xAxisRange[0] = timeWindow.minTime;
    xAxisRange[1] = timeWindow.maxTime;

    if (devices.length === 0) {
      plotOptions = null;
    } else if (chartApi) {
      // Only mode 1 re-invokes a non-auto scale's range fn on setData, so both
      // scale windows must be pushed explicitly here
      chartApi.setFrame(data, {
        x: { min: timeWindow.minTime, max: timeWindow.maxTime },
        y: { min: yAxisRange[0], max: yAxisRange[1] }
      });
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
    createFacetDeviceSeries = utilsModule.createFacetDeviceSeries;
    createAxes = utilsModule.createAxes;
    tooltipsPlugin = tooltipsModule.tooltipsPlugin({
      showSeriesPoints: true,
      showCursorPosition: false,
      faceted: true,
      formatValue: (xVal, yVal, seriesIdx, dataIdx) => {
        const win = deviceWindows[seriesIdx - 1];
        const sample = win?.samples[win.startIdx + dataIdx];
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
