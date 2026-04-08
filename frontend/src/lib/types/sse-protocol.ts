/**
 * Server-Sent Events (SSE) Protocol Types
 *
 * Strongly-typed contract for SSE events exchanged between the
 * aggregator server and frontend clients.
 *
 * Keep in sync with: packages/ecg-aggregator/src/ecg_aggregator/application/dto/realtime.py
 */

import type { BufferStats, DeviceStatus } from '$lib/types/api';

// SSE Event Type Literals
export type SSEEventType =
  | 'connected'
  | 'collector_update'
  | 'device_update'
  | 'buffer_stats'
  | 'heartbeat';

// Collector status values
export type CollectorStatus = 'CONNECTED' | 'HEALTHY' | 'DISCONNECTED';

/**
 * Connected event - sent immediately on initial connection
 */
export interface ConnectedEventData {
  timestamp: number;
}

/**
 * Collector update event - sent when collector status changes
 */
export interface CollectorUpdateData {
  collector_id: string;
  display_name?: string;
  status?: CollectorStatus;
  device_count?: number;
  samples_sent?: number;
  active_devices?: number;
}

/**
 * Device update event - sent when device status changes
 */
export interface DeviceUpdateData {
  device_id: string;
  collector_id: string;
  status: DeviceStatus['status'];
  battery_level?: number | null;
}

/**
 * Buffer stats event - sent on connect and periodically with buffer statistics
 */
export interface BufferStatsData {
  ecg_buffer: BufferStats;
  acc_buffer: BufferStats;
}

/**
 * Heartbeat event - keepalive sent when idle (every 30s)
 */
export interface HeartbeatEventData {
  timestamp: number;
}
