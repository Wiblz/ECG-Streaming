<script lang="ts">
	interface Props {
		/** Array of sample objects with timestamps and values */
		samples: Array<{ timestamp: number; value: number }>;
		/** Label for this monitor */
		label?: string;
		/** Height of the sparkline in pixels */
		height?: number;
		/** Color of the line */
		color?: string;
		/** Width of the sparkline in pixels (determines resolution) */
		width?: number;
		/** Pixels per time bucket (lower = more detail) */
		pixelsPerBucket?: number;
		/** Calculated sampling rate in Hz */
		samplingRate?: number | null;
	}

	let {
		samples,
		label = 'Activity',
		height = 60,
		color = '#10b981',
		width = 200,
		pixelsPerBucket = 3,
		samplingRate = null
	}: Props = $props();

	// Get latest value and count

	// Optimized min-max downsampling with fixed resolution based on time
	function renderSparkline(
		samples: Array<{ timestamp: number; value: number }>,
		width: number,
		height: number,
		pixelsPerBucket: number
	): { points: string; min: number; max: number } {
		if (samples.length === 0) {
			return { points: '', min: 0, max: 0 };
		}

		// Find global min/max in single pass
		let globalMin = samples[0].value;
		let globalMax = samples[0].value;
		for (let i = 1; i < samples.length; i++) {
			const val = samples[i].value;
			if (val < globalMin) globalMin = val;
			if (val > globalMax) globalMax = val;
		}
		const range = globalMax - globalMin || 1;

		// Fixed number of buckets based on pixel width (constant resolution)
		const numBuckets = Math.floor(width / pixelsPerBucket);

		if (samples.length <= numBuckets * 2) {
			// Not enough data to downsample, render all points
			const points: string[] = [];
			for (let i = 0; i < samples.length; i++) {
				const x = (i / (samples.length - 1 || 1)) * width;
				const y = height - ((samples[i].value - globalMin) / range) * height;
				points.push(`${x},${y}`);
			}
			return { points: points.join(' '), min: globalMin, max: globalMax };
		}

		// Divide TIME range into fixed buckets
		const minTime = samples[0].timestamp;
		const maxTime = samples[samples.length - 1].timestamp;
		const timeRange = maxTime - minTime;
		const bucketDuration = timeRange / numBuckets;

		const points: string[] = [];
		let sampleIdx = 0;

		// Single pass through samples with bucket tracking
		for (let bucketIdx = 0; bucketIdx < numBuckets; bucketIdx++) {
			const bucketStart = minTime + bucketIdx * bucketDuration;
			const bucketEnd = bucketStart + bucketDuration;

			let bucketMin = Infinity;
			let bucketMax = -Infinity;
			let minTimestamp = 0;
			let maxTimestamp = 0;
			let foundAny = false;

			// Advance through samples in this bucket (linear scan, no filter)
			while (sampleIdx < samples.length && samples[sampleIdx].timestamp < bucketEnd) {
				const sample = samples[sampleIdx];

				if (sample.timestamp >= bucketStart) {
					foundAny = true;
					if (sample.value < bucketMin) {
						bucketMin = sample.value;
						minTimestamp = sample.timestamp;
					}
					if (sample.value > bucketMax) {
						bucketMax = sample.value;
						maxTimestamp = sample.timestamp;
					}
				}

				sampleIdx++;
			}

			if (!foundAny) continue;

			const x = (bucketIdx / numBuckets) * width;

			// Add points in temporal order
			if (minTimestamp < maxTimestamp) {
				const yMin = height - ((bucketMin - globalMin) / range) * height;
				const yMax = height - ((bucketMax - globalMin) / range) * height;
				points.push(`${x},${yMin}`, `${x},${yMax}`);
			} else {
				const yMax = height - ((bucketMax - globalMin) / range) * height;
				const yMin = height - ((bucketMin - globalMin) / range) * height;
				points.push(`${x},${yMax}`, `${x},${yMin}`);
			}
		}

		return { points: points.join(' '), min: globalMin, max: globalMax };
	}

	// Cache the sparkline result to avoid recalculating on every reactive update
	let cachedSparkline = $state({ points: '', min: 0, max: 0 });
	let lastSampleCount = $state(0);
	let lastFirstTimestamp = $state(0);
	let lastLastTimestamp = $state(0);

	// Only recompute sparkline if data actually changed
	$effect(() => {
		const currentCount = samples.length;
		const currentFirst = samples.length > 0 ? samples[0].timestamp : 0;
		const currentLast = samples.length > 0 ? samples[samples.length - 1].timestamp : 0;

		// Skip if data hasn't changed
		if (
			currentCount === lastSampleCount &&
			currentFirst === lastFirstTimestamp &&
			currentLast === lastLastTimestamp
		) {
			return;
		}

		lastSampleCount = currentCount;
		lastFirstTimestamp = currentFirst;
		lastLastTimestamp = currentLast;

		// Defer computation to avoid blocking
		requestAnimationFrame(() => {
			cachedSparkline = renderSparkline(samples, width, height, pixelsPerBucket);
		});
	});

	const sparkline = $derived(cachedSparkline);
</script>

<div class="activity-monitor">
	<div class="header">
		<span class="title">{label}</span>
		<span class="rate">
			{#if samplingRate !== null}
				{samplingRate} Hz
			{:else}
				-
			{/if}
		</span>
	</div>

	<div class="monitor" style="--monitor-height: {height}px;">
		<svg class="sparkline" viewBox="0 0 {width} {height}" preserveAspectRatio="none">
			{#if samples.length > 0}
				<polyline
					points={sparkline.points}
					fill="none"
					stroke={color}
					stroke-width="1.5"
					vector-effect="non-scaling-stroke"
				/>
			{:else}
				<line
					x1="0"
					y1={height / 2}
					x2="200"
					y2={height / 2}
					stroke="#e5e7eb"
					stroke-width="1"
					stroke-dasharray="4"
				/>
			{/if}
		</svg>
	</div>
</div>

<style>
	.activity-monitor {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		font-family: ui-monospace, monospace;
		font-size: 0.75rem;
	}

	.header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.25rem 0.5rem;
		background: #f3f4f6;
		border-radius: 0.25rem;
	}

	.title {
		font-weight: 600;
		color: #374151;
		font-size: 0.8rem;
	}

	.rate {
		color: #6b7280;
		font-size: 0.7rem;
	}

	.monitor {
		padding: 0.5rem;
		background: #fafafa;
		border: 1px solid #e5e7eb;
		border-radius: 0.25rem;
	}

	.sparkline {
		width: 100%;
		height: var(--monitor-height);
		background: white;
		border-radius: 0.125rem;
	}
</style>
