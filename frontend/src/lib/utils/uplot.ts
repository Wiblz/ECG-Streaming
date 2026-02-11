/**
 * Shared uPlot utilities for ECG waveform rendering
 */

import type uPlot from 'uplot';

// Standard color palette for device waveforms
export const DEVICE_COLORS = ['#ff3e00', '#40b3ff', '#676778', '#ff6b6b', '#4ecdc4'];

/**
 * Get color for device by index
 */
export function getDeviceColor(index: number): string {
	return DEVICE_COLORS[index % DEVICE_COLORS.length];
}

/**
 * Create series configuration for devices
 */
export function createDeviceSeries(
	deviceIds: string[],
	getVerifiedIndices?: (deviceId: string) => number[],
	deviceNicknames?: Map<string, string>,
	spanGaps: boolean = true
): uPlot.Series[] {
	const series: uPlot.Series[] = [{ label: 'Time' }];

	deviceIds.forEach((deviceId, idx) => {
		const displayName = deviceNicknames?.get(deviceId) || deviceId;
		series.push({
			label: displayName,
			stroke: getDeviceColor(idx),
			width: 2,
			spanGaps,
			points: getVerifiedIndices
				? {
						show: true,
						size: 5,
						width: 2,
						stroke: '#00ff00', // Green for verified samples
						filter: () => {
							// Return pre-computed indices - O(1) lookup
							return getVerifiedIndices(deviceId);
						}
					}
				: { show: false }
		});
	});

	return series;
}

/**
 * Format time values for x-axis display
 */
export function formatTimeAxis(u: uPlot, vals: number[]): string[] {
	return vals.map((v) => {
		if (v < 60) {
			return v.toFixed(1) + 's';
		} else {
			const mins = Math.floor(v / 60);
			const secs = (v % 60).toFixed(0);
			return `${mins}m ${secs}s`;
		}
	});
}

/**
 * Create common axes configuration
 */
export function createAxes(yLabel: string = 'Raw Value'): uPlot.Axis[] {
	return [
		{
			label: 'Time (s)',
			values: formatTimeAxis
		},
		{
			label: yLabel,
			space: 80,
			gap: 5
		}
	];
}
