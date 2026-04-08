import type { BufferedAccelerometerSample } from '$lib/types/api';

const MAX_DURATION = 15; // seconds - keep more than window duration to avoid gaps

// Plain Map for accelerometer samples - no reactivity, polling-based access
export const samples = new Map<string, BufferedAccelerometerSample[]>();

export function addSamples(newSamples: BufferedAccelerometerSample[]) {
  // Group new samples by device to process in batch
  const byDevice = new Map<string, BufferedAccelerometerSample[]>();
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

    // Only trim if buffer exceeds threshold
    const newestTime = deviceSamples[deviceSamples.length - 1].global_time;
    const oldestTime = deviceSamples[0].global_time;

    if (newestTime - oldestTime > MAX_DURATION * 1.2) {
      const cutoffTime = newestTime - MAX_DURATION;

      // Binary search for first index to keep
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

      if (left > 0) {
        samples.set(device_id, deviceSamples.slice(left));
      }
    }
  }
}

export function clearSamples() {
  samples.clear();
}
