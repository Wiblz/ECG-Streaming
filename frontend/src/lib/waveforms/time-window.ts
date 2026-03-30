/**
 * Time window management for live waveforms.
 * Handles sliding time windows for real-time data visualization.
 */

export interface TimeWindow {
  minTime: number;
  maxTime: number;
}

/**
 * Calculates the current time window for a sliding live view.
 *
 * @param currentTime - Current playback time (relative to session start)
 * @param windowDuration - Duration of the window in seconds
 * @returns Time window, or null if currentTime is null
 */
export function calculateTimeWindow(
  currentTime: number | null,
  windowDuration: number
): TimeWindow | null {
  if (currentTime === null) {
    return null;
  }

  return {
    minTime: currentTime - windowDuration,
    maxTime: currentTime
  };
}

/**
 * Checks if a timestamp falls within a time window.
 */
export function isInTimeWindow(timestamp: number, window: TimeWindow): boolean {
  return timestamp >= window.minTime && timestamp <= window.maxTime;
}
