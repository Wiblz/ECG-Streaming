import type uPlot from 'uplot'

export interface TooltipOptions {
	/** Show individual tooltips for each series data point */
	showSeriesPoints?: boolean
	/** Show cursor position tooltip */
	showCursorPosition?: boolean
	/** Custom formatter for tooltip text - receives x value, y value, series index, and data point index */
	formatValue?: (xVal: number, yVal: number, seriesIdx: number, dataIdx: number) => string
}

/**
 * uPlot plugin for displaying tooltips on hover.
 *
 * Creates tooltips that show:
 * - Individual data point values for each series
 * - Automatically positions tooltips at data points
 * - Respects series visibility settings
 *
 * @param opts - Tooltip configuration options
 * @returns uPlot plugin object
 */
export function tooltipsPlugin(opts: TooltipOptions = {}) {
	const {
		showSeriesPoints = true,
		showCursorPosition = false,
		formatValue = (xVal: number, yVal: number, seriesIdx: number, dataIdx: number) =>
			`${xVal.toFixed(2)}, ${yVal.toFixed(2)}`
	} = opts

	let cursortt: HTMLDivElement | null = null
	let seriestt: (HTMLDivElement | undefined)[] = []

	function init(u: uPlot) {
		const over = u.over

		// Create cursor position tooltip
		if (showCursorPosition) {
			const tt = (cursortt = document.createElement('div'))
			tt.className = 'uplot-tooltip uplot-tooltip-cursor'
			tt.style.pointerEvents = 'none'
			tt.style.position = 'absolute'
			tt.style.background = 'rgba(0, 0, 0, 0.8)'
			tt.style.color = 'white'
			tt.style.padding = '4px 8px'
			tt.style.borderRadius = '4px'
			tt.style.fontSize = '12px'
			tt.style.fontFamily = 'monospace'
			tt.style.display = 'none'
			tt.style.zIndex = '1000'
			over.appendChild(tt)
		}

		// Create series tooltips
		if (showSeriesPoints) {
			seriestt = u.series.map((s, i) => {
				if (i === 0) return undefined // Skip x-axis

				const tt = document.createElement('div')
				tt.className = 'uplot-tooltip uplot-tooltip-series'
				tt.style.pointerEvents = 'none'
				tt.style.position = 'absolute'
				tt.style.background = 'rgba(0, 0, 0, 0.9)'
				tt.style.color = 'white'
				tt.style.padding = '6px 10px'
				tt.style.borderRadius = '4px'
				tt.style.fontSize = '11px'
				tt.style.fontFamily = 'monospace'
				tt.style.display = 'none'
				tt.style.zIndex = '1000'
				tt.style.lineHeight = '1.2'

				// Add a small dot indicator in the series color
				if (s.stroke) {
					tt.style.borderLeft = `3px solid ${s.stroke as string}`
				}

				over.appendChild(tt)
				return tt
			})
		}

		function hideTips() {
			if (cursortt) cursortt.style.display = 'none'
			seriestt.forEach((tt) => {
				if (tt) tt.style.display = 'none'
			})
		}

		function showTips() {
			if (cursortt) cursortt.style.display = 'block'
			seriestt.forEach((tt, i) => {
				if (!tt || i === 0) return
				const s = u.series[i]
				tt.style.display = s.show ? 'block' : 'none'
			})
		}

		over.addEventListener('mouseleave', () => {
			if (!u.cursor.lock) {
				hideTips()
			}
		})

		over.addEventListener('mouseenter', () => {
			showTips()
		})

		// Initial state
		if (u.cursor.left && u.cursor.left >= 0) {
			showTips()
		} else {
			hideTips()
		}
	}

	function setCursor(u: uPlot) {
		const { left, top, idx } = u.cursor

		if (left === undefined || top === undefined || idx === undefined) {
			return
		}

		// Update cursor position tooltip
		if (cursortt && showCursorPosition) {
			cursortt.style.left = left + 'px'
			cursortt.style.top = top + 'px'
			const xVal = u.posToVal(left, 'x')
			const yVal = u.posToVal(top, 'y')
			cursortt.textContent = `(${xVal.toFixed(2)}, ${yVal.toFixed(2)})`
		}

		// Update series tooltips
		if (showSeriesPoints) {
			seriestt.forEach((tt, i) => {
				if (!tt || i === 0) return

				const s = u.series[i]

				if (s.show && idx !== null && idx !== undefined) {
					const xVal = u.data[0][idx]
					const yVal = u.data[i][idx]

					if (xVal !== null && xVal !== undefined && yVal !== null && yVal !== undefined) {
						tt.innerHTML = formatValue(xVal, yVal, i, idx)

						// Position tooltip at cursor position
						tt.style.left = left + 15 + 'px'
						tt.style.top = top + 15 + 'px'
						tt.style.display = 'block'
					} else {
						tt.style.display = 'none'
					}
				} else {
					tt.style.display = 'none'
				}
			})
		}
	}

	return {
		hooks: {
			init,
			setCursor
		}
	}
}
