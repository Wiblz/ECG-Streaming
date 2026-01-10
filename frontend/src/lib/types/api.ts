export interface BufferedECGSample {
	device_id: string;
	global_time: number;
	raw_value: number;
	confidence: number;
}

export interface InitMessage {
	type: 'init';
	devices: string[];
	timestamp: number;
}

export interface DataMessage {
	type: 'data';
	samples: BufferedECGSample[];
	timestamp: number;
	count: number;
}

export interface DeviceInfo {
	device_id: string;
	sync_ready: boolean;
	sync?: {
		confidence: number;
		drift_ppm: number;
		sample_count: number;
	};
	// Persistent metadata from database
	nickname?: string | null;
	first_seen?: number;
	last_seen?: number;
	total_samples?: number;
	// Connection status
	collector_id?: string | null;
	status?: 'UNKNOWN' | 'DISCONNECTED' | 'CONNECTING' | 'CONNECTED' | 'STREAMING' | 'ERROR';
	last_update?: number;
	battery_level?: number | null;
	error_message?: string | null;
}

export interface BufferStats {
	total_samples: number;
	duration_seconds: number;
	device_count: number;
	samples_per_device: Record<string, number>;
	oldest_timestamp: number;
	newest_timestamp: number;
	total_processed: number;
	buffer_utilization: number;
}

// Session types

export interface Session {
	id: number;
	start_time: number;
	end_time: number | null;
	device_count: number;
	sample_count: number;
	notes: string | null;
	duration_seconds: number | null;
	devices: string[];
}

export interface SessionSample {
	device_id: string;
	global_time: number;
	raw_value: number;
	confidence: number;
}

export interface SessionsResponse {
	sessions: Session[];
	count: number;
}

export interface SessionSamplesResponse {
	session_id: number;
	samples: SessionSample[];
	count: number;
}

// Device status types

export interface DeviceStatus {
	device_id: string;
	collector_id: string | null;
	collector_name: string | null;
	status: 'UNKNOWN' | 'DISCONNECTED' | 'CONNECTING' | 'CONNECTED' | 'STREAMING' | 'ERROR';
	last_update: number;
	battery_level: number | null;
	error_message: string | null;
}

export interface DeviceStatusResponse {
	devices: DeviceStatus[];
	count: number;
	error?: string;
}

// Collector types

export interface Collector {
	collector_id: string;
	display_name: string;
	device_ids?: string[];
	version: string | null;
	metadata: Record<string, string>;
	connected_at?: number;
	first_seen?: number;
	last_seen?: number;
	last_heartbeat: number | null;
	time_since_heartbeat: number | null;
	health: 'healthy' | 'warning' | 'disconnected';
	samples_sent?: number;
	active_devices?: number;
	connected: boolean;
}

export interface CollectorsResponse {
	collectors: Collector[];
	count: number;
	error?: string;
}

// API Client interface

/**
 * Interface defining all API client methods.
 * Both HttpClient and MockClient must implement this interface.
 */
export interface ApiClient {
	// Device methods
	getDevices(): Promise<{ devices: DeviceInfo[]; count: number }>;
	getAllDevices(): Promise<{ devices: DeviceInfo[]; count: number }>;
	getDeviceStatus(): Promise<DeviceStatusResponse>;
	updateDeviceNickname(
		deviceId: string,
		nickname: string | null
	): Promise<{ success: boolean; device_id: string; nickname: string | null }>;

	// Collector methods
	getCollectors(): Promise<CollectorsResponse>;

	// Stats methods
	getStats(): Promise<{
		sync: unknown;
		websocket_connections: number;
		buffer: BufferStats;
	}>;
	getBufferStats(): Promise<BufferStats>;

	// Session methods
	getSessions(params?: { limit?: number; offset?: number }): Promise<SessionsResponse>;
	getSession(sessionId: number): Promise<Session>;
	getSessionSamples(
		sessionId: number,
		params?: {
			device_id?: string;
			start_time?: number;
			end_time?: number;
			limit?: number;
			offset?: number;
		}
	): Promise<SessionSamplesResponse>;
	deleteSession(sessionId: number): Promise<{ success: boolean }>;
	getSessionExportUrl(sessionId: number): string;
	importSession(file: File): Promise<{
		success: boolean;
		session_id?: number;
		message?: string;
		error?: string;
	}>;
}
