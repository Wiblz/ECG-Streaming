import type { BufferedAccelerometerSample } from '$lib/types/api';

const MAX_DURATION = 15; // seconds - keep more than window duration to avoid gaps

// Plain Map for accelerometer samples - no reactivity, polling-based access
export const samples = new Map<string, BufferedAccelerometerSample[]>();

let updateCount = 0;
let lastLogTime = 0;

export function addSamples(newSamples: BufferedAccelerometerSample[]) {
  const start = performance.now();
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
    const bufferDuration = newestTime - oldestTime;

    if (bufferDuration > MAX_DURATION * 1.2) {
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
        const filtered = deviceSamples.slice(left);
        samples.set(device_id, filtered);
      }
    }
  }

  const duration = performance.now() - start;
  updateCount++;

  // Log every 60 updates (~2 seconds at 30 FPS)
  const now = Date.now();
  if (now - lastLogTime > 2000) {
    console.log(
      `[ACC Data] Updates: ${updateCount} in last ${((now - lastLogTime) / 1000).toFixed(1)}s, last duration: ${duration.toFixed(1)}ms, samples: ${newSamples.length}`
    );
    updateCount = 0;
    lastLogTime = now;
  }
}

export function clearSamples() {
  samples.clear();
}
