import { SvelteMap } from 'svelte/reactivity';
import type { DeviceInfo } from '$lib/types/api';

// Reactive device map using SvelteMap for proper reactivity
const _devices = new SvelteMap<string, DeviceInfo>();

export function getDevices() {
  return _devices;
}

export function setDevices(devicesArray: DeviceInfo[]) {
  _devices.clear();
  devicesArray.forEach((device) => {
    _devices.set(device.device_id, device);
  });
}

export function updateDevice(deviceId: string, deviceInfo: DeviceInfo) {
  _devices.set(deviceId, deviceInfo);
}

/**
 * Update or add a device, merging with existing data if present
 */
export function mergeDevice(deviceId: string, partialInfo: Partial<DeviceInfo>) {
  const existing = _devices.get(deviceId);
  if (existing) {
    _devices.set(deviceId, { ...existing, ...partialInfo });
  } else {
    _devices.set(deviceId, { device_id: deviceId, sync_ready: false, ...partialInfo });
  }
}
