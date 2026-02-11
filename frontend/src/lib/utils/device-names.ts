/**
 * Utilities for working with device names and nicknames
 */

import type { DeviceInfo } from '$lib/types/api';

/**
 * Get display name for a device (nickname if available, otherwise device ID)
 */
export function getDeviceDisplayName(deviceId: string, nickname?: string | null): string {
	return nickname || deviceId;
}

/**
 * Create a map of device IDs to display names from device info
 */
export function createDeviceNicknameMap(devices: DeviceInfo[]): Map<string, string> {
	const map = new Map<string, string>();
	for (const device of devices) {
		if (device.nickname) {
			map.set(device.device_id, device.nickname);
		}
	}
	return map;
}

/**
 * Get display name for a device ID using a nickname map
 */
export function getDisplayNameFromMap(deviceId: string, nicknameMap: Map<string, string>): string {
	return nicknameMap.get(deviceId) || deviceId;
}
