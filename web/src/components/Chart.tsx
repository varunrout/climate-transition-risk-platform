import * as echarts from 'echarts/core'
import { BarChart, LineChart, ScatterChart } from 'echarts/charts'
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
import { useEcharts } from '../lib/useEcharts'

// Only the chart/renderer modules the dashboard actually uses -- avoids
// pulling the full echarts bundle (this alone cuts the largest production
// chunk from ~1.1MB to a few hundred KB).
echarts.use([
  BarChart,
  LineChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  SVGRenderer,
])

/**
 * Thin wrapper around ECharts with a project-standard grid/axis palette and
 * a plain-text summary for screen readers (charts do not have accessible
 * text content by default -- ECharts renders to canvas/SVG).
 */
export function Chart({
  option,
  height = 280,
  ariaLabel,
  summary,
}: {
  option: EChartsOption
  height?: number
  ariaLabel: string
  summary?: string
}) {
  const merged: EChartsOption = {
    textStyle: { fontFamily: 'inherit' },
    grid: { left: 48, right: 16, top: 24, bottom: 32, containLabel: true },
    ...option,
  }
  const { containerRef } = useEcharts(merged)

  return (
    <div role="img" aria-label={ariaLabel}>
      <div ref={containerRef} style={{ height, width: '100%' }} />
      {summary && <p className="sr-only">{summary}</p>}
    </div>
  )
}
