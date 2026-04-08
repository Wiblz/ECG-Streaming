/**
 * Global pause state for live data streaming.
 * When paused, WebSocket messages are ignored and plots freeze.
 */

let _paused = $state(false);

export function isPaused(): boolean {
  return _paused;
}

export function setPaused(paused: boolean): void {
  _paused = paused;
}

export function togglePause(): boolean {
  _paused = !_paused;
  return _paused;
}
