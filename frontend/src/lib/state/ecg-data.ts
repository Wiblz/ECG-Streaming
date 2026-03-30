import type { BufferedECGSample } from '$lib/types/api';

const MAX_DURATION = 15; // seconds - keep more than window duration to avoid gaps

// Plain Map for ECG samples - no reactivity, polling-based access
export const samples = new Map<string, BufferedECGSample[]>();

let updateCount = 0;
let lastLogTime = 0;

export function addSamples(newSamples: BufferedECGSample[]) {
  const start = performance.now();
  const t1 = performance.now();

  // Group new samples by device to process in batch

  const byDevice = new Map<string, BufferedECGSample[]>();
  for (const sample of newSamples) {
    if (!byDevice.has(sample.device_id)) {
      byDevice.set(sample.device_id, []);
    }
    byDevice.get(sample.device_id)!.push(sample);
  }
  const t2 = performance.now();

  let trimCount = 0;

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
    const bufferDuration = newestTime - oldestTime;

    // Add 20% margin to avoid filtering on every update
    if (bufferDuration > MAX_DURATION * 1.2) {
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
        const filtered = deviceSamples.slice(left);
        samples.set(device_id, filtered);
        trimCount++;
      }
    }
  }
  const t3 = performance.now();

  const duration = performance.now() - start;
  updateCount++;

  // Log every 60 updates (~2 seconds at 30 FPS)
  const now = Date.now();
  if (now - lastLogTime > 2000) {
    const updateRate = updateCount / ((now - lastLogTime) / 1000);
    console.log(
      `[ECG Data] Updates: ${updateCount} in last ${((now - lastLogTime) / 1000).toFixed(1)}s (${updateRate.toFixed(1)}/s), ` +
        `last duration: ${duration.toFixed(1)}ms (group=${(t2 - t1).toFixed(1)}ms, process=${(t3 - t2).toFixed(1)}ms), ` +
        `samples: ${newSamples.length}, trimmed: ${trimCount}`
    );
    updateCount = 0;
    lastLogTime = now;
  }
}

export function clearSamples() {
  samples.clear();
}
