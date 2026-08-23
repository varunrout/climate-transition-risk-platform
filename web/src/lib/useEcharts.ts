import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import type { EChartsOption, ECharts } from 'echarts'

/**
 * Minimal direct ECharts binding.
 *
 * `echarts-for-react`'s core wrapper does a two-phase init (create a
 * throwaway instance, wait for its 'finished' event, then recreate with
 * measured size) before ever calling `setOption`. Under echarts v6 that
 * 'finished' event never fires for an instance with no option set yet, so
 * the wrapper permanently renders an empty chart with no error -- a real,
 * observed version-incompatibility bug (verified in-browser), not a
 * configuration mistake. This hook calls `init`/`setOption` directly,
 * which is the standard, version-agnostic ECharts React pattern.
 */
export function useEcharts(option: EChartsOption) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<ECharts | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const chart = echarts.init(containerRef.current, undefined, { renderer: 'svg' })
    chartRef.current = chart

    const resizeObserver = new ResizeObserver(() => chart.resize())
    resizeObserver.observe(containerRef.current)

    return () => {
      resizeObserver.disconnect()
      chart.dispose()
      chartRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    chartRef.current?.setOption(option, true)
  }, [option])

  return { containerRef, chartRef }
}
