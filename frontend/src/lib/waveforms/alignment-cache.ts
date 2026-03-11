import type { PlottableSample } from '$lib/types/api';

/**
 * Cache structure for aligned waveform data.
 * Stores aligned data to avoid re-aligning on every animation frame.
 */
export interface AlignmentCache<T extends PlottableSample> {
	deviceOrder: string[];
	deviceSampleCounts: Map<string, number>;
	timestamps: number[];
	seriesData: (number | null)[][];
	sampleByDeviceAndTime: Map<string, Map<number, T>>;
	sessionStartTime: number;
	baseDeviceId: string;
}

/**
 * Checks if the alignment cache is still valid for the current samples.
 * Cache is invalid if:
 * - Device list changed
 * - Sample counts changed
 * - Timestamps changed (samples shifted)
 * - Session start time changed
 */
export function isCacheValid<T extends PlottableSample>(
	cache: AlignmentCache<T> | null,
	sampleMap: Map<string, T[]>,
	sessionStartTime: number | null
): boolean {
	if (!cache) return false;

	const devices = Array.from(sampleMap.keys()).sort();

	// Check if session start time changed
	if (sessionStartTime !== null && cache.sessionStartTime !== sessionStartTime) {
		return false;
	}

	// Check if device list changed
	if (devices.length !== cache.deviceOrder.length) {
		return false;
	}
	if (!devices.every((d, idx) => cache.deviceOrder[idx] === d)) {
		return false;
	}

	// Check if any device has different sample count OR different timestamps
	for (const deviceId of devices) {
		const currentSamples = sampleMap.get(deviceId) ?? [];
		const cachedCount = cache.deviceSampleCounts.get(deviceId) ?? 0;

		// Count changed - cache invalid
		if (currentSamples.length !== cachedCount) {
			return false;
		}

		// Count same but check if timestamps changed (samples dropped and added)
		if (currentSamples.length > 0 && sessionStartTime !== null) {
			const cachedDeviceSamples = cache.sampleByDeviceAndTime.get(deviceId);
			if (!cachedDeviceSamples) return false;

			// Check first and last sample timestamps
			const firstCurrentTime = currentSamples[0].global_time - sessionStartTime;
			const lastCurrentTime =
				currentSamples[currentSamples.length - 1].global_time - sessionStartTime;

			const cachedTimes = Array.from(cachedDeviceSamples.keys()).sort((a, b) => a - b);
			if (cachedTimes.length === 0) return false;

			const firstCachedTime = cachedTimes[0];
			const lastCachedTime = cachedTimes[cachedTimes.length - 1];

			// If first or last timestamp changed, samples have shifted
			const EPSILON = 0.001;
			if (
				Math.abs(firstCurrentTime - firstCachedTime) > EPSILON ||
				Math.abs(lastCurrentTime - lastCachedTime) > EPSILON
			) {
				return false;
			}
		}
	}

	return true;
}

/**
 * Finds the device with the most samples to use as the time base for alignment.
 */
export function findBaseDevice<T extends PlottableSample>(
	sampleMap: Map<string, T[]>
): string | null {
	const devices = Array.from(sampleMap.keys());
	if (devices.length === 0) return null;

	let maxDevice = devices[0];
	let maxLength = 0;

	for (const deviceId of devices) {
		const len = sampleMap.get(deviceId)!.length;
		if (len > maxLength) {
			maxLength = len;
			maxDevice = deviceId;
		}
	}

	return maxDevice;
}
