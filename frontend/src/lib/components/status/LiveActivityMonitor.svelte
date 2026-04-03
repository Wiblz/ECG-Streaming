<script lang="ts" generics="T extends PlottableSample">
  import { onDestroy, onMount } from 'svelte';
  import type { PlottableSample } from '$lib/types/api';
  import ActivityMonitor from '../session/ActivityMonitor.svelte';
  import { calculateTimeWindow } from '$lib/waveforms/time-window';
  import { getCurrentPlaybackTime, getSessionStartTime } from '$lib/state/session-time.svelte';
  import { filterSingleDeviceSamples } from '$lib/waveforms/chart-data-transformer';
  import { DEVICE_COLORS } from '$lib/utils/uplot';

  interface Props {
    /** Function that returns map of deviceId -> samples for all devices */
    getSamplesMap: () => Map<string, T[]>;
    /** Function to extract value from sample */
    getValue: (sample: T) => number;
    /** Section label e.g. "ECG" / "Accelerometer" */
    label: string;
    /** Optional display name resolver */
    getDeviceNickname?: (id: string) => string;
    /** Monitor height in pixels */
    height?: number;
    /** Per-device colors */
    colors?: string[];
    /** Time window duration in seconds */
    windowDuration?: number;
    /** Width in pixels (determines resolution) */
    width?: number;
    /** Pixels per time bucket (lower = more detail) */
    pixelsPerBucket?: number;
  }

  let {
    getSamplesMap,
    getValue,
    label,
    getDeviceNickname,
    height = 60,
    colors = DEVICE_COLORS,
    windowDuration = 30,
    width = 200,
    pixelsPerBucket = 3
  }: Props = $props();

  interface PerDeviceData {
    deviceId: string;
    label: string;
    color: string;
    samples: Array<{ timestamp: number; value: number }>;
    samplingRate: number | null;
  }

  let perDeviceData = $state<PerDeviceData[]>([]);
  let updateIntervalId: number | null = null;

  function updateDisplayValues() {
    const samplesMap = getSamplesMap();
    const currentTime = getCurrentPlaybackTime();
    const timeWindow = calculateTimeWindow(currentTime, windowDuration);
    const sessionStartTime = getSessionStartTime();

    if (!timeWindow || sessionStartTime === null) {
      perDeviceData = [];
      return;
    }

    const deviceIds = Array.from(samplesMap.keys());
    const updated: PerDeviceData[] = [];

    for (let i = 0; i < deviceIds.length; i++) {
      const deviceId = deviceIds[i];
      const samples = samplesMap.get(deviceId) ?? [];
      const color = colors[i % colors.length];
      const deviceLabel = getDeviceNickname ? getDeviceNickname(deviceId) : deviceId;

      if (samples.length === 0) {
        updated.push({ deviceId, label: deviceLabel, color, samples: [], samplingRate: null });
        continue;
      }

      const result = filterSingleDeviceSamples(samples, sessionStartTime, timeWindow, {
        maxSamples: 500,
        maxSamplesToProcess: 5000
      });

      updated.push({
        deviceId,
        label: deviceLabel,
        color,
        samples: result.samples.map((s) => ({
          timestamp: s.global_time - sessionStartTime,
          value: getValue(s)
        })),
        samplingRate: result.samplingRate
      });
    }

    perDeviceData = updated;
  }

  onMount(() => {
    updateDisplayValues();
    updateIntervalId = window.setInterval(updateDisplayValues, 1000);
  });

  onDestroy(() => {
    if (updateIntervalId !== null) {
      clearInterval(updateIntervalId);
    }
  });
</script>

{#each perDeviceData as device (device.deviceId)}
  <ActivityMonitor
    samples={device.samples}
    label={device.label}
    color={device.color}
    {height}
    {width}
    {pixelsPerBucket}
    samplingRate={device.samplingRate}
  />
{:else}
  <ActivityMonitor samples={[]} {label} {height} {width} {pixelsPerBucket} />
{/each}
