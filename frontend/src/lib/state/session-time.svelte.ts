/**
 * Shared session start time for synchronizing multiple waveform displays.
 *
 * This ensures that ECG and accelerometer waveforms use the same time origin,
 * allowing them to be visually aligned and synchronized.
 */

let _sessionStartTime = $state<number | null>(null);
let _wallClockStartTime = $state<number | null>(null); // Wall-clock time when session started

export function getSessionStartTime(): number | null {
  return _sessionStartTime;
}

export function setSessionStartTime(time: number): void {
  if (_sessionStartTime === null) {
    _sessionStartTime = time;
    _wallClockStartTime = Date.now() / 1000; // Record wall-clock time
  }
}

/**
 * Get the current playback time based on wall-clock progression
 */
export function getCurrentPlaybackTime(): number | null {
  if (_sessionStartTime === null || _wallClockStartTime === null) {
    return null;
  }

  return Date.now() / 1000 - _wallClockStartTime;
}
