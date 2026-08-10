<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import type uPlot from 'uplot';
  import { browser } from '$app/environment';

  export interface WaveformPlotApi {
    setData: (data: uPlot.AlignedData) => void;
    setScale: (scaleId: string, range: { min: number; max: number }) => void;
    setDataPreserveScale: (data: uPlot.AlignedData, scaleId?: string) => void;
    /** Replace data and scale ranges in one batched redraw */
    setFrame: (
      data: uPlot.AlignedData,
      scaleRanges: Record<string, { min: number; max: number }>
    ) => void;
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
    setFrame: (nextData, scaleRanges) => {
      if (!chart) return;
      chart.batch(() => {
        chart!.setData(nextData, false);
        for (const [scaleId, range] of Object.entries(scaleRanges)) {
          chart!.setScale(scaleId, range);
        }
      });
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

  /**
   * Total point count across the data, for use as an $effect dependency.
   *
   * Mode 2 data is [null, [xs, ys], ...], so data[0].length doesn't exist and
   * each series carries its own x array.
   */
  function dataLengthKey(d: uPlot.AlignedData): number {
    if (d[0] != null) return d[0].length;

    let total = 0;
    for (let i = 1; i < d.length; i++) {
      const facets = d[i] as unknown as [number[], number[]] | undefined;
      total += facets?.[0]?.length ?? 0;
    }
    return total;
  }

  function createChart() {
    if (!uPlotLib || !plotContainer || !options) return;
    // The mode 2 constructor reads series[1].facets, so it needs a device series
    if (options.mode === 2 && (options.series?.length ?? 0) < 2) return;
    if (plotContainer.clientWidth === 0) {
      pendingFrame = requestAnimationFrame(createChart);
      return;
    }

    const nextOptions = buildOptions();
    if (!nextOptions) return;

    chart = new uPlotLib(nextOptions, data, plotContainer);
    // Mode 1 renders a legend row for the x series; mode 2 does not. css/uplot.css
    // keys off this class to hide that row.
    if (options.mode !== 2) {
      chart.root.classList.add('u-mode-1');
    }
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
  $effect(() => {
    // Reading into the array is what registers data as a dependency; `if (data)` does not
    void dataLengthKey(data);
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
