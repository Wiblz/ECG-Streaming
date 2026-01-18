import { SvelteMap } from 'svelte/reactivity'
import type { BufferedECGSample } from '$lib/types/api'

const MAX_DURATION = 10 // seconds

// Reactive state for ECG samples - using SvelteMap for proper reactivity
const _samples = new SvelteMap<string, BufferedECGSample[]>()

export function getSamples() {
	return _samples
}

export function addSamples(newSamples: BufferedECGSample[]) {
	// Group new samples by device to process in batch
	const byDevice = new SvelteMap<string, BufferedECGSample[]>()
	for (const sample of newSamples) {
		if (!byDevice.has(sample.device_id)) {
			byDevice.set(sample.device_id, [])
		}
		byDevice.get(sample.device_id)!.push(sample)
	}

	// Process each device's samples in one go
	for (const [device_id, newDeviceSamples] of byDevice) {
		if (!_samples.has(device_id)) {
			_samples.set(device_id, [])
			// console.log(`[Live ECG Waveforms] ✓ New device: ${device_id}`);
		}

		// Get current samples, add new ones
		const deviceSamples = _samples.get(device_id)!
		deviceSamples.push(...newDeviceSamples)

		// Remove old samples based on newest timestamp
		const newestTime = deviceSamples[deviceSamples.length - 1].global_time
		const cutoffTime = newestTime - MAX_DURATION
		const filtered = deviceSamples.filter((s) => s.global_time >= cutoffTime)

		const dropped = deviceSamples.length - filtered.length
		if (dropped > 0) {
			// Show first and last 3 samples that were dropped
			const droppedSamples = deviceSamples.filter((s) => s.global_time < cutoffTime)
			const _droppedPreview = [
				...droppedSamples.slice(0, 3).map((s) => s.global_time.toFixed(2)),
				droppedSamples.length > 6 ? '...' : null,
				...droppedSamples.slice(-3).map((s) => s.global_time.toFixed(2))
			]
				.filter(Boolean)
				.join(', ')

			// console.log(
			// 	`[Live ECG Waveforms] ${device_id}: added ${newDeviceSamples.length}, dropped ${dropped} samples [${droppedPreview}], now ${filtered.length} (cutoff: ${cutoffTime.toFixed(2)}, newest: ${newestTime.toFixed(2)})`
			// );
		}

		// Log current buffer state
		const _timeRange =
			filtered.length > 0
				? `${filtered[0].global_time.toFixed(2)}s - ${filtered[filtered.length - 1].global_time.toFixed(2)}s`
				: 'empty'
		// console.log(
		// 	`[Live ECG Waveforms] ${device_id} buffer: ${filtered.length} samples, range: ${timeRange}`
		// );

		// Update the map with filtered samples
		_samples.set(device_id, filtered)
	}
}

export function clearSamples() {
	_samples.clear()
}
