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
}

export interface BufferStats {
	total_samples: number;
	duration_seconds: number;
	device_count: number;
	samples_per_device: Record<string, number>;
	oldest_timestamp: number;
	newest_timestamp: number;
	total_processed: number;
	dropped_samples: number;
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
	device_ids: string[];
	version: string | null;
	metadata: Record<string, string>;
	connected_at: number;
	last_heartbeat: number;
	time_since_heartbeat: number;
	health: 'healthy' | 'warning' | 'disconnected';
	samples_sent: number;
	active_devices: number;
}

export interface CollectorsResponse {
	collectors: Collector[];
	count: number;
	error?: string;
}
