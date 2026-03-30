import type { PlottableSample } from '$lib/types/api';

/**
 * Cache structure for aligned waveform data.
 * Stores aligned data to avoid re-aligning on every animation frame.
 */
export interface AlignmentCache<T extends PlottableSample> {
  deviceOrder: string[];
  deviceSampleCounts: Map<string, number>;
  timestamps: number[];
  seriesData: (number | null)[][];
  samplesByDevice: (T | null)[][];
  sessionStartTime: number;
  baseDeviceId: string;
  timestampRange: { min: number; max: number };
}

/**
 * Checks if the alignment cache is still valid for the current samples.
 * Cache is invalid if:
 * - Device list changed
 * - Session start time changed
 */
export function isCacheValid<T extends PlottableSample>(
  cache: AlignmentCache<T> | null,
  sampleMap: Map<string, T[]>,
  sessionStartTime: number | null
): boolean {
  if (!cache) return false;

  const devices = Array.from(sampleMap.keys()).sort();

  // Check if session start time changed
  if (sessionStartTime !== null && cache.sessionStartTime !== sessionStartTime) {
    return false;
  }

  // Check if device list changed
  if (devices.length !== cache.deviceOrder.length) {
    return false;
  }
  if (!devices.every((d, idx) => cache.deviceOrder[idx] === d)) {
    return false;
  }

  return true;
}

/**
 * Finds the device with the most samples to use as the time base for alignment.
 */
export function findBaseDevice<T extends PlottableSample>(
  sampleMap: Map<string, T[]>
): string | null {
  const devices = Array.from(sampleMap.keys());
  if (devices.length === 0) return null;

  let maxDevice = devices[0];
  let maxLength = 0;

  for (const deviceId of devices) {
    const len = sampleMap.get(deviceId)!.length;
    if (len > maxLength) {
      maxLength = len;
      maxDevice = deviceId;
    }
  }

  return maxDevice;
}
