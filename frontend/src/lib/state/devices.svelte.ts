import type { DeviceInfo } from '$lib/types/api'

// Reactive device map
const _devices = $state(new Map<string, DeviceInfo>())

export function getDevices() {
	return _devices
}

export function setDevices(devicesArray: DeviceInfo[]) {
	_devices.clear()
	devicesArray.forEach((device) => {
		_devices.set(device.device_id, device)
	})
}

export function updateDevice(deviceId: string, deviceInfo: DeviceInfo) {
	_devices.set(deviceId, deviceInfo)
}
