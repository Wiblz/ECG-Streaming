import type { Collector, DeviceInfo } from '$lib/types/api'

/**
 * Mock data for UI testing
 * Simulates various device and collector states
 */

// Generate mock collectors in different states
export function getMockCollectors(): Collector[] {
	const now = Date.now() / 1000

	return [
		// Healthy connected collector
		{
			collector_id: 'collector-001',
			display_name: 'Lab Station 1',
			device_ids: ['A0:E6:F8:1E:5C:9A', 'B1:D7:A9:2F:6D:8B'],
			version: '1.0.0',
			metadata: {
				location: 'Lab Room A',
				operator: 'Dr. Smith'
			},
			connected_at: now - 3600, // Connected 1 hour ago
			first_seen: now - 86400 * 7, // First seen 7 days ago
			last_seen: now,
			last_heartbeat: now - 2, // 2 seconds ago
			time_since_heartbeat: 2,
			health: 'healthy',
			samples_sent: 458392,
			active_devices: 2,
			connected: true
		},
		// Warning collector (slow heartbeat)
		{
			collector_id: 'collector-002',
			display_name: 'Mobile Unit 3',
			device_ids: ['C2:F8:B0:3A:7E:1C'],
			version: '1.0.0',
			metadata: {
				location: 'Field Test Site',
				operator: 'Dr. Johnson'
			},
			connected_at: now - 1800, // Connected 30 minutes ago
			first_seen: now - 86400 * 3, // First seen 3 days ago
			last_seen: now,
			last_heartbeat: now - 20, // 20 seconds ago (warning threshold)
			time_since_heartbeat: 20,
			health: 'warning',
			samples_sent: 125483,
			active_devices: 1,
			connected: true
		},
		// Disconnected collector (recently)
		{
			collector_id: 'collector-003',
			display_name: 'Lab Station 2',
			device_ids: ['D3:A9:C1:4B:8F:2D', 'E4:BA:D2:5C:9A:3E'],
			version: '0.9.5',
			metadata: {
				location: 'Lab Room B',
				operator: 'Dr. Williams'
			},
			first_seen: now - 86400 * 14, // First seen 14 days ago
			last_seen: now - 300, // Last seen 5 minutes ago
			last_heartbeat: now - 300,
			time_since_heartbeat: 300,
			health: 'disconnected',
			connected: false
		},
		// Disconnected collector (long time ago)
		{
			collector_id: 'collector-004',
			display_name: 'Backup Collector',
			version: '0.9.0',
			metadata: {
				location: 'Storage',
				notes: 'Spare unit'
			},
			first_seen: now - 86400 * 30, // First seen 30 days ago
			last_seen: now - 86400 * 2, // Last seen 2 days ago
			last_heartbeat: now - 86400 * 2,
			time_since_heartbeat: 86400 * 2,
			health: 'disconnected',
			connected: false
		}
	]
}

// Generate mock devices in different states
export function getMockDevices(): DeviceInfo[] {
	const now = Date.now() / 1000

	return [
		// Streaming device with nickname
		{
			device_id: 'A0:E6:F8:1E:5C:9A',
			nickname: 'Subject 1 - Chest',
			sync_ready: true,
			sync: {
				confidence: 0.98,
				drift_ppm: 2.3,
				sample_count: 45839
			},
			first_seen: now - 86400 * 7,
			last_seen: now - 1,
			total_samples: 458392,
			collector_id: 'collector-001',
			status: 'STREAMING',
			last_update: now - 1,
			battery_level: 87,
			error_message: null
		},
		// Connected device, syncing
		{
			device_id: 'B1:D7:A9:2F:6D:8B',
			nickname: 'Subject 2 - Chest',
			sync_ready: false,
			sync: {
				confidence: 0.65,
				drift_ppm: 15.7,
				sample_count: 234
			},
			first_seen: now - 86400 * 7,
			last_seen: now - 2,
			total_samples: 234,
			collector_id: 'collector-001',
			status: 'CONNECTED',
			last_update: now - 2,
			battery_level: 92,
			error_message: null
		},
		// Streaming device without nickname
		{
			device_id: 'C2:F8:B0:3A:7E:1C',
			sync_ready: true,
			sync: {
				confidence: 0.95,
				drift_ppm: 3.1,
				sample_count: 12548
			},
			first_seen: now - 86400 * 3,
			last_seen: now - 3,
			total_samples: 125483,
			collector_id: 'collector-002',
			status: 'STREAMING',
			last_update: now - 3,
			battery_level: 54,
			error_message: null
		},
		// Disconnected device (from recently disconnected collector)
		{
			device_id: 'D3:A9:C1:4B:8F:2D',
			nickname: 'Test Device Alpha',
			sync_ready: false,
			first_seen: now - 86400 * 14,
			last_seen: now - 300,
			total_samples: 892451,
			collector_id: 'collector-003',
			status: 'DISCONNECTED',
			last_update: now - 300,
			battery_level: null,
			error_message: null
		},
		// Another disconnected device
		{
			device_id: 'E4:BA:D2:5C:9A:3E',
			nickname: 'Test Device Beta',
			sync_ready: false,
			first_seen: now - 86400 * 14,
			last_seen: now - 300,
			total_samples: 783291,
			collector_id: 'collector-003',
			status: 'DISCONNECTED',
			last_update: now - 300,
			battery_level: null,
			error_message: null
		},
		// Device with error
		{
			device_id: 'F5:CB:E3:6D:AB:4F',
			nickname: 'Faulty Sensor',
			sync_ready: false,
			first_seen: now - 86400 * 5,
			last_seen: now - 10,
			total_samples: 15234,
			collector_id: 'collector-001',
			status: 'ERROR',
			last_update: now - 10,
			battery_level: 12,
			error_message: 'Signal quality too low - check electrode connection'
		},
		// Connecting device
		{
			device_id: 'G6:DC:F4:7E:BC:5A',
			sync_ready: false,
			first_seen: now - 86400,
			last_seen: now - 5,
			total_samples: 892,
			collector_id: 'collector-002',
			status: 'CONNECTING',
			last_update: now - 5,
			battery_level: 100,
			error_message: null
		},
		// Old disconnected device (no collector association)
		{
			device_id: 'H7:ED:A5:8F:CD:6B',
			nickname: 'Retired Device',
			sync_ready: false,
			first_seen: now - 86400 * 30,
			last_seen: now - 86400 * 2,
			total_samples: 5483921,
			collector_id: null,
			status: 'DISCONNECTED',
			last_update: now - 86400 * 2,
			battery_level: null,
			error_message: null
		},
		// Unknown status device
		{
			device_id: 'I8:FE:B6:9A:DE:7C',
			sync_ready: false,
			first_seen: now - 86400 * 10,
			last_seen: now - 3600,
			total_samples: 234891,
			collector_id: 'collector-004',
			status: 'UNKNOWN',
			last_update: now - 3600,
			battery_level: null,
			error_message: null
		}
	]
}

// Simulate live updates to mock data (for testing real-time updates)
export function updateMockData(
	devices: DeviceInfo[],
	collectors: Collector[]
): { devices: DeviceInfo[]; collectors: Collector[] } {
	const now = Date.now() / 1000

	// Update timestamps for connected devices/collectors
	const updatedDevices = devices.map((device) => {
		if (device.status === 'STREAMING' || device.status === 'CONNECTED') {
			return {
				...device,
				last_seen: now - Math.random() * 5,
				last_update: now - Math.random() * 5,
				// Simulate battery drain
				battery_level:
					device.battery_level !== null && device.battery_level !== undefined
						? Math.max(0, device.battery_level - Math.random() * 0.01)
						: null,
				// Randomly update sync stats
				sync: device.sync
					? {
							...device.sync,
							sample_count: device.sync.sample_count + Math.floor(Math.random() * 100),
							confidence: Math.min(1, device.sync.confidence + (Math.random() - 0.5) * 0.01)
						}
					: undefined,
				total_samples: device.total_samples
					? device.total_samples + Math.floor(Math.random() * 100)
					: 0
			}
		}
		return device
	})

	const updatedCollectors = collectors.map((collector) => {
		if (collector.connected) {
			return {
				...collector,
				last_seen: now,
				last_heartbeat: now - Math.random() * 10,
				time_since_heartbeat: Math.random() * 10,
				samples_sent: collector.samples_sent
					? collector.samples_sent + Math.floor(Math.random() * 200)
					: 0
			}
		}
		return collector
	})

	return { devices: updatedDevices, collectors: updatedCollectors }
}
