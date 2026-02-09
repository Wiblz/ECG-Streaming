/**
 * Server-Sent Events (SSE) client for real-time status updates.
 * Manages connection to /events/status endpoint and maintains reactive state.
 */

import { get_api_base_url } from '$lib/api/client'
import type { BufferStats, Collector, DeviceStatus } from '$lib/types/api'
import type {
	BufferStatsData,
	CollectorUpdateData,
	DeviceUpdateData
} from '$lib/types/sse-protocol'

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

class StatusEventsClient {
	private eventSource: EventSource | null = $state(null)
	private reconnectTimer: ReturnType<typeof setTimeout> | null = null
	private reconnectAttempts = 0
	private maxReconnectAttempts = 10
	private baseReconnectDelay = 1000

	// Reactive state using Svelte 5 runes
	connectionStatus = $state<ConnectionStatus>('disconnected')
	collectors = $state<Map<string, Collector>>(new Map())
	devices = $state<Map<string, DeviceStatus>>(new Map())
	bufferStats = $state<BufferStatsData | null>(null)
	lastUpdate = $state<Date | null>(null)
	error = $state<string | null>(null)

	constructor() {
		// Auto-connect on client-side (browser)
		if (typeof window !== 'undefined') {
			this.connect()
		}
	}

	/**
	 * Connect to the SSE endpoint
	 */
	connect() {
		if (this.eventSource) {
			this.eventSource.close()
		}

		this.connectionStatus = 'connecting'
		this.error = null

		try {
			const baseUrl = get_api_base_url()
			const url = `${baseUrl}/events/status`

			this.eventSource = new EventSource(url)

			this.eventSource.addEventListener('connected', (event) => {
				this.handleConnected(event)
			})

			this.eventSource.addEventListener('collector_update', (event) => {
				this.handleCollectorUpdate(event)
			})

			this.eventSource.addEventListener('device_update', (event) => {
				this.handleDeviceUpdate(event)
			})

			this.eventSource.addEventListener('buffer_stats', (event) => {
				this.handleBufferStats(event)
			})

			this.eventSource.addEventListener('heartbeat', (event) => {
				this.handleHeartbeat(event)
			})

			this.eventSource.onerror = (event) => {
				this.handleError(event)
			}

			this.eventSource.onopen = () => {
				this.connectionStatus = 'connected'
				this.reconnectAttempts = 0
				console.log('[SSE] Connected to status events')
			}
		} catch (err) {
			this.handleError(err)
		}
	}

	/**
	 * Disconnect from the SSE endpoint
	 */
	disconnect() {
		if (this.reconnectTimer) {
			clearTimeout(this.reconnectTimer)
			this.reconnectTimer = null
		}

		if (this.eventSource) {
			this.eventSource.close()
			this.eventSource = null
		}

		this.connectionStatus = 'disconnected'
	}

	/**
	 * Handle initial connection event
	 */
	private handleConnected(event: MessageEvent) {
		console.log('[SSE] Connected event received')
		this.connectionStatus = 'connected'
		this.lastUpdate = new Date()
	}

	/**
	 * Handle collector status updates
	 */
	private handleCollectorUpdate(event: MessageEvent) {
		try {
			const data: CollectorUpdateData = JSON.parse(event.data)
			const collectorId = data.collector_id

			if (data.status === 'DISCONNECTED') {
				// Remove collector
				this.collectors.delete(collectorId)
			} else {
				// Update or create collector
				const existing = this.collectors.get(collectorId)
				const updated: Collector = {
					collector_id: collectorId,
					display_name: data.display_name || existing?.display_name || collectorId,
					version: existing?.version || null,
					metadata: existing?.metadata || {},
					last_heartbeat: Date.now() / 1000,
					time_since_heartbeat: 0,
					health: data.status === 'HEALTHY' ? 'healthy' : 'warning',
					samples_sent: data.samples_sent ?? existing?.samples_sent,
					active_devices: data.active_devices ?? existing?.active_devices,
					connected: true, // We're in the else block, so not disconnected
					device_ids: existing?.device_ids,
					connected_at: existing?.connected_at ?? Date.now() / 1000
				}

				this.collectors.set(collectorId, updated)
			}

			this.lastUpdate = new Date()
		} catch (err) {
			console.error('[SSE] Error parsing collector_update:', err)
		}
	}

	/**
	 * Handle device status updates
	 */
	private handleDeviceUpdate(event: MessageEvent) {
		try {
			const data: DeviceUpdateData = JSON.parse(event.data)
			const deviceId = data.device_id

			const updated: DeviceStatus = {
				device_id: deviceId,
				collector_id: data.collector_id,
				collector_name: null, // Will be filled by components if needed
				status: data.status as DeviceStatus['status'],
				last_update: Date.now() / 1000,
				battery_level: data.battery_level ?? null,
				error_message: null
			}

			this.devices.set(deviceId, updated)
			this.lastUpdate = new Date()
		} catch (err) {
			console.error('[SSE] Error parsing device_update:', err)
		}
	}

	/**
	 * Handle buffer stats updates
	 */
	private handleBufferStats(event: MessageEvent) {
		try {
			const data = JSON.parse(event.data) as BufferStatsData | BufferStats
			if ('ecg_buffer' in data && 'acc_buffer' in data) {
				this.bufferStats = data
			} else {
				const empty: BufferStats = {
					total_samples: 0,
					duration_seconds: 0,
					device_count: 0,
					samples_per_device: {},
					samples_per_second: 0,
					samples_per_second_per_device: {},
					oldest_timestamp: null,
					newest_timestamp: null,
					total_processed: 0,
					buffer_utilization: 0
				}
				this.bufferStats = { ecg_buffer: data, acc_buffer: empty }
			}
			this.lastUpdate = new Date()
		} catch (err) {
			console.error('[SSE] Error parsing buffer_stats:', err)
		}
	}

	/**
	 * Handle heartbeat events
	 */
	private handleHeartbeat(event: MessageEvent) {
		// Just update last update time
		this.lastUpdate = new Date()
	}

	/**
	 * Handle connection errors
	 */
	private handleError(event: Event | unknown) {
		console.error('[SSE] Connection error:', event)

		if (this.eventSource?.readyState === EventSource.CLOSED) {
			this.connectionStatus = 'disconnected'

			// Attempt reconnection with exponential backoff
			if (this.reconnectAttempts < this.maxReconnectAttempts) {
				const delay = this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts)
				this.reconnectAttempts++

				console.log(
					`[SSE] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`
				)

				this.reconnectTimer = setTimeout(() => {
					this.connect()
				}, delay)
			} else {
				this.connectionStatus = 'error'
				this.error = 'Failed to connect after multiple attempts'
			}
		}
	}

	/**
	 * Get all collectors as an array
	 */
	getCollectors(): Collector[] {
		return Array.from(this.collectors.values())
	}

	/**
	 * Get all devices as an array
	 */
	getDevices(): DeviceStatus[] {
		return Array.from(this.devices.values())
	}

	/**
	 * Reset reconnection attempts (useful after successful connection)
	 */
	resetReconnection() {
		this.reconnectAttempts = 0
		if (this.reconnectTimer) {
			clearTimeout(this.reconnectTimer)
			this.reconnectTimer = null
		}
	}
}

// Export singleton instance
export const statusEvents = new StatusEventsClient()
