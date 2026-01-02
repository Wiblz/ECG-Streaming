<script lang="ts">
	import { onMount } from 'svelte';
	import * as d3 from 'd3';
	import { getSamples } from '$lib/state/ecg-data.svelte';

	let canvas: HTMLCanvasElement;
	let mounted = $state(false);

	// Get reactive samples
	const samples = $derived(getSamples());

	onMount(() => {
		mounted = true;
		return () => {
			mounted = false;
		};
	});

	// Effect to redraw when samples change
	$effect(() => {
		if (!mounted || !canvas) return;

		const ctx = canvas.getContext('2d');
		if (!ctx) return;

		const width = canvas.width;
		const height = canvas.height;

		// Clear canvas
		ctx.fillStyle = '#ffffff';
		ctx.fillRect(0, 0, width, height);

		// Draw grid
		ctx.strokeStyle = '#f0f0f0';
		ctx.lineWidth = 1;
		for (let i = 0; i <= 10; i++) {
			const y = (i / 10) * height;
			ctx.beginPath();
			ctx.moveTo(0, y);
			ctx.lineTo(width, y);
			ctx.stroke();

			const x = (i / 10) * width;
			ctx.beginPath();
			ctx.moveTo(x, 0);
			ctx.lineTo(x, height);
			ctx.stroke();
		}

		// Draw each device's data
		const colors = ['#ff3e00', '#40b3ff', '#676778', '#ff6b6b', '#4ecdc4'];
		let colorIndex = 0;

		for (const [deviceId, deviceSamples] of samples) {
			if (deviceSamples.length === 0) continue;

			ctx.strokeStyle = colors[colorIndex % colors.length];
			ctx.lineWidth = 2;
			ctx.globalAlpha = 0.8;
			ctx.beginPath();

			// Use D3 scales for proper mapping
			const xScale = d3
				.scaleLinear()
				.domain([0, deviceSamples.length - 1])
				.range([0, width]);

			const yScale = d3
				.scaleLinear()
				.domain([0, 1024]) // Typical ECG ADC range
				.range([height, 0]);

			deviceSamples.forEach((sample, i) => {
				const x = xScale(i);
				const y = yScale(sample.raw_value);

				if (i === 0) {
					ctx.moveTo(x, y);
				} else {
					ctx.lineTo(x, y);
				}
			});

			ctx.stroke();

			// Draw device label
			ctx.globalAlpha = 1;
			ctx.fillStyle = colors[colorIndex % colors.length];
			ctx.font = '12px sans-serif';
			ctx.fillText(deviceId, 10, 20 + colorIndex * 20);

			colorIndex++;
		}
	});
</script>

<div class="bg-white border border-gray-200 rounded-xl shadow-lg p-6">
	<div class="flex items-center justify-between mb-4">
		<h2 class="text-lg font-semibold text-gray-900">Live Waveforms</h2>
		<div class="flex items-center gap-2 text-xs text-gray-500">
			<div class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
			<span>Streaming</span>
		</div>
	</div>
	<canvas
		bind:this={canvas}
		width="800"
		height="400"
		class="w-full h-auto border border-gray-200 rounded-lg bg-white"
		style="max-width: 100%;"
	></canvas>
</div>
