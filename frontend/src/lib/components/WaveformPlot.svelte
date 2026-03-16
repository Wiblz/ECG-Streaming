<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import type uPlot from 'uplot';
	import { browser } from '$app/environment';

	export interface WaveformPlotApi {
		setData: (data: uPlot.AlignedData) => void;
		setScale: (scaleId: string, range: { min: number; max: number }) => void;
		setDataPreserveScale: (data: uPlot.AlignedData, scaleId?: string) => void;
	}

	export type WaveformPlotOptions = Omit<uPlot.Options, 'width' | 'height'> & {
		height?: number;
	};

	interface Props {
		data: uPlot.AlignedData;
		options: WaveformPlotOptions | null;
		plotClass?: string;
		onReady?: (api: WaveformPlotApi) => void;
		onChartDestroy?: () => void;
	}

	let { data, options, plotClass = '', onReady, onChartDestroy }: Props = $props();

	let plotContainer: HTMLDivElement;
	let chart: uPlot | null = null;
	let uPlotLib = $state<typeof uPlot | null>(null);
	let currentOptions: WaveformPlotOptions | null = null;
	let pendingFrame: number | null = null;

	const api: WaveformPlotApi = {
		setData: (nextData) => {
			if (chart) {
				chart.setData(nextData);
			}
		},
		setScale: (scaleId, range) => {
			if (!chart) return;
			chart.setScale(scaleId, range);
		},
		setDataPreserveScale: (nextData, scaleId = 'x') => {
			if (!chart) return;
			const scale = chart.scales[scaleId];
			const currentMin = scale?.min;
			const currentMax = scale?.max;
			chart.batch(() => {
				chart!.setData(nextData, false);
				if (currentMin !== undefined && currentMax !== undefined) {
					chart!.setScale(scaleId, { min: currentMin, max: currentMax });
				}
			});
		}
	};

	function buildOptions(): uPlot.Options | null {
		if (!options) return null;
		return {
			...options,
			width: plotContainer.clientWidth,
			height: options.height ?? 400
		};
	}

	function createChart() {
		if (!uPlotLib || !plotContainer || !options) return;
		if (plotContainer.clientWidth === 0) {
			pendingFrame = requestAnimationFrame(createChart);
			return;
		}

		const nextOptions = buildOptions();
		if (!nextOptions) return;

		chart = new uPlotLib(nextOptions, data, plotContainer);
		currentOptions = options;
		onReady?.(api);
	}

	function destroyChart() {
		if (chart) {
			chart.destroy();
			chart = null;
			onChartDestroy?.();
		}
	}

	function handleResize() {
		if (!chart || !plotContainer) return;
		chart.setSize({
			width: plotContainer.clientWidth,
			height: chart.height ?? options?.height ?? 400
		});
	}

	$effect(() => {
		if (!browser || !uPlotLib) return;

		if (!options) {
			destroyChart();
			return;
		}

		if (!chart) {
			createChart();
			return;
		}

		if (options !== currentOptions) {
			destroyChart();
			createChart();
		}
	});

	// Update chart when data changes
	let effectRunCount = 0;
	let lastEffectLog = 0;
	$effect(() => {
		effectRunCount++;
		const now = performance.now();
		if (now - lastEffectLog > 2000) {
			const pointCount = data[0]?.length || 0;
			const seriesCount = data.length - 1;
			console.log(
				`[uPlot effect] ran ${effectRunCount} times in last ${((now - lastEffectLog) / 1000).toFixed(1)}s | rendering ${pointCount} points x ${seriesCount} series = ${pointCount * seriesCount} total`
			);
			effectRunCount = 0;
			lastEffectLog = now;
		}

		// Must read data[0]?.length to track the data array as a dependency.
		// Without this, just checking `if (data)` doesn't register data as a dependency.
		void data[0]?.length;
		if (chart && data) {
			chart.setData(data);
		}
	});

	onMount(async () => {
		if (!browser) return;
		const uPlotModule = await import('uplot');
		uPlotLib = uPlotModule.default;
		createChart();
		window.addEventListener('resize', handleResize);
	});

	onDestroy(() => {
		if (pendingFrame !== null) {
			cancelAnimationFrame(pendingFrame);
			pendingFrame = null;
		}
		if (browser) {
			window.removeEventListener('resize', handleResize);
		}
		destroyChart();
	});
</script>

<div bind:this={plotContainer} class={plotClass}></div>
