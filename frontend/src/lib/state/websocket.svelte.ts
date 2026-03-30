export const ConnectionState = {
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  ERROR: 'error'
} as const;

export type ConnectionStateType = (typeof ConnectionState)[keyof typeof ConnectionState];

// ECG WebSocket reactive state
let _state = $state<ConnectionStateType>(ConnectionState.DISCONNECTED);
let _error = $state<string | null>(null);

// Accelerometer WebSocket reactive state
let _accState = $state<ConnectionStateType>(ConnectionState.DISCONNECTED);
let _accError = $state<string | null>(null);

// ECG WebSocket getters and setters
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

// Accelerometer WebSocket getters and setters
export function getAccWsState() {
  return _accState;
}

export function setAccWsState(newState: ConnectionStateType) {
  _accState = newState;
}

export function getAccWsError() {
  return _accError;
}

export function setAccWsError(err: string | null) {
  _accError = err;
}
