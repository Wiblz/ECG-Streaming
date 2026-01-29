/**
 * Server-Sent Events (SSE) Protocol Types
 *
 * This file defines the strongly-typed contract for SSE events
 * exchanged between the aggregator server and frontend clients.
 *
 * Keep in sync with: packages/ecg-aggregator/src/ecg_aggregator/api/sse_broadcaster.py
 */

// SSE Event Type Literals
export type SSEEventType =
	| 'connected'
	| 'collector_update'
	| 'device_update'
	| 'buffer_stats'
	| 'heartbeat'

// Collector status values
export type CollectorStatus = 'CONNECTED' | 'HEALTHY' | 'DISCONNECTED'

// Device status values (matches protobuf enum)
export type DeviceStatus =
	| 'UNKNOWN'
	| 'DISCONNECTED'
	| 'CONNECTING'
	| 'CONNECTED'
	| 'STREAMING'
	| 'ERROR'

/**
 * Connected event - sent immediately on initial connection
 */
export interface ConnectedEventData {
	timestamp: number
}

/**
 * Collector update event - sent when collector status changes
 */
export interface CollectorUpdateData {
	collector_id: string
	display_name?: string
	status?: CollectorStatus
	device_count?: number
	samples_sent?: number
	active_devices?: number
}

/**
 * Device update event - sent when device status changes
 */
export interface DeviceUpdateData {
	device_id: string
	collector_id: string
	status?: DeviceStatus
	battery_level?: number | null
}

/**
 * Buffer stats event - sent periodically (every 5s) with buffer statistics
 */
export interface BufferStatsData {
	ecg_buffer: {
		total_samples: number
		duration_seconds: number
		device_count: number
		samples_per_device: Record<string, number>
		samples_per_second: number
		samples_per_second_per_device: Record<string, number>
		oldest_timestamp: number
		newest_timestamp: number
		total_processed: number
		buffer_utilization: number
	}
	acc_buffer: {
		total_samples: number
		duration_seconds: number
		device_count: number
		samples_per_device: Record<string, number>
		samples_per_second: number
		samples_per_second_per_device: Record<string, number>
		oldest_timestamp: number
		newest_timestamp: number
		total_processed: number
		buffer_utilization: number
	}
}

/**
 * Heartbeat event - keepalive sent when idle (every 30s)
 */
export interface HeartbeatEventData {
	timestamp: number
}

/**
 * Union of all SSE event data types
 */
export type SSEEventData =
	| ConnectedEventData
	| CollectorUpdateData
	| DeviceUpdateData
	| BufferStatsData
	| HeartbeatEventData

/**
 * SSE Message envelope (as received from EventSource)
 */
export interface SSEMessage<T extends SSEEventData = SSEEventData> {
	event: SSEEventType
	data: T
}
