/**
 * Shared session start time for synchronizing multiple waveform displays.
 *
 * This ensures that ECG and accelerometer waveforms use the same time origin,
 * allowing them to be visually aligned and synchronized.
 */

let _sessionStartTime = $state<number | null>(null)
let _wallClockStartTime = $state<number | null>(null) // Wall-clock time when session started
let _initialOffset = $state<number | null>(null) // Fixed offset between sample time and wall-clock

export function getSessionStartTime(): number | null {
	return _sessionStartTime
}

export function setSessionStartTime(time: number): void {
	if (_sessionStartTime === null) {
		_sessionStartTime = time
		_wallClockStartTime = Date.now() / 1000 // Record wall-clock time
		_initialOffset = _wallClockStartTime - time // Save the offset
		console.log(
			'[session-time] Session start - sample time:',
			time,
			'wall-clock:',
			_wallClockStartTime,
			'fixed offset:',
			_initialOffset
		)
	}
}

export function resetSessionStartTime(): void {
	_sessionStartTime = null
	_wallClockStartTime = null
	_initialOffset = null
	console.log('[session-time] Session start time reset')
}

/**
 * Get the current playback time based on wall-clock progression
 * Returns time in SAMPLE time space by subtracting the fixed initial offset
 * This ensures window and samples use the same time base
 */
export function getCurrentPlaybackTime(): number | null {
	if (_sessionStartTime === null || _wallClockStartTime === null || _initialOffset === null) {
		return null
	}

	// Calculate current time in wall-clock space
	const now = Date.now() / 1000
	const elapsedWallClock = now - _wallClockStartTime

	// Convert to sample time space by subtracting the fixed offset
	// This keeps the relationship between window and samples stable
	return elapsedWallClock
}
