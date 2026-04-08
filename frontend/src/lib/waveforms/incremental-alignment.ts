import type { PlottableSample } from '$lib/types/api';
import type { AlignmentCache } from './alignment-cache';
import { buildUnionTimestamps, alignSamplesToTimestamps } from '$lib/utils/samples';
import type { AlignMode } from '$lib/utils/samples';

/**
 * Get the timestamp range (min, max) from current buffer samples.
 */
function getBufferTimestampRange<T extends PlottableSample>(
  sampleMap: Map<string, T[]>,
  sessionStartTime: number
): { min: number; max: number } | null {
  let minTime = Infinity;
  let maxTime = -Infinity;

  for (const deviceSamples of sampleMap.values()) {
    if (deviceSamples.length === 0) continue;

    const firstSampleTime = deviceSamples[0].global_time - sessionStartTime;
    const lastSampleTime = deviceSamples[deviceSamples.length - 1].global_time - sessionStartTime;

    minTime = Math.min(minTime, firstSampleTime);
    maxTime = Math.max(maxTime, lastSampleTime);
  }

  if (!isFinite(minTime) || !isFinite(maxTime)) {
    return null;
  }

  return { min: minTime, max: maxTime };
}

/**
 * Extract new samples that have timestamps > maxTime.
 */
function extractNewSamples<T extends PlottableSample>(
  sampleMap: Map<string, T[]>,
  maxTime: number,
  sessionStartTime: number
): Map<string, T[]> {
  const newSamplesByDevice = new Map<string, T[]>();

  for (const [deviceId, deviceSamples] of sampleMap.entries()) {
    const newSamples = deviceSamples.filter((s) => {
      const relTime = s.global_time - sessionStartTime;
      return relTime > maxTime;
    });

    if (newSamples.length > 0) {
      newSamplesByDevice.set(deviceId, newSamples);
    }
  }

  return newSamplesByDevice;
}

/**
 * Append newly aligned samples to the cache.
 *
 * NOTE: During live streaming, new timestamps are ALWAYS > cache.max,
 * so we can simply append instead of doing a full sorted merge.
 */
function appendNewSamplesToCache<T extends PlottableSample>(
  cache: AlignmentCache<T>,
  newTimestamps: number[],
  newSeriesData: (number | null)[][],
  newSamplesByDevice: (T | null)[][]
): void {
  if (newTimestamps.length === 0) return;

  // Simply append timestamps (they're already > cache.max)
  cache.timestamps.push(...newTimestamps);

  // Append series data and samples for each device
  for (let deviceIdx = 0; deviceIdx < cache.deviceOrder.length; deviceIdx++) {
    cache.seriesData[deviceIdx].push(...newSeriesData[deviceIdx]);
    cache.samplesByDevice[deviceIdx].push(...newSamplesByDevice[deviceIdx]);
  }
}

/**
 * Remove samples that have been dropped from the buffer (timestamp < minTime).
 *
 * Uses splice for in-place removal to avoid creating new arrays.
 */
function removeDroppedSamplesFromCache<T extends PlottableSample>(
  cache: AlignmentCache<T>,
  minTime: number
): void {
  // Find first index to keep (all timestamps >= minTime) using binary search
  let left = 0;
  let right = cache.timestamps.length;

  while (left < right) {
    const mid = Math.floor((left + right) / 2);
    if (cache.timestamps[mid] < minTime) {
      left = mid + 1;
    } else {
      right = mid;
    }
  }

  const firstKeepIdx = left;
  if (firstKeepIdx === 0) return;

  // Remove from timestamps (use slice instead of splice to avoid shifting)
  cache.timestamps = cache.timestamps.slice(firstKeepIdx);

  // Remove from series data and samples (use slice instead of splice)
  for (let deviceIdx = 0; deviceIdx < cache.seriesData.length; deviceIdx++) {
    cache.seriesData[deviceIdx] = cache.seriesData[deviceIdx].slice(firstKeepIdx);
    cache.samplesByDevice[deviceIdx] = cache.samplesByDevice[deviceIdx].slice(firstKeepIdx);
  }
}

/**
 * Incrementally update the alignment cache with new/dropped samples.
 * Returns true if update was successful, false if full rebuild is needed.
 */
export function updateAlignmentCache<T extends PlottableSample>(
  cache: AlignmentCache<T>,
  sampleMap: Map<string, T[]>,
  getValue: (sample: T) => number,
  sessionStartTime: number,
  maxGapSeconds: number,
  alignMode: AlignMode
): boolean {
  // Get current buffer timestamp range
  const bufferRange = getBufferTimestampRange(sampleMap, sessionStartTime);
  if (!bufferRange) {
    // No samples in buffer - can't update
    return false;
  }

  // Check if buffer shrank unexpectedly (need full rebuild)
  if (bufferRange.max < cache.timestampRange.max - 1) {
    return false;
  }

  // Handle new samples (timestamps > cache.max)
  if (bufferRange.max > cache.timestampRange.max) {
    const newSamplesByDevice = extractNewSamples(
      sampleMap,
      cache.timestampRange.max,
      sessionStartTime
    );

    if (newSamplesByDevice.size > 0) {
      // Flatten for timestamp union
      const flatNewSamples = Array.from(newSamplesByDevice.values()).flat();

      // Build union of new timestamps only
      const newTimestamps = buildUnionTimestamps(flatNewSamples, sessionStartTime);

      // Align all devices to these new timestamps (even devices without new samples get nulls)
      const allDevicesSampleMap = new Map<string, T[]>();
      for (const deviceId of cache.deviceOrder) {
        allDevicesSampleMap.set(deviceId, newSamplesByDevice.get(deviceId) ?? []);
      }

      const newAligned = alignSamplesToTimestamps(
        allDevicesSampleMap,
        cache.deviceOrder,
        newTimestamps,
        sessionStartTime,
        getValue,
        maxGapSeconds,
        alignMode
      );

      // Append to cache
      appendNewSamplesToCache(
        cache,
        newAligned.timestamps,
        newAligned.data.slice(1) as (number | null)[][],
        newAligned.samplesByDevice
      );
    }
  }

  // Handle dropped samples (bufferMin > cache.min)
  if (bufferRange.min > cache.timestampRange.min) {
    removeDroppedSamplesFromCache(cache, bufferRange.min);
  }

  // Update cache range and sample counts
  cache.timestampRange = bufferRange;
  for (const [deviceId, deviceSamples] of sampleMap.entries()) {
    cache.deviceSampleCounts.set(deviceId, deviceSamples.length);
  }

  return true;
}
