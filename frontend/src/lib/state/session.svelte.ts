import type { Session } from '$lib/types/api';

// Active session state
let _activeSession = $state<Session | null>(null);
let _isRecording = $state(false);

export function getActiveSession(): Session | null {
  return _activeSession;
}

export function setActiveSession(session: Session | null): void {
  _activeSession = session;
  _isRecording = session !== null && session.end_time === null;
}

export function isRecording(): boolean {
  return _isRecording;
}

export function clearActiveSession(): void {
  _activeSession = null;
  _isRecording = false;
}
