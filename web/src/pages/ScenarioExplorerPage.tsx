import { useState } from 'react'
import type { EChartsOption } from 'echarts'
import { useCountries, useCountryTimeseries, useScenarioQuantiles } from '../lib/queries'
import { LoadingState, ErrorState, ChartUnavailable } from '../components/StatusStates'
import { Card, StatCard } from '../components/Card'
import { Chart } from '../components/Chart'
import { ProductionTag, ResearchTag } from '../components/Badges'
import { formatNumber } from '../lib/format'

export function ScenarioExplorerPage() {
  const countries = useCountries()
  const scenarios = useScenarioQuantiles()
  const timeseries = useCountryTimeseries()
  const [selected, setSelected] = useState('')

  if (countries.isPending || scenarios.isPending || timeseries.isPending) {
    return <LoadingState label="Loading scenario explorer…" />
  }
  if (countries.isError) return <ErrorState error={countries.error} />
  if (scenarios.isError) return <ErrorState error={scenarios.error} />
  if (timeseries.isError) return <ErrorState error={timeseries.error} />

  const activeIso3 = selected || countries.data[0]?.country_iso3 || ''
  const scenario = scenarios.data.find((s) => s.country_iso3 === activeIso3)
  const historical = timeseries.data
    .filter((r) => r.country_iso3 === activeIso3 && r.carbon_intensity_gdp !== null)
    .sort((a, b) => a.year - b.year)

  const ordered = scenario ? scenario.forecast_p05 <= scenario.forecast_p50 && scenario.forecast_p50 <= scenario.forecast_p95 : null

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Scenario Explorer</h1>
          <p className="mt-1 max-w-2xl text-sm text-[var(--color-text-muted)]">
            Forward uncertainty range for carbon intensity of GDP. Production method:{' '}
            <ProductionTag>empirical_bootstrap_v1</ProductionTag>
          </p>
        </div>
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
      </div>

      {scenario ? (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard label="Origin year" value={scenario.origin_year} />
            <StatCard label="Target year" value={scenario.target_year} />
            <StatCard label="Horizon" value={`${scenario.scenario_horizon_years}y`} />
            <StatCard label="Simulations" value={scenario.simulation_count.toLocaleString()} />
          </div>

          <Card
            title="Historical trajectory + forward scenario fan"
            subtitle={ordered ? 'P5 ≤ P50 ≤ P95 (verified)' : 'Ordering could not be verified'}
          >
            {historical.length > 0 ? (
              <FanChart historical={historical} scenario={scenario} />
            ) : (
              <ChartUnavailable reason="No historical carbon-intensity trajectory available." />
            )}
          </Card>

          <div className="grid grid-cols-3 gap-4">
            <StatCard label="P5" value={formatNumber(scenario.forecast_p05, 3)} />
            <StatCard label="P50 (median)" value={formatNumber(scenario.forecast_p50, 3)} />
            <StatCard label="P95" value={formatNumber(scenario.forecast_p95, 3)} />
          </div>

          <Card title="Research methods not used in production">
            <p className="text-sm text-[var(--color-text-muted)]">
              Recency-weighted and regime-aware bootstrap variants were researched in M7 but were{' '}
              <strong>not promoted to production</strong>: gains were small, country-level robustness
              failed leave-one-out testing, and historical P5-P95 coverage remained below the nominal
              90% target either way. Only <ProductionTag>empirical_bootstrap_v1</ProductionTag> is used
              for the forecast shown above.
            </p>
            <p className="mt-2">
              <ResearchTag>recency_weighted_bootstrap, regime_aware_bootstrap — rejected</ResearchTag>
            </p>
          </Card>
        </>
      ) : (
        <ChartUnavailable reason="No scenario projection available for this country." />
      )}
    </div>
  )
}

function FanChart({
  historical,
  scenario,
}: {
  historical: { year: number; carbon_intensity_gdp: number | null }[]
  scenario: { origin_year: number; target_year: number; forecast_p05: number; forecast_p50: number; forecast_p95: number; deterministic_baseline: number | null }
}) {
  const years = [...historical.map((h) => h.year), scenario.target_year]
  const historicalSeries = years.map((y) => {
    const h = historical.find((r) => r.year === y)
    return h ? h.carbon_intensity_gdp : null
  })
  const p50Series = years.map((y) => (y === scenario.target_year ? scenario.forecast_p50 : null))
  const bandLow = years.map((y) => (y === scenario.target_year ? scenario.forecast_p05 : null))
  const bandHigh = years.map((y) =>
    y === scenario.target_year ? scenario.forecast_p95 - scenario.forecast_p05 : null,
  )

  const option: EChartsOption = {
    legend: { top: 0, textStyle: { color: 'var(--color-text-muted)' } },
    xAxis: { type: 'category', data: years },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: 'var(--color-chart-grid)' } } },
    series: [
      { type: 'line', name: 'Historical', data: historicalSeries, showSymbol: false, itemStyle: { color: '#1f5f8b' } },
      { type: 'bar', name: 'P5', data: bandLow, stack: 'band', itemStyle: { color: 'transparent' }, silent: true, barMaxWidth: 20 },
      { type: 'bar', name: 'P5–P95 range', data: bandHigh, stack: 'band', itemStyle: { color: '#8ab6d640' }, barMaxWidth: 20 },
      { type: 'scatter', name: 'P50 (median forecast)', data: p50Series, itemStyle: { color: '#144a6e' }, symbolSize: 10 },
    ],
  }
  return (
    <Chart
      option={option}
      ariaLabel="Historical carbon intensity with forward scenario uncertainty fan"
      summary={`Historical trajectory through ${scenario.origin_year}, forecast for ${scenario.target_year}: P5 ${scenario.forecast_p05.toFixed(3)}, median ${scenario.forecast_p50.toFixed(3)}, P95 ${scenario.forecast_p95.toFixed(3)}.`}
    />
  )
}
