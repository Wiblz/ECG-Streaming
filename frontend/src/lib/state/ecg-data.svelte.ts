import type { BufferedECGSample } from '$lib/types/api';

const MAX_DURATION = 30; // seconds

// Reactive state for ECG samples
const _samples = $state(new Map<string, BufferedECGSample[]>());

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
