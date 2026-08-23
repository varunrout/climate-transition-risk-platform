import { useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import * as echarts from 'echarts/core'
import { MapChart } from 'echarts/charts'
import { TooltipComponent, VisualMapComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
import { useEcharts } from '../lib/useEcharts'
import { buildWorldGeoJson } from '../lib/worldMap'
import type { CountryOverview } from '../lib/schemas'

const MAP_NAME = 'world-g20'

echarts.use([MapChart, TooltipComponent, VisualMapComponent, SVGRenderer])
echarts.registerMap(MAP_NAME, buildWorldGeoJson() as never)

export function RiskMap({ countries }: { countries: CountryOverview[] }) {
  const navigate = useNavigate()

  const option = useMemo<EChartsOption>(() => {
    const scores = countries.map((c) => c.score_total)
    return {
      tooltip: {
        trigger: 'item',
        formatter: (params: unknown) => {
          const p = params as { name: string; value?: number }
          const country = countries.find((c) => c.country_iso3 === p.name)
          if (!country) return p.name
          return `<strong>${country.country_name}</strong><br/>Transition risk score: ${country.score_total.toFixed(1)}<br/>Rank #${country.rank} of ${countries.length}`
        },
      },
      visualMap: {
        min: Math.min(...scores),
        max: Math.max(...scores),
        left: 'left',
        bottom: 8,
        text: ['Higher risk', 'Lower risk'],
        calculable: false,
        // ECharts renders to canvas/SVG and cannot resolve CSS custom
        // properties, so these mirror the --color-risk-* tokens as literal
        // hex values (kept in sync manually; see src/index.css).
        inRange: { color: ['#2e86ab', '#d4ac0d', '#e67e22', '#c0392b'] },
      },
      series: [
        {
          type: 'map',
          map: MAP_NAME,
          roam: true,
          selectedMode: false,
          emphasis: { label: { show: false }, itemStyle: { areaColor: '#144a6e' } },
          itemStyle: { borderColor: '#ffffff', borderWidth: 0.5 },
          data: countries.map((c) => ({ name: c.country_iso3, value: c.score_total })),
        },
      ],
    }
  }, [countries])

  const { containerRef, chartRef } = useEcharts(option)

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const handler = (params: { name?: string }) => {
      if (params.name && countries.some((c) => c.country_iso3 === params.name)) {
        navigate(`/country/${params.name}`)
      }
    }
    chart.on('click', handler)
    return () => {
      chart.off('click', handler)
    }
  }, [chartRef, countries, navigate])

  return (
    <div role="img" aria-label="World map coloured by transition risk score for covered G20 sovereigns">
      <div ref={containerRef} style={{ height: 360, width: '100%' }} />
      <p className="sr-only">
        Interactive map. {countries.length} covered countries, coloured by transition risk score.
        Use the sortable ranking table below for the same information in accessible form.
      </p>
    </div>
  )
}
