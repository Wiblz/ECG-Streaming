import type { BufferedECGSample } from '$lib/types/api';

const MAX_DURATION = 15; // seconds - keep more than window duration to avoid gaps

// Plain Map for ECG samples - no reactivity, polling-based access
export const samples = new Map<string, BufferedECGSample[]>();

export function addSamples(newSamples: BufferedECGSample[]) {
  // Group new samples by device to process in batch
  const byDevice = new Map<string, BufferedECGSample[]>();
  for (const sample of newSamples) {
    if (!byDevice.has(sample.device_id)) {
      byDevice.set(sample.device_id, []);
    }
    byDevice.get(sample.device_id)!.push(sample);
  }

  // Process each device's samples in one go
  for (const [device_id, newDeviceSamples] of byDevice) {
    if (!samples.has(device_id)) {
      samples.set(device_id, []);
    }

    // Get current samples, add new ones
    const deviceSamples = samples.get(device_id)!;
    deviceSamples.push(...newDeviceSamples);

    // Only filter if buffer duration exceeds threshold
    const newestTime = deviceSamples[deviceSamples.length - 1].global_time;
    const oldestTime = deviceSamples[0].global_time;

    // Add 20% margin to avoid filtering on every update
    if (newestTime - oldestTime > MAX_DURATION * 1.2) {
      const cutoffTime = newestTime - MAX_DURATION;

      // Find first index to keep using binary search
      let left = 0;
      let right = deviceSamples.length;
      while (left < right) {
        const mid = Math.floor((left + right) / 2);
        if (deviceSamples[mid].global_time < cutoffTime) {
          left = mid + 1;
        } else {
          right = mid;
        }
      }

      // Remove old samples if needed
      if (left > 0) {
        samples.set(device_id, deviceSamples.slice(left));
      }
    }
  }
}
