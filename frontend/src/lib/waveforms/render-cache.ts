import type uPlot from 'uplot';
import type { PlottableSample } from '$lib/types/api';

/**
 * RenderCache maintains a windowed view of aligned data with array reuse.
 * Instead of creating new arrays on every update, it mutates existing arrays in-place.
 * This eliminates garbage collection pressure from high-frequency updates.
 */
export class RenderCache<T extends PlottableSample> {
  // Reused array instances - NEVER replaced, only mutated
  timestamps: number[] = [];
  seriesData: (number | null)[][] = [];
  samplesByDevice: (T | null)[][] = [];

  deviceOrder: string[] = [];
  currentWindow: { minTime: number; maxTime: number } | null = null;

  /**
   * Updates the render cache with data from the alignment cache,
   * filtered to the current time window. Reuses existing arrays.
   */
  updateFromAlignmentCache(
    alignmentTimestamps: number[],
    alignmentSeriesData: (number | null)[][],
    alignmentSamplesByDevice: (T | null)[][],
    deviceOrder: string[],
    timeWindow: { minTime: number; maxTime: number }
  ): boolean {
    // Find window bounds using binary search
    const startIdx = this.binarySearchStart(alignmentTimestamps, timeWindow.minTime);
    const endIdx = this.binarySearchEnd(alignmentTimestamps, timeWindow.maxTime, startIdx);

    const newLength = endIdx - startIdx;
    if (newLength === 0) {
      // Empty window - clear arrays
      this.timestamps.length = 0;
      for (const series of this.seriesData) {
        series.length = 0;
      }
      for (const samples of this.samplesByDevice) {
        samples.length = 0;
      }
      return false;
    }

    // Update device order if changed
    if (
      this.deviceOrder.length !== deviceOrder.length ||
      !this.deviceOrder.every((d, i) => d === deviceOrder[i])
    ) {
      this.deviceOrder = [...deviceOrder];

      // Resize series and samples arrays to match device count
      while (this.seriesData.length < deviceOrder.length) {
        this.seriesData.push([]);
      }
      while (this.samplesByDevice.length < deviceOrder.length) {
        this.samplesByDevice.push([]);
      }

      this.seriesData.length = deviceOrder.length;
      this.samplesByDevice.length = deviceOrder.length;
    }

    // Resize timestamps array to match new length
    this.timestamps.length = newLength;

    // Copy timestamps into reused array
    for (let i = 0; i < newLength; i++) {
      this.timestamps[i] = alignmentTimestamps[startIdx + i];
    }

    // Copy each series into reused arrays
    for (let seriesIdx = 0; seriesIdx < deviceOrder.length; seriesIdx++) {
      const targetSeries = this.seriesData[seriesIdx];
      const sourceSeries = alignmentSeriesData[seriesIdx];

      targetSeries.length = newLength;
      for (let i = 0; i < newLength; i++) {
        targetSeries[i] = sourceSeries[startIdx + i];
      }

      // Copy samples
      const targetSamples = this.samplesByDevice[seriesIdx];
      const sourceSamples = alignmentSamplesByDevice[seriesIdx];

      targetSamples.length = newLength;
      for (let i = 0; i < newLength; i++) {
        targetSamples[i] = sourceSamples[startIdx + i];
      }
    }

    this.currentWindow = timeWindow;
    return true;
  }

  /**
   * Get uPlot-compatible data structure.
   * Returns references to the internal arrays (not copies).
   */
  toUPlotData(): uPlot.AlignedData {
    return [this.timestamps, ...this.seriesData];
  }

  /**
   * Binary search for first index >= minTime
   */
  private binarySearchStart(timestamps: number[], minTime: number): number {
    let left = 0;
    let right = timestamps.length;

    while (left < right) {
      const mid = Math.floor((left + right) / 2);
      if (timestamps[mid] < minTime) {
        left = mid + 1;
      } else {
        right = mid;
      }
    }

    return left;
  }

  /**
   * Binary search for first index > maxTime (exclusive end)
   */
  private binarySearchEnd(timestamps: number[], maxTime: number, startIdx: number): number {
    let left = startIdx;
    let right = timestamps.length;

    while (left < right) {
      const mid = Math.floor((left + right) / 2);
      if (timestamps[mid] <= maxTime) {
        left = mid + 1;
      } else {
        right = mid;
      }
    }

    return left;
  }
}
