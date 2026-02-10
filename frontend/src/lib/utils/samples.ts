/**
 * Utility functions for working with grouped sample data.
 */

import type uPlot from 'uplot'

/**
 * Flatten grouped samples back into an array with device_id.
 *
 * @param devices - Record mapping device_id to array of samples (without device_id field)
 * @returns Flat array of samples with device_id field added
 */
export function flattenGroupedSamples<T>(devices: Record<string, Omit<T, 'device_id'>[]>): T[] {
	return Object.entries(devices).flatMap(([device_id, deviceSamples]) =>
		deviceSamples.map((sample) => ({ device_id, ...sample }) as T)
	)
}

export interface AlignedDeviceSeries<T> {
	data: uPlot.AlignedData
	deviceOrder: string[]
	timestamps: number[]
	sampleByDeviceAndTime: Map<string, Map<number, T>>
}

export function groupSamplesByDevice<T extends { device_id: string }>(
	samples: T[]
): Map<string, T[]> {
	const byDevice = new Map<string, T[]>()
	for (const sample of samples) {
		let deviceSamples = byDevice.get(sample.device_id)
		if (!deviceSamples) {
			deviceSamples = []
			byDevice.set(sample.device_id, deviceSamples)
		}
		deviceSamples.push(sample)
	}
	return byDevice
}

export function buildUnionTimestamps<T extends { global_time: number }>(
	samples: T[],
	sessionStartTime: number
): number[] {
	const timeSet = new Set<number>()
	for (const sample of samples) {
		timeSet.add(sample.global_time - sessionStartTime)
	}
	return Array.from(timeSet).sort((a, b) => a - b)
}

function findNearestSampleIndex<T extends { global_time: number }>(
	samples: T[],
	targetAbsTime: number
): { index: number; diff: number } | null {
	if (samples.length === 0) {
		return null
	}

	let left = 0
	let right = samples.length - 1

	if (samples.length === 1) {
		return { index: 0, diff: Math.abs(samples[0].global_time - targetAbsTime) }
	}

	while (left < right) {
		const mid = Math.floor((left + right) / 2)
		if (samples[mid].global_time < targetAbsTime) {
			left = mid + 1
		} else {
			right = mid
		}
	}

	let closestIdx = left
	let minDiff = Math.abs(samples[left].global_time - targetAbsTime)

	if (left > 0) {
		const leftDiff = Math.abs(samples[left - 1].global_time - targetAbsTime)
		if (leftDiff < minDiff) {
			closestIdx = left - 1
			minDiff = leftDiff
		}
	}

	return { index: closestIdx, diff: minDiff }
}

/**
 * Align multi-device samples onto a shared time axis (relative to session start).
 */
export function alignSamplesToTimestamps<T extends { device_id: string; global_time: number }>(
	samplesByDevice: Map<string, T[]>,
	deviceOrder: string[],
	timestamps: number[],
	sessionStartTime: number,
	getValue: (sample: T) => number,
	maxGapSeconds: number
): AlignedDeviceSeries<T> {
	const sampleByDeviceAndTime = new Map<string, Map<number, T>>()

	const seriesData = deviceOrder.map((deviceId) => {
		const deviceSamples = samplesByDevice.get(deviceId) ?? []
		deviceSamples.sort((a, b) => a.global_time - b.global_time)

		const deviceLookup = new Map<number, T>()
		const series = timestamps.map((relTime) => {
			if (deviceSamples.length === 0) {
				return null
			}

			const targetAbsTime = sessionStartTime + relTime
			const nearest = findNearestSampleIndex(deviceSamples, targetAbsTime)
			if (!nearest || nearest.diff > maxGapSeconds) {
				return null
			}

			const sample = deviceSamples[nearest.index]
			deviceLookup.set(relTime, sample)
			return getValue(sample)
		})

		sampleByDeviceAndTime.set(deviceId, deviceLookup)
		return series
	})

	return {
		data: [timestamps, ...seriesData] as uPlot.AlignedData,
		deviceOrder,
		timestamps,
		sampleByDeviceAndTime
	}
}
