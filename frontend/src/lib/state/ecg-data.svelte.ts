import { SvelteMap } from 'svelte/reactivity';
import type { BufferedECGSample } from '$lib/types/api';

const MAX_DURATION = 15; // seconds - keep more than window duration to avoid gaps

// Reactive state for ECG samples - using SvelteMap for proper reactivity
const _samples = new SvelteMap<string, BufferedECGSample[]>();

export function getSamples() {
  return _samples;
}

export function addSamples(newSamples: BufferedECGSample[]) {
  // Group new samples by device to process in batch
  const byDevice = new SvelteMap<string, BufferedECGSample[]>();
  for (const sample of newSamples) {
    if (!byDevice.has(sample.device_id)) {
      byDevice.set(sample.device_id, []);
    }
    byDevice.get(sample.device_id)!.push(sample);
  }

  // Process each device's samples in one go
  for (const [device_id, newDeviceSamples] of byDevice) {
    if (!_samples.has(device_id)) {
      _samples.set(device_id, []);
    }

    // Get current samples, add new ones
    const deviceSamples = _samples.get(device_id)!;
    deviceSamples.push(...newDeviceSamples);

    // Remove old samples based on newest timestamp
    const newestTime = deviceSamples[deviceSamples.length - 1].global_time;
    const cutoffTime = newestTime - MAX_DURATION;
    const filtered = deviceSamples.filter((s) => s.global_time >= cutoffTime);

    // Update the map with filtered samples
    _samples.set(device_id, filtered);
  }
}

export function clearSamples() {
  _samples.clear();
}
