export const ConnectionState = {
	DISCONNECTED: 'disconnected',
	CONNECTING: 'connecting',
	CONNECTED: 'connected',
	ERROR: 'error'
} as const;

export type ConnectionStateType = (typeof ConnectionState)[keyof typeof ConnectionState];

// Reactive state using $state rune
let _state = $state<ConnectionStateType>(ConnectionState.DISCONNECTED);
let _error = $state<string | null>(null);

// Export getters and setters
export function getWsState() {
	return _state;
}

export function setWsState(newState: ConnectionStateType) {
	_state = newState;
}

export function getWsError() {
	return _error;
}

export function setWsError(err: string | null) {
	_error = err;
}
