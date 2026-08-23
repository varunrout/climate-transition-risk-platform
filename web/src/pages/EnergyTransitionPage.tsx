import { useState } from 'react'
import type { EChartsOption } from 'echarts'
import { useCountries, useCountryOverview, useEnergyIndicators } from '../lib/queries'
import { LoadingState, ErrorState, ChartUnavailable } from '../components/StatusStates'
import { Card } from '../components/Card'
import { Chart } from '../components/Chart'
import { formatPercent } from '../lib/format'

export function EnergyTransitionPage() {
  const overview = useCountryOverview()
  const countries = useCountries()
  const indicators = useEnergyIndicators()
  const [selected, setSelected] = useState<string>('')

  if (overview.isPending || countries.isPending || indicators.isPending) {
    return <LoadingState label="Loading energy transition data…" />
  }
  if (overview.isError) return <ErrorState error={overview.error} />
  if (countries.isError) return <ErrorState error={countries.error} />
  if (indicators.isError) return <ErrorState error={indicators.error} />

  const activeIso3 = selected || countries.data[0]?.country_iso3 || ''
  const series = indicators.data
    .filter((r) => r.country_iso3 === activeIso3)
    .sort((a, b) => a.year - b.year)

  const latestByCountry = overview.data
    .map((c) => ({
      iso3: c.country_iso3,
      name: c.country_name,
      lowCarbon: c.low_carbon_share_elec,
      momentum: c.transition_velocity,
    }))
    .filter((c) => c.lowCarbon !== null)
    .sort((a, b) => (b.lowCarbon ?? 0) - (a.lowCarbon ?? 0))

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Energy Transition</h1>
        <p className="mt-1 max-w-2xl text-sm text-[var(--color-text-muted)]">
          Raw electricity-mix indicators, shown separately from their normalised contribution to the
          production risk score.
        </p>
      </div>

      <Card title="Low-carbon electricity share, latest year" subtitle="Cross-country ranking (raw indicator, not risk-normalised)">
        {latestByCountry.length > 0 ? <CrossCountryChart data={latestByCountry} /> : <ChartUnavailable />}
      </Card>

      <Card
        title="Country energy-system trajectory"
        action={
          <label className="text-xs text-[var(--color-text-subtle)]">
            Country{' '}
            <select
              value={activeIso3}
              onChange={(e) => setSelected(e.target.value)}
              className="ml-1 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1"
            >
              {countries.data.map((c) => (
                <option key={c.country_iso3} value={c.country_iso3}>
                  {c.country_name}
                </option>
              ))}
            </select>
          </label>
        }
      >
        {series.length > 0 ? <MixTrajectoryChart series={series} /> : <ChartUnavailable />}
      </Card>

      <Card title="Latest indicators" subtitle="Raw shares (%) for the selected country's most recent year">
        {series.length > 0 ? <LatestIndicatorsTable row={series[series.length - 1]} /> : <ChartUnavailable />}
      </Card>
    </div>
  )
}

function CrossCountryChart({
  data,
}: {
  data: { iso3: string; name: string; lowCarbon: number | null; momentum: number | null }[]
}) {
  const option: EChartsOption = {
    xAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { color: 'var(--color-chart-grid)' } } },
    yAxis: { type: 'category', data: data.map((d) => d.iso3), inverse: true },
    series: [{ type: 'bar', data: data.map((d) => d.lowCarbon), itemStyle: { color: '#1e8f6b' }, barMaxWidth: 14 }],
  }
  return <Chart option={option} ariaLabel="Low-carbon electricity share by country" height={420} />
}

function MixTrajectoryChart({
  series,
}: {
  series: { year: number; fossil_share_elec: number | null; low_carbon_share_elec: number | null; renewables_share_elec: number | null }[]
}) {
  const option: EChartsOption = {
    legend: { top: 0, textStyle: { color: 'var(--color-text-muted)' } },
    xAxis: { type: 'category', data: series.map((s) => s.year) },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { color: 'var(--color-chart-grid)' } } },
    series: [
      { type: 'line', name: 'Fossil', data: series.map((s) => s.fossil_share_elec), showSymbol: false, itemStyle: { color: '#c0392b' } },
      { type: 'line', name: 'Low-carbon', data: series.map((s) => s.low_carbon_share_elec), showSymbol: false, itemStyle: { color: '#1e8f6b' } },
      { type: 'line', name: 'Renewables', data: series.map((s) => s.renewables_share_elec), showSymbol: false, itemStyle: { color: '#2e86ab' } },
    ],
  }
  return <Chart option={option} ariaLabel="Electricity mix trajectory over time" />
}

function LatestIndicatorsTable({
  row,
}: {
  row: {
    year: number
    coal_share_elec: number | null
    gas_share_elec: number | null
    renewables_share_elec: number | null
    low_carbon_share_elec: number | null
    latest_feature_clean_power_momentum_pp_per_year?: number | null
    latest_feature_renewable_buildout_rate_pp_per_year?: number | null
  }
}) {
  const items: [string, number | null | undefined][] = [
    ['Coal share', row.coal_share_elec],
    ['Gas share', row.gas_share_elec],
    ['Renewables share', row.renewables_share_elec],
    ['Low-carbon share', row.low_carbon_share_elec],
  ]
  return (
    <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt className="text-xs text-[var(--color-text-subtle)]">{label}</dt>
          <dd className="text-lg font-semibold tabular-nums">{formatPercent(value ?? null)}</dd>
        </div>
      ))}
    </dl>
  )
}
