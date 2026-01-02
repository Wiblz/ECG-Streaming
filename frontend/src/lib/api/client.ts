import type {
	DeviceInfo,
	BufferStats,
	Session,
	SessionsResponse,
	SessionSamplesResponse
} from '$lib/types/api';

const envBase = import.meta.env.VITE_AGGREGATOR_HTTP as string | undefined;
const API_BASE =
	envBase ??
	(typeof window !== 'undefined'
		? `${window.location.protocol}//${window.location.hostname}:7999`
		: 'http://localhost:7999');

export async function getDevices(): Promise<{ devices: DeviceInfo[]; count: number }> {
	const res = await fetch(`${API_BASE}/devices`);
	return res.json();
}

export async function getStats(): Promise<{
	sync: unknown;
	websocket_connections: number;
	buffer: BufferStats;
}> {
	const res = await fetch(`${API_BASE}/stats`);
	return res.json();
}

export async function getBufferStats(): Promise<BufferStats> {
	const res = await fetch(`${API_BASE}/buffer/stats`);
	return res.json();
}

// Session API methods

export async function getSessions(params?: {
	limit?: number;
	offset?: number;
}): Promise<SessionsResponse> {
	const searchParams = new URLSearchParams();
	if (params?.limit) searchParams.set('limit', params.limit.toString());
	if (params?.offset) searchParams.set('offset', params.offset.toString());

	const url = `${API_BASE}/sessions${searchParams.toString() ? `?${searchParams}` : ''}`;
	const res = await fetch(url);
	return res.json();
}

export async function getSession(sessionId: number): Promise<Session> {
	const res = await fetch(`${API_BASE}/sessions/${sessionId}`);
	if (!res.ok) {
		throw new Error(`Failed to fetch session ${sessionId}`);
	}
	return res.json();
}

export async function getSessionSamples(
	sessionId: number,
	params?: {
		device_id?: string;
		start_time?: number;
		end_time?: number;
		limit?: number;
		offset?: number;
	}
): Promise<SessionSamplesResponse> {
	const searchParams = new URLSearchParams();
	if (params?.device_id) searchParams.set('device_id', params.device_id);
	if (params?.start_time !== undefined)
		searchParams.set('start_time', params.start_time.toString());
	if (params?.end_time !== undefined) searchParams.set('end_time', params.end_time.toString());
	if (params?.limit) searchParams.set('limit', params.limit.toString());
	if (params?.offset) searchParams.set('offset', params.offset.toString());

	const url = `${API_BASE}/sessions/${sessionId}/samples${searchParams.toString() ? `?${searchParams}` : ''}`;
	const res = await fetch(url);
	return res.json();
}

export async function deleteSession(sessionId: number): Promise<{ success: boolean }> {
	const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
		method: 'DELETE'
	});
	return res.json();
}

export function getSessionExportUrl(sessionId: number): string {
	return `${API_BASE}/sessions/${sessionId}/export`;
}

export async function importSession(file: File): Promise<{
	success: boolean;
	session_id?: number;
	message?: string;
	error?: string;
}> {
	const formData = new FormData();
	formData.append('file', file);

	const res = await fetch(`${API_BASE}/sessions/import`, {
		method: 'POST',
		body: formData
	});
	return res.json();
}
