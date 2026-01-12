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
	console.log(`[pause] Streaming ${paused ? 'PAUSED' : 'RESUMED'}`);
}

export function togglePause(): boolean {
	_paused = !_paused;
	console.log(`[pause] Streaming ${_paused ? 'PAUSED' : 'RESUMED'}`);
	return _paused;
}
