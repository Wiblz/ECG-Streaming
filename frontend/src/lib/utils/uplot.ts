/**
 * Shared uPlot utilities for ECG waveform rendering
 */

import type uPlot from 'uplot';

// Device waveform color palettes — same hues, tuned lightness per theme
const DEVICE_COLORS_LIGHT = [
  '#2898BD', // Teal-blue
  '#5E4DB2', // Indigo
  '#E56910', // Orange
  '#943D73', // Magenta
  '#09326C', // Navy
  '#8F7EE7', // Lavender
  '#50253F', // Plum
  '#A54800' // Burnt orange
];

const DEVICE_COLORS_DARK = [
  '#6cc8e8', // Teal-blue — lighter
  '#9d8fef', // Indigo — lighter
  '#ffaa57', // Orange — lighter
  '#d97ab8', // Magenta — lighter
  '#4d8fd4', // Navy — much lighter
  '#c4b8ff', // Lavender — lighter
  '#c47faa', // Plum — lighter
  '#e88040' // Burnt orange — lighter
];

function isDarkTheme(): boolean {
  return document.documentElement.dataset.theme === 'dark';
}

/**
 * Get the full device color palette for the current theme
 */
export function getDeviceColors(): string[] {
  return isDarkTheme() ? DEVICE_COLORS_DARK : DEVICE_COLORS_LIGHT;
}

/**
 * Get color for device by index, adjusted for current theme
 */
export function getDeviceColor(index: number): string {
  return getDeviceColors()[index % getDeviceColors().length];
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
  const series: uPlot.Series[] = [{}];

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
 * Read a CSS custom property value from the document root.
 */
function getCssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/**
 * Create common axes configuration, reading theme colors at call time.
 */
export function createAxes(yLabel: string = 'Raw Value'): uPlot.Axis[] {
  const mutedColor = getCssVar('--color-text-secondary');
  const gridColor = getCssVar('--color-border');

  return [
    {
      label: 'Time (s)',
      values: formatTimeAxis,
      stroke: mutedColor,
      ticks: { stroke: gridColor },
      grid: { stroke: gridColor }
    },
    {
      label: yLabel,
      space: 80,
      gap: 5,
      stroke: mutedColor,
      ticks: { stroke: gridColor },
      grid: { stroke: gridColor }
    }
  ];
}
