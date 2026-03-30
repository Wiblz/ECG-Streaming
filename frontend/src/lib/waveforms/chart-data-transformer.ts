import type uPlot from 'uplot';
import type { PlottableSample } from '$lib/types/api';
import type { AlignMode } from '$lib/utils/samples';
import {
  alignSamplesToTimestamps,
  buildUnionTimestamps,
  groupSamplesByDevice
} from '$lib/utils/samples';

export interface ChartDataResult<T extends PlottableSample> {
  /** uPlot-compatible aligned data [timestamps, ...series] */
  data: uPlot.AlignedData;
  /** Ordered list of device IDs */
  deviceOrder: string[];
  /** Array of samples per device [deviceIdx][timestampIdx] → sample or null */
  samplesByDevice: (T | null)[][];
  /** Timestamps array (same as data[0]) */
  timestamps: number[];
}

export interface PrepareChartDataOptions<T extends PlottableSample> {
  /** Map of device ID to samples, or flat array of samples */
  samples: Map<string, T[]> | T[];
  /** Function to extract value from sample for plotting */
  getValue: (sample: T) => number;
  /** Reference time for relative timestamps (e.g., session start time) */
  referenceTime: number;
  /** Maximum gap in seconds before null insertion */
  maxGapSeconds?: number;
  /** Alignment mode */
  alignMode?: AlignMode;
  /** Optional device order to use (for stable ordering) */
  deviceOrder?: string[];
}

/**
 * Prepares sample data for chart rendering by aligning samples across devices.
 * This is the core data transformation logic shared between live and historical views.
 *
 * @returns Aligned data ready for uPlot, plus metadata for tooltips and verified points
 */
export function prepareChartData<T extends PlottableSample>(
  options: PrepareChartDataOptions<T>
): ChartDataResult<T> {
  const {
    samples,
    getValue,
    referenceTime,
    maxGapSeconds = 0.1,
    alignMode = 'linear',
    deviceOrder: preferredDeviceOrder
  } = options;

  // Handle empty data
  const flatSamples = Array.isArray(samples) ? samples : Array.from(samples.values()).flat();
  if (flatSamples.length === 0) {
    return {
      data: [[], []],
      deviceOrder: [],
      samplesByDevice: [],
      timestamps: []
    };
  }

  // Convert to Map<deviceId, samples> if needed
  const samplesByDevice = samples instanceof Map ? samples : groupSamplesByDevice(flatSamples);

  // Determine device order
  const devices = Array.from(samplesByDevice.keys());
  const deviceOrder =
    preferredDeviceOrder && preferredDeviceOrder.length > 0 ? preferredDeviceOrder : devices.sort();

  // Build union of all timestamps
  const timestamps = buildUnionTimestamps(flatSamples, referenceTime);

  // Align samples to timestamps
  const aligned = alignSamplesToTimestamps(
    samplesByDevice,
    deviceOrder,
    timestamps,
    referenceTime,
    getValue,
    maxGapSeconds,
    alignMode
  );

  return {
    data: aligned.data,
    deviceOrder: aligned.deviceOrder,
    samplesByDevice: aligned.samplesByDevice,
    timestamps: aligned.timestamps
  };
}

/**
 * Filters aligned chart data by time window.
 * Used for live waveforms with sliding time windows.
 */
export function filterChartDataByTimeWindow<T extends PlottableSample>(
  chartData: ChartDataResult<T>,
  timeWindow: { minTime: number; maxTime: number }
): ChartDataResult<T> {
  const { data, deviceOrder, samplesByDevice, timestamps } = chartData;

  // Find indices within time window
  const filteredIndices: number[] = [];
  for (let i = 0; i < timestamps.length; i++) {
    const time = timestamps[i];
    if (time >= timeWindow.minTime && time <= timeWindow.maxTime) {
      filteredIndices.push(i);
    }
  }

  // Filter all series data and samples
  const filteredTimestamps = filteredIndices.map((i) => timestamps[i]);
  const filteredSeriesData = data.slice(1).map((series) => filteredIndices.map((i) => series[i]));
  const filteredSamplesByDevice = samplesByDevice.map((deviceSamples) =>
    filteredIndices.map((i) => deviceSamples[i])
  );

  return {
    data: [filteredTimestamps, ...filteredSeriesData],
    deviceOrder,
    samplesByDevice: filteredSamplesByDevice,
    timestamps: filteredTimestamps
  };
}

/**
 * Extracts verified point indices from chart data.
 * Verified points are samples that have direct Polar timestamps.
 */
export function extractVerifiedIndices<T extends PlottableSample>(
  chartData: ChartDataResult<T>
): Map<string, number[]> {
  const { deviceOrder, samplesByDevice } = chartData;
  const verifiedIndicesByDevice = new Map<string, number[]>();

  for (let deviceIdx = 0; deviceIdx < deviceOrder.length; deviceIdx++) {
    const deviceId = deviceOrder[deviceIdx];
    const deviceSamples = samplesByDevice[deviceIdx];
    const indices: number[] = [];

    if (deviceSamples) {
      for (let i = 0; i < deviceSamples.length; i++) {
        const sample = deviceSamples[i];
        if (sample?.time_verified) {
          indices.push(i);
        }
      }
    }

    verifiedIndicesByDevice.set(deviceId, indices);
  }

  return verifiedIndicesByDevice;
}

/**
 * Filters samples for a single device by time window and optionally decimates.
 * Useful for activity monitors and other single-device visualizations.
 *
 * @param samples - Array of samples for single device
 * @param sessionStartTime - Session start time for relative calculations
 * @param timeWindow - Time window to filter by {minTime, maxTime}
 * @param maxSamples - Optional: decimate to this many samples max
 * @returns Filtered (and optionally decimated) samples with metadata
 */
export function filterSingleDeviceSamples<T extends PlottableSample>(
  samples: T[],
  sessionStartTime: number,
  timeWindow: { minTime: number; maxTime: number },
  options?: {
    maxSamples?: number;
    maxSamplesToProcess?: number;
  }
): {
  samples: T[];
  samplingRate: number | null;
} {
  if (!samples || samples.length === 0) {
    return { samples: [], samplingRate: null };
  }

  // Limit processing for performance
  const maxSamplesToProcess = options?.maxSamplesToProcess ?? 5000;
  const startIdx = Math.max(0, samples.length - maxSamplesToProcess);
  const recentSamples = samples.slice(startIdx);

  // Filter samples in time window
  const windowedSamples = recentSamples.filter((s) => {
    const relTime = s.global_time - sessionStartTime;
    return relTime >= timeWindow.minTime && relTime <= timeWindow.maxTime;
  });

  // Calculate sampling rate from windowed samples (before decimation)
  let samplingRate: number | null = null;
  if (windowedSamples.length >= 2) {
    const firstTime = windowedSamples[0].global_time - sessionStartTime;
    const lastTime = windowedSamples[windowedSamples.length - 1].global_time - sessionStartTime;
    const timeSpan = lastTime - firstTime;
    samplingRate = timeSpan > 0 ? Math.round((windowedSamples.length / timeSpan) * 10) / 10 : null;
  }

  // Optionally decimate for rendering performance
  const maxSamples = options?.maxSamples;
  if (maxSamples && windowedSamples.length > maxSamples) {
    const decimationFactor = Math.max(1, Math.floor(windowedSamples.length / maxSamples));
    const decimatedSamples: T[] = [];
    for (let i = 0; i < windowedSamples.length; i += decimationFactor) {
      decimatedSamples.push(windowedSamples[i]);
    }
    return { samples: decimatedSamples, samplingRate };
  }

  return { samples: windowedSamples, samplingRate };
}
