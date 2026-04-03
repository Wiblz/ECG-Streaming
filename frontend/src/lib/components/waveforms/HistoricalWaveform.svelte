<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';
  import type uPlot from 'uplot';
  import { browser } from '$app/environment';
  import { api } from '$lib/api/client';
  import type { Session, SessionSample } from '$lib/types/api';
  import { flattenGroupedSamples } from '$lib/utils/samples';

  let uPlotLib = $state<typeof uPlot | null>(null);
  let createDeviceSeries:
    | ((
        deviceIds: string[],
        getVerifiedIndices?: () => number[],
        deviceNicknames?: Map<string, string>
      ) => uPlot.Series[])
    | null = null;
  let createAxes: (() => uPlot.Axis[]) | null = null;
  let tooltipsPlugin: ReturnType<typeof import('$lib/utils/uplot-tooltips').tooltipsPlugin> | null =
    null;

  interface Props {
    session: Session;
    loading?: boolean;
    showVerifiedPoints?: boolean;
    deviceNicknames?: Map<string, string>;
    timeSyncEnabled?: boolean;
    sharedTimeWindow?: { minTime: number; maxTime: number } | null;
    onTimeWindowChange?: (window: { minTime: number; maxTime: number }) => void;
  }

  let {
    session,
    loading = false,
    showVerifiedPoints = false,
    deviceNicknames,
    timeSyncEnabled = false,
    sharedTimeWindow = null,
    onTimeWindowChange
  }: Props = $props();

  let plotContainer: HTMLDivElement;
  let chart: uPlot | null = null;
  let loadedSamples: SessionSample[] = $state([]);
  let isLoadingData = $state(false);

  // Pre-computed indices of verified samples for efficient filtering
  let verifiedIndices: number[] = [];

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
      const response = await api.getSessionSamples(session.id, {
        start_time: startTime,
        end_time: endTime
      });

      // Flatten grouped data back into samples array with device_id
      const samples = flattenGroupedSamples<SessionSample>(response.devices);

      console.log(`[Waveform] Loaded ${samples.length} samples`);
      loadedSamples = samples;
      loadedTimeRange = { start: startTime, end: endTime };

      // Update chart with new data
      if (chart) {
        // Save current viewport
        const xScale = chart.scales.x;
        const currentMin = xScale?.min;
        const currentMax = xScale?.max;

        // Prepare and set new data
        const chartData = prepareChartData(loadedSamples);

        // Set programmatic flag to prevent hook from triggering
        programmaticUpdate = true;

        const chartInstance = chart; // Capture for closure

        // Batch the data update and scale restoration together
        chartInstance.batch(() => {
          // Pass false to prevent triggering hooks
          chartInstance.setData(chartData.data, false);

          // Restore viewport if we had one
          if (currentMin !== undefined && currentMax !== undefined) {
            chartInstance.setScale('x', { min: currentMin, max: currentMax });
          }
        });

        // Reset flag after next tick to ensure all updates are processed
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
  const prepareChartData = (
    samples: SessionSample[]
  ): { data: uPlot.AlignedData; devices: string[]; sortedSamples: SessionSample[] } => {
    if (samples.length === 0) {
      return { data: [[], []], devices: [], sortedSamples: [] };
    }

    const devices = [...new Set(samples.map((s) => s.device_id))];

    if (devices.length === 1) {
      // Single device - simple case
      const sorted = [...samples].sort((a, b) => a.global_time - b.global_time);
      // Convert to relative time (seconds from session start)
      const timestamps = sorted.map((s) => s.global_time - session.start_time);
      const values = sorted.map((s) => s.raw_value);

      return {
        data: [timestamps, values] as uPlot.AlignedData,
        devices,
        sortedSamples: sorted
      };
    }

    // Multiple devices
    const byDevice = new SvelteMap<string, SessionSample[]>();
    for (const sample of samples) {
      if (!byDevice.has(sample.device_id)) {
        byDevice.set(sample.device_id, []);
      }
      byDevice.get(sample.device_id)!.push(sample);
    }

    // Sort each device's samples
    for (const [deviceId, deviceSamples] of byDevice.entries()) {
      deviceSamples.sort((a, b) => a.global_time - b.global_time);
      byDevice.set(deviceId, deviceSamples);
    }

    // Use first device's timestamps as x-axis (relative time)
    const firstDevice = byDevice.values().next().value;
    if (!firstDevice) {
      return { data: [[], []], devices: [], sortedSamples: [] };
    }
    const timestamps = firstDevice.map((s: SessionSample) => s.global_time - session.start_time);

    // Each device gets its own y-values array
    const seriesData = devices.map((deviceId) => {
      const deviceSamples = byDevice.get(deviceId)!;
      return deviceSamples.map((s) => s.raw_value);
    });

    return {
      data: [timestamps, ...seriesData] as uPlot.AlignedData,
      devices,
      sortedSamples: firstDevice
    };
  };

  // Plugin for wheel zoom and middle-click pan (based on uPlot official demo)
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

  const createChart = () => {
    if (!plotContainer || loadedSamples.length === 0) return;

    console.log('[Waveform] Creating chart...');

    const { data, devices, sortedSamples } = prepareChartData(loadedSamples);

    // Pre-compute verified indices for performance
    verifiedIndices = sortedSamples.reduce((acc, sample, i) => {
      if (sample.time_verified) acc.push(i);
      return acc;
    }, [] as number[]);

    if (!createDeviceSeries || !createAxes) return;

    const opts: uPlot.Options = {
      width: plotContainer.clientWidth,
      height: 400,
      series: createDeviceSeries(
        devices,
        showVerifiedPoints ? () => verifiedIndices : undefined,
        deviceNicknames
      ),
      axes: createAxes(),
      scales: {
        x: {
          time: false
        }
      },
      plugins: tooltipsPlugin ? [wheelZoomPlugin(), tooltipsPlugin] : [wheelZoomPlugin()],
      hooks: {
        setScale: [
          (u) => {
            const xScale = u.scales.x;
            if (!xScale || !xScale.min || !xScale.max) return;

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
      }
    };

    if (chart) {
      chart.destroy();
    }

    if (!uPlotLib) return;
    chart = new uPlotLib(opts, data, plotContainer);
    console.log('[Waveform] Chart created');
  };

  // Initialize: load first window of data
  const initialize = async () => {
    if (loading || !session) return;

    const sessionDuration = session.duration_seconds ?? INITIAL_WINDOW_SECONDS;
    const windowSize = Math.min(INITIAL_WINDOW_SECONDS, sessionDuration);

    // Load data using global time for API
    const globalStart = session.start_time;
    const globalEnd = session.start_time + windowSize;

    await loadTimeRange(globalStart, globalEnd);
    createChart();
  };

  // Initialize once when component is ready
  let initialized = false;
  $effect(() => {
    if (!loading && session && !initialized) {
      initialized = true;
      initialize();
    }
  });

  // Sync with shared time window when time sync is enabled
  $effect(() => {
    if (timeSyncEnabled && sharedTimeWindow && chart) {
      // Set programmatic update flag to prevent triggering setScale hook
      programmaticUpdate = true;
      chart.setScale('x', {
        min: sharedTimeWindow.minTime,
        max: sharedTimeWindow.maxTime
      });
      programmaticUpdate = false;
    }
  });

  // Handle window resize
  const handleResize = () => {
    if (chart && plotContainer) {
      chart.setSize({
        width: plotContainer.clientWidth,
        height: 400
      });
    }
  };

  onMount(async () => {
    if (!browser) return;

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
        const sample = loadedSamples[dataIdx];
        if (sample) {
          const verified = sample.time_verified ? ' ✓' : '';
          return `
						<table style="border-collapse: collapse;">
							<tr><td style="padding: 1px 4px 1px 0;">ID:</td><td style="padding: 1px 0;">${sample.id}</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Value:</td><td style="padding: 1px 0;">${sample.raw_value}</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Time:</td><td style="padding: 1px 0;">${xVal.toFixed(2)}s</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Global:</td><td style="padding: 1px 0;">${sample.global_time.toFixed(3)}s</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Polar:</td><td style="padding: 1px 0;">${(sample.polar_clock_us / 1_000_000).toFixed(3)}s${verified}</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Receiver:</td><td style="padding: 1px 0;">${(sample.receiver_clock_us / 1_000_000).toFixed(3)}s</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Wall:</td><td style="padding: 1px 0;">${(sample.wall_clock_us / 1_000_000).toFixed(3)}s</td></tr>
							<tr><td style="padding: 1px 4px 1px 0;">Conf:</td><td style="padding: 1px 0;">${(sample.confidence * 100).toFixed(0)}%</td></tr>
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

    window.addEventListener('resize', handleResize);

    themeObserver = new MutationObserver(() => createChart());
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme']
    });
  });

  let themeObserver: MutationObserver | null = null;

  onDestroy(() => {
    if (browser) {
      window.removeEventListener('resize', handleResize);
      themeObserver?.disconnect();
    }
    if (chart) {
      chart.destroy();
    }
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
          <div class="text-xs font-mono text-text-secondary">
            Loaded: {currentViewport.sampleCount.toLocaleString()} / {session.ecg_sample_count.toLocaleString()}
            samples
          </div>
          <div class="text-xs text-text-secondary">
            Window: {(currentViewport.end - currentViewport.start).toFixed(1)}s ({currentViewport.start.toFixed(
              1
            )}s - {currentViewport.end.toFixed(1)}s)
          </div>
        {/if}
      </div>
    {/if}
  </div>

  <div class="mb-3 text-xs text-text-secondary">
    Middle-click + drag to pan, scroll wheel to zoom. Data loads dynamically.
  </div>

  {#if loadedSamples.length === 0 && !loading && !isLoadingData}
    <div class="border border-border rounded-lg bg-surface-muted p-12 text-center">
      <p class="text-text-secondary">No data to display</p>
    </div>
  {:else}
    <div bind:this={plotContainer} class="border border-border rounded-lg"></div>
  {/if}
</div>
