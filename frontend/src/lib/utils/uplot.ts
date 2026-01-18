/**
 * Shared uPlot utilities for ECG waveform rendering
 */

import type uPlot from 'uplot'

// Standard color palette for device waveforms
export const DEVICE_COLORS = ['#ff3e00', '#40b3ff', '#676778', '#ff6b6b', '#4ecdc4']

/**
 * Get color for device by index
 */
export function getDeviceColor(index: number): string {
	return DEVICE_COLORS[index % DEVICE_COLORS.length]
}

/**
 * Create series configuration for devices
 */
export function createDeviceSeries(deviceIds: string[]): uPlot.Series[] {
	const series: uPlot.Series[] = [{ label: 'Time' }]

	deviceIds.forEach((deviceId, idx) => {
		series.push({
			label: deviceId,
			stroke: getDeviceColor(idx),
			width: 2,
			points: { show: false }
		})
	})

	return series
}

/**
 * Format time values for x-axis display
 */
export function formatTimeAxis(u: uPlot, vals: number[]): string[] {
	return vals.map((v) => {
		if (v < 60) {
			return v.toFixed(1) + 's'
		} else {
			const mins = Math.floor(v / 60)
			const secs = (v % 60).toFixed(0)
			return `${mins}m ${secs}s`
		}
	})
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
	]
}
