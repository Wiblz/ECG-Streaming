/**
 * Utility functions for working with grouped sample data.
 */

/**
 * Flatten grouped samples back into an array with device_id.
 *
 * @param devices - Record mapping device_id to array of samples (without device_id field)
 * @returns Flat array of samples with device_id field added
 */
export function flattenGroupedSamples<T>(devices: Record<string, Omit<T, 'device_id'>[]>): T[] {
	return Object.entries(devices).flatMap(([device_id, deviceSamples]) =>
		deviceSamples.map((sample) => ({ device_id, ...sample } as T))
	)
}
