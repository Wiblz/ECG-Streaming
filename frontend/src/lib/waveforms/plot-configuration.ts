import type uPlot from 'uplot';
import type { WaveformPlotOptions } from '$lib/components/WaveformPlot.svelte';

export interface PlotConfigOptions {
	/**
	 * Device IDs to create series for
	 */
	devices: string[];

	/**
	 * Y-axis label
	 */
	yAxisLabel: string;

	/**
	 * Height of the plot in pixels
	 */
	height?: number;

	/**
	 * Whether to show verified sample points
	 */
	showVerifiedPoints?: boolean;

	/**
	 * Function to get verified indices for a device
	 */
	getVerifiedIndices?: (deviceId: string) => number[];

	/**
	 * Map of device IDs to display nicknames
	 */
	deviceNicknames?: Map<string, string>;

	/**
	 * Whether to span gaps in the series
	 */
	spanGaps?: boolean;

	/**
	 * Additional uPlot plugins to include
	 */
	plugins?: uPlot.Plugin[];

	/**
	 * Custom scale configuration
	 */
	scales?: uPlot.Scales;

	/**
	 * Custom hooks
	 */
	hooks?: uPlot.Hooks.Arrays;

	/**
	 * Legend configuration
	 */
	legend?: uPlot.Legend;

	/**
	 * Functions to create series and axes (loaded from uplot-config)
	 */
	createDeviceSeries: (
		deviceIds: string[],
		getVerifiedIndices?: (deviceId: string) => number[],
		deviceNicknames?: Map<string, string>,
		spanGaps?: boolean
	) => uPlot.Series[];

	createAxes: (yLabel: string) => uPlot.Axis[];
}

/**
 * Builds uPlot options configuration from the given parameters.
 * This centralizes plot configuration logic shared between live and historical waveforms.
 */
export function buildPlotOptions(config: PlotConfigOptions): WaveformPlotOptions | null {
	const {
		devices,
		yAxisLabel,
		height = 400,
		showVerifiedPoints = false,
		getVerifiedIndices,
		deviceNicknames,
		spanGaps = true,
		plugins = [],
		scales,
		hooks,
		legend,
		createDeviceSeries,
		createAxes
	} = config;

	if (devices.length === 0) {
		return null;
	}

	return {
		height,
		series: createDeviceSeries(
			devices,
			showVerifiedPoints && getVerifiedIndices ? getVerifiedIndices : undefined,
			deviceNicknames,
			spanGaps
		),
		axes: createAxes(yAxisLabel),
		scales: scales || {
			x: {
				time: false
			}
		},
		plugins,
		hooks,
		legend: legend || {
			show: true
		}
	};
}
