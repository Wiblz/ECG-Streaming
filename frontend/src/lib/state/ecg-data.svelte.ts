import { SvelteMap } from 'svelte/reactivity';
import type { BufferedECGSample } from '$lib/types/api';

const MAX_DURATION = 10; // seconds

// Reactive state for ECG samples - using SvelteMap for proper reactivity
const _samples = new SvelteMap<string, BufferedECGSample[]>();

export function getSamples() {
	return _samples;
}

export function addSamples(newSamples: BufferedECGSample[]) {
	const now = Date.now() / 1000;
	const cutoffTime = now - MAX_DURATION;

	// Update each device's samples
	newSamples.forEach((sample) => {
		if (!_samples.has(sample.device_id)) {
			_samples.set(sample.device_id, []);
			console.log(`[ecg-data] ✓ New device: ${sample.device_id}`);
		}

		const deviceSamples = _samples.get(sample.device_id)!;
		deviceSamples.push(sample);

		// Remove old samples (older than 30 seconds)
		const filtered = deviceSamples.filter((s) => s.global_time >= cutoffTime);
		_samples.set(sample.device_id, filtered);
	});
}

export function clearSamples() {
	_samples.clear();
}
