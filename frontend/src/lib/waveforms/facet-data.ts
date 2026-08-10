/**
 * Per-frame data builder for uPlot mode 2 (faceted) live charts.
 *
 * Each device carries its own [xs, ys] pair, so every rendered point is a real
 * measured sample at its real timestamp. The builder pools per-device typed
 * arrays, so the steady-state frame cost is a copy into existing memory rather
 * than fresh allocations.
 */

import type uPlot from 'uplot';
import type { PlottableSample } from '$lib/types/api';

/** uPlot mode 2 data shape: a null x placeholder followed by per-series [xs, ys]. */
export type FacetedData = [null, ...[Float64Array, Float64Array][]];

/**
 * uPlot's typings only describe mode 1 data, so faceted data needs a cast at the
 * call boundary.
 */
export function toAlignedData(data: FacetedData): uPlot.AlignedData {
  return data as unknown as uPlot.AlignedData;
}

/**
 * A device's slice of its sample buffer for the current frame: series data
 * index i corresponds to samples[startIdx + i]. Holds the buffer array itself
 * because trimming replaces the array in the state map.
 */
export interface DeviceWindow<T extends PlottableSample> {
  samples: T[];
  startIdx: number;
}

export interface BuildFacetDataOptions<T extends PlottableSample> {
  samples: Map<string, T[]>;
  deviceOrder: string[];
  getValue: (sample: T) => number;
  sessionStartTime: number;
  timeWindow: { minTime: number; maxTime: number };
  /** Collect verified-sample indices; skip the scan while markers are hidden */
  collectVerified?: boolean;
}

export interface FacetDataResult<T extends PlottableSample> {
  /** [null, [xs, ys], ...] with one facet pair per device, in deviceOrder */
  data: FacetedData;
  /** [deviceIdx] → window into that device's buffer, for tooltip lookups */
  deviceWindows: DeviceWindow<T>[];
  /** [deviceIdx] → per-series indices of samples with verified Polar timestamps */
  verifiedIndices: number[][];
  /** Unpadded y extremes across all devices, or null if no points in the window */
  yRange: [number, number] | null;
}

/**
 * Finds the first index whose relative time is >= minTime.
 * Assumes samples are sorted by global_time.
 */
function lowerBound<T extends PlottableSample>(
  samples: T[],
  sessionStartTime: number,
  minTime: number,
  from: number
): number {
  let left = from;
  let right = samples.length;
  while (left < right) {
    const mid = (left + right) >> 1;
    if (samples[mid].global_time - sessionStartTime < minTime) {
      left = mid + 1;
    } else {
      right = mid;
    }
  }
  return left;
}

/**
 * Finds the first index whose relative time is > maxTime.
 * Assumes samples are sorted by global_time.
 */
function upperBound<T extends PlottableSample>(
  samples: T[],
  sessionStartTime: number,
  maxTime: number,
  from: number
): number {
  let left = from;
  let right = samples.length;
  while (left < right) {
    const mid = (left + right) >> 1;
    if (samples[mid].global_time - sessionStartTime <= maxTime) {
      left = mid + 1;
    } else {
      right = mid;
    }
  }
  return left;
}

/**
 * Builds one frame of faceted plot data: per device, the samples inside the
 * time window, as they were measured. A device with no samples in the window
 * gets empty facet arrays and simply draws nothing.
 *
 * Keep one builder per chart: the returned facet arrays are subarray views
 * into the builder's pool and are overwritten by the next build() call.
 */
export class FacetDataBuilder<T extends PlottableSample> {
  private pool = new Map<string, { xs: Float64Array; ys: Float64Array }>();

  private buffersFor(deviceId: string, count: number): { xs: Float64Array; ys: Float64Array } {
    let buffers = this.pool.get(deviceId);
    if (!buffers || buffers.xs.length < count) {
      const capacity = Math.ceil(count * 1.5) + 64;
      buffers = { xs: new Float64Array(capacity), ys: new Float64Array(capacity) };
      this.pool.set(deviceId, buffers);
    }
    return buffers;
  }

  build(opts: BuildFacetDataOptions<T>): FacetDataResult<T> {
    const {
      samples,
      deviceOrder,
      getValue,
      sessionStartTime,
      timeWindow,
      collectVerified = false
    } = opts;

    const data: FacetedData = [null];
    const deviceWindows: DeviceWindow<T>[] = [];
    const verifiedIndices: number[][] = [];
    let yMin = Infinity;
    let yMax = -Infinity;

    for (const deviceId of deviceOrder) {
      const deviceSamples = samples.get(deviceId) ?? [];

      const startIdx = lowerBound(deviceSamples, sessionStartTime, timeWindow.minTime, 0);
      const endIdx = upperBound(deviceSamples, sessionStartTime, timeWindow.maxTime, startIdx);
      const count = endIdx - startIdx;

      const { xs, ys } = this.buffersFor(deviceId, count);
      const verified: number[] = [];

      for (let i = 0; i < count; i++) {
        const sample = deviceSamples[startIdx + i];
        xs[i] = sample.global_time - sessionStartTime;
        const value = getValue(sample);
        ys[i] = value;
        if (value < yMin) yMin = value;
        if (value > yMax) yMax = value;
        if (collectVerified && sample.time_verified) verified.push(i);
      }

      data.push([xs.subarray(0, count), ys.subarray(0, count)]);
      deviceWindows.push({ samples: deviceSamples, startIdx });
      verifiedIndices.push(verified);
    }

    return {
      data,
      deviceWindows,
      verifiedIndices,
      yRange: yMin <= yMax ? [yMin, yMax] : null
    };
  }
}
