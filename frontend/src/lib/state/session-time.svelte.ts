/**
 * Shared session start time for synchronizing multiple waveform displays.
 *
 * This ensures that ECG and accelerometer waveforms use the same time origin,
 * allowing them to be visually aligned and synchronized.
 */

let _sessionStartTime = $state<number | null>(null)

export function getSessionStartTime(): number | null {
	return _sessionStartTime
}

export function setSessionStartTime(time: number): void {
	if (_sessionStartTime === null) {
		_sessionStartTime = time
		console.log('[session-time] Session start time set to:', time)
	}
}

export function resetSessionStartTime(): void {
	_sessionStartTime = null
	console.log('[session-time] Session start time reset')
}
