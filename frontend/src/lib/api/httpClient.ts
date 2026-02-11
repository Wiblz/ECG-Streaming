import type {
	ApiClient,
	BufferStats,
	CollectorsResponse,
	DeviceInfo,
	DeviceStatusResponse,
	Session,
	SessionAccelerometerSamplesResponse,
	SessionSamplesResponse,
	SessionsResponse,
	SyncStats
} from '$lib/types/api';

const envBase = import.meta.env.VITE_AGGREGATOR_HTTP as string | undefined;
const API_BASE =
	envBase ??
	(typeof window !== 'undefined'
		? `${window.location.protocol}//${window.location.hostname}:7999`
		: 'http://localhost:7999');

/**
 * Real HTTP API client implementation
 */
export class HttpClient implements ApiClient {
	async getVersion(): Promise<{ version: string }> {
		const res = await fetch(`${API_BASE}/version`);
		return res.json();
	}

	async getDevices(): Promise<{ devices: DeviceInfo[]; count: number }> {
		const res = await fetch(`${API_BASE}/devices`);
		return res.json();
	}

	async getAllDevices(): Promise<{ devices: DeviceInfo[]; count: number }> {
		const res = await fetch(`${API_BASE}/devices/all`);
		return res.json();
	}

	async getDeviceStatus(): Promise<DeviceStatusResponse> {
		const res = await fetch(`${API_BASE}/devices/status`);
		return res.json();
	}

	async updateDeviceNickname(
		deviceId: string,
		nickname: string | null
	): Promise<{ success: boolean; device_id: string; nickname: string | null }> {
		const res = await fetch(`${API_BASE}/devices/${encodeURIComponent(deviceId)}/nickname`, {
			method: 'PUT',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({ nickname })
		});
		if (!res.ok) {
			throw new Error(`Failed to update nickname: ${res.statusText}`);
		}
		return res.json();
	}

	async getCollectors(): Promise<CollectorsResponse> {
		const res = await fetch(`${API_BASE}/collectors`);
		return res.json();
	}

	async getStats(): Promise<{
		sync: SyncStats;
		grpc: Record<string, unknown>;
		ecg_websocket_connections: number;
		acc_websocket_connections: number;
		ecg_buffer: BufferStats;
		acc_buffer: BufferStats;
	}> {
		const res = await fetch(`${API_BASE}/stats`);
		return res.json();
	}

	async getBufferStats(): Promise<BufferStats> {
		const res = await fetch(`${API_BASE}/buffer/stats`);
		return res.json();
	}

	async getAccelerometerBufferStats(): Promise<BufferStats> {
		const res = await fetch(`${API_BASE}/accelerometer/buffer/stats`);
		return res.json();
	}

	async getSessions(params?: { limit?: number; offset?: number }): Promise<SessionsResponse> {
		const searchParams = new URLSearchParams();
		if (params?.limit) searchParams.set('limit', params.limit.toString());
		if (params?.offset) searchParams.set('offset', params.offset.toString());

		const url = `${API_BASE}/sessions${searchParams.toString() ? `?${searchParams}` : ''}`;
		const res = await fetch(url);
		return res.json();
	}

	async getSession(sessionId: number): Promise<Session> {
		const res = await fetch(`${API_BASE}/sessions/${sessionId}`);
		if (!res.ok) {
			const errorData = await res.json().catch(() => ({ detail: 'Unknown error' }));
			throw new Error(
				errorData.detail || errorData.error || `Failed to fetch session ${sessionId}`
			);
		}
		return res.json();
	}

	async getSessionSamples(
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

	async getSessionAccelerometerSamples(
		sessionId: number,
		params?: {
			device_id?: string;
			start_time?: number;
			end_time?: number;
			limit?: number;
			offset?: number;
		}
	): Promise<SessionAccelerometerSamplesResponse> {
		const searchParams = new URLSearchParams();
		if (params?.device_id) searchParams.set('device_id', params.device_id);
		if (params?.start_time !== undefined)
			searchParams.set('start_time', params.start_time.toString());
		if (params?.end_time !== undefined) searchParams.set('end_time', params.end_time.toString());
		if (params?.limit) searchParams.set('limit', params.limit.toString());
		if (params?.offset) searchParams.set('offset', params.offset.toString());

		const url = `${API_BASE}/sessions/${sessionId}/accelerometer${searchParams.toString() ? `?${searchParams}` : ''}`;
		const res = await fetch(url);
		return res.json();
	}

	async deleteSession(sessionId: number): Promise<{ success: boolean }> {
		const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
			method: 'DELETE'
		});
		return res.json();
	}

	getSessionExportUrl(sessionId: number): string {
		return `${API_BASE}/sessions/${sessionId}/export`;
	}

	async importSession(file: File): Promise<{
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

	async startSession(notes?: string | null): Promise<{
		success: boolean;
		session_id?: number;
		message: string;
		error?: string;
	}> {
		const searchParams = new URLSearchParams();
		if (notes) searchParams.set('notes', notes);

		const url = `${API_BASE}/sessions/start${searchParams.toString() ? `?${searchParams}` : ''}`;
		const res = await fetch(url, {
			method: 'POST'
		});
		return res.json();
	}

	async stopSession(): Promise<{
		success: boolean;
		session_id?: number;
		message: string;
		error?: string;
	}> {
		const res = await fetch(`${API_BASE}/sessions/stop`, {
			method: 'POST'
		});
		return res.json();
	}

	async getActiveSession(): Promise<{
		active: boolean;
		session?: Session;
	}> {
		const res = await fetch(`${API_BASE}/sessions/active`);
		return res.json();
	}
}
