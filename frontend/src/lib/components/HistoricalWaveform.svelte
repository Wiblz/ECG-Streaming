<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import uPlot from 'uplot';
	import type { SessionSample } from '$lib/types/api';

	interface Props {
		samples: SessionSample[];
		loading?: boolean;
	}

	let { samples, loading = false }: Props = $props();

	let plotContainer: HTMLDivElement;
	let chart: uPlot | null = null;

	// Downsample data to max points for performance
	const downsample = (samples: SessionSample[], maxPoints: number = 10000) => {
		if (samples.length <= maxPoints) return samples;

		console.log(`[uPlot] Downsampling ${samples.length} → ${maxPoints} points`);
		const stride = Math.ceil(samples.length / maxPoints);
		return samples.filter((_, i) => i % stride === 0);
	};

	// Group samples by device and prepare data for uPlot
	const prepareChartData = (samples: SessionSample[]) => {
		console.log(`[uPlot] Preparing ${samples.length} samples for visualization`);
		const startTime = performance.now();

		// For single device (most common case), use simpler logic
		const devices = [...new Set(samples.map((s) => s.device_id))];

		if (devices.length === 1) {
			// Single device - simple case
			const sorted = [...samples].sort((a, b) => a.global_time - b.global_time);
			const downsampled = downsample(sorted);
			const timestamps = downsampled.map((s) => s.global_time);
			const values = downsampled.map((s) => s.raw_value);

			const prepTime = performance.now() - startTime;
			console.log(
				`[uPlot] Data prepared in ${prepTime.toFixed(0)}ms (single device, ${downsampled.length} points)`
			);

			return {
				data: [timestamps, values],
				devices
			};
		}

		// Multiple devices - more complex
		const byDevice = new Map<string, SessionSample[]>();
		for (const sample of samples) {
			if (!byDevice.has(sample.device_id)) {
				byDevice.set(sample.device_id, []);
			}
			byDevice.get(sample.device_id)!.push(sample);
		}

		// Sort and downsample each device's samples
		for (const [deviceId, deviceSamples] of byDevice.entries()) {
			deviceSamples.sort((a, b) => a.global_time - b.global_time);
			byDevice.set(deviceId, downsample(deviceSamples));
		}

		// For multiple devices, just use first device's timestamps as x-axis
		const firstDevice = byDevice.values().next().value;
		const timestamps = firstDevice.map((s: SessionSample) => s.global_time);

		// Each device gets its own y-values array
		const seriesData = devices.map((deviceId) => {
			const deviceSamples = byDevice.get(deviceId)!;
			return deviceSamples.map((s) => s.raw_value);
		});

		const prepTime = performance.now() - startTime;
		console.log(
			`[uPlot] Data prepared in ${prepTime.toFixed(0)}ms (${devices.length} devices, ${timestamps.length} points each)`
		);

		return {
			data: [timestamps, ...seriesData],
			devices
		};
	};

	const createChart = () => {
		if (!plotContainer || samples.length === 0) return;

		console.log('[uPlot] Creating chart...');
		const startCreate = performance.now();

		const { data, devices } = prepareChartData(samples);

		const colors = ['#ff3e00', '#40b3ff', '#676778', '#ff6b6b', '#4ecdc4'];

		// Build series configuration
		const series: uPlot.Series[] = [
			{
				label: 'Time'
			}
		];

		devices.forEach((deviceId, idx) => {
			series.push({
				label: deviceId,
				stroke: colors[idx % colors.length],
				width: 2,
				points: { show: false } // Don't show individual points for performance
			});
		});

		const opts: uPlot.Options = {
			width: plotContainer.clientWidth,
			height: 400,
			series,
			axes: [
				{
					label: 'Time',
					values: (u, vals) => vals.map((v) => new Date(v * 1000).toLocaleTimeString())
				},
				{
					label: 'Raw Value',
					space: 40
				}
			],
			scales: {
				x: {
					time: false // Treat as numeric timestamps
				}
			},
			legend: {
				show: true
			}
		};

		if (chart) {
			chart.destroy();
		}

		chart = new uPlot(opts, data, plotContainer);

		const createTime = performance.now() - startCreate;
		console.log(`[uPlot] Chart created in ${createTime.toFixed(0)}ms`);
	};

	// Create chart when samples change
	$effect(() => {
		if (!loading && samples.length > 0) {
			createChart();
		}
	});

	// Handle window resize
	const handleResize = () => {
		if (chart && plotContainer) {
			chart.setSize({
				width: plotContainer.clientWidth,
				height: 400
			});
		}
	};

	onMount(() => {
		window.addEventListener('resize', handleResize);
	});

	onDestroy(() => {
		window.removeEventListener('resize', handleResize);
		if (chart) {
			chart.destroy();
		}
	});
</script>

<svelte:head>
	<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/uplot@1.6.32/dist/uPlot.min.css" />
</svelte:head>

<div class="bg-white border border-gray-200 rounded-xl shadow-lg p-6">
	<div class="flex items-center justify-between mb-4">
		<h2 class="text-lg font-semibold text-gray-900">ECG Waveform</h2>
		{#if loading}
			<div class="flex items-center gap-2 text-xs text-gray-500">
				<div class="w-2 h-2 bg-gray-400 rounded-full animate-pulse"></div>
				<span>Loading...</span>
			</div>
		{:else}
			<div class="text-xs text-gray-500">
				{samples.length.toLocaleString()} samples
			</div>
		{/if}
	</div>

	{#if samples.length === 0 && !loading}
		<div class="border border-gray-200 rounded-lg bg-gray-50 p-12 text-center">
			<p class="text-gray-500">No data to display</p>
		</div>
	{:else}
		<div bind:this={plotContainer} class="border border-gray-200 rounded-lg"></div>
	{/if}
</div>
