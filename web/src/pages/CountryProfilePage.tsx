import { useParams } from 'react-router-dom'
import type { EChartsOption } from 'echarts'
import {
  useCountryOverview,
  useCountryTimeseries,
  useRegimeDiagnostics,
  useRiskComponents,
  useScenarioQuantiles,
} from '../lib/queries'
import { LoadingState, ErrorState, CountryNotFound, ChartUnavailable } from '../components/StatusStates'
import { Card, StatCard } from '../components/Card'
import { Chart } from '../components/Chart'
import { RiskBadge, ConfidenceBadge, ProductionTag, ComparisonTag, ResearchTag } from '../components/Badges'
import { formatRank, formatScore, formatSignedPercent } from '../lib/format'

export function CountryProfilePage() {
  const { iso3 = '' } = useParams()
  const overview = useCountryOverview()
  const timeseries = useCountryTimeseries()
  const components = useRiskComponents()
  const scenarios = useScenarioQuantiles()
  const regimes = useRegimeDiagnostics()

  if (overview.isPending || timeseries.isPending || components.isPending || scenarios.isPending || regimes.isPending) {
    return <LoadingState label={`Loading profile for ${iso3}…`} />
  }
  if (overview.isError) return <ErrorState error={overview.error} />
  if (timeseries.isError) return <ErrorState error={timeseries.error} />
  if (components.isError) return <ErrorState error={components.error} />
  if (scenarios.isError) return <ErrorState error={scenarios.error} />
  if (regimes.isError) return <ErrorState error={regimes.error} />

  const country = overview.data.find((c) => c.country_iso3 === iso3)
  if (!country) return <CountryNotFound iso3={iso3} />

  const series = timeseries.data
    .filter((r) => r.country_iso3 === iso3)
    .sort((a, b) => a.year - b.year)
  const countryComponents = components.data.filter(
    (c) => c.country_iso3 === iso3 && c.is_active_score,
  )
  const scenario = scenarios.data.find((s) => s.country_iso3 === iso3)
  const countryRegimes = regimes.data.filter((r) => r.country_iso3 === iso3)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            {country.country_name} <span className="text-[var(--color-text-subtle)]">({country.country_iso3})</span>
          </h1>
          <p className="text-sm text-[var(--color-text-muted)]">
            {country.region} · {country.income_group}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <RiskBadge band={country.rank_band} />
          <ConfidenceBadge score={country.data_confidence_score} />
        </div>
      </div>

      <Card>
        <p className="text-sm leading-relaxed">{interpret(country)}</p>
      </Card>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Active score (v2)" value={formatScore(country.score_total)} hint={<ProductionTag>v2_energy</ProductionTag>} />
        <StatCard label="Rank" value={formatRank(country.rank, overview.data.length)} />
        <StatCard label="Comparison score (v1)" value={formatScore(country.score_total_v1)} hint={<ComparisonTag>v1</ComparisonTag>} />
        <StatCard
          label="Rank delta (v2 − v1)"
          value={country.rank_delta_v2_minus_v1 !== null ? `${country.rank_delta_v2_minus_v1 > 0 ? '+' : ''}${country.rank_delta_v2_minus_v1}` : '—'}
        />
        <StatCard label="Weight coverage" value={country.weight_coverage !== null ? `${Math.round(country.weight_coverage * 100)}%` : '—'} />
        <StatCard label="Data confidence" value={Math.round(country.data_confidence_score ?? 0)} />
        <StatCard label="Energy confidence" value={country.energy_confidence !== null ? Math.round(country.energy_confidence) : '—'} />
        <StatCard label="Model-eligible year" value={country.latest_transition_year ?? '—'} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Score component decomposition" subtitle="Active score (v2_energy) components">
          {countryComponents.length > 0 ? (
            <ComponentChart
              components={countryComponents.map((c) => ({ name: c.component_name, score: c.component_score }))}
            />
          ) : (
            <ChartUnavailable />
          )}
        </Card>
        <Card title="Carbon intensity trajectory" subtitle="CO2 per unit GDP over time">
          {series.some((r) => r.carbon_intensity_gdp !== null) ? (
            <TrajectoryChart series={series} field="carbon_intensity_gdp" label="Carbon intensity of GDP" />
          ) : (
            <ChartUnavailable />
          )}
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Energy transition indicators" subtitle="Electricity mix over time">
          {series.some((r) => r.low_carbon_share_elec !== null) ? (
            <EnergyMixChart series={series} />
          ) : (
            <ChartUnavailable />
          )}
        </Card>
        <Card
          title="Forward scenario"
          subtitle={scenario ? <ProductionTag>{scenario.scenario_method}</ProductionTag> : undefined}
        >
          {scenario ? <ScenarioFanChart scenario={scenario} /> : <ChartUnavailable reason="No scenario projection available." />}
        </Card>
      </div>

      <Card
        title="Structural change diagnostics"
        subtitle={<ResearchTag>M7 structural-break research</ResearchTag>}
      >
        <p className="mb-3 rounded-md bg-[var(--color-research)]/10 p-2 text-xs font-medium text-[var(--color-research)]">
          STRUCTURAL-BREAK DIAGNOSTICS ARE RESEARCH/INTERPRETATION ONLY. THEY DO NOT SELECT THE
          PRODUCTION FORECAST.
        </p>
        {countryRegimes.length > 0 ? (
          <ul className="flex flex-col gap-2 text-sm">
            {countryRegimes.map((r) => (
              <li key={r.series_name} className="rounded-md border border-[var(--color-border)] p-2">
                <span className="font-medium">{r.series_name}</span>: {r.current_regime_label ?? 'no regime label'} ·
                regime direction {r.regime_direction ?? 'unknown'} · break count {r.break_count}
              </li>
            ))}
          </ul>
        ) : (
          <ChartUnavailable reason="No structural diagnostics available for this country." />
        )}
      </Card>
    </div>
  )
}

function interpret(country: {
  country_name: string
  rank: number
  rank_band: string
  data_confidence_score: number | null
  transition_velocity: number | null
  score_delta_v2_minus_v1: number | null
}): string {
  const parts: string[] = []
  parts.push(
    `${country.country_name} ranks #${country.rank} on the production transition risk score, placing it in the "${country.rank_band}" band.`,
  )
  if (country.transition_velocity !== null) {
    parts.push(
      country.transition_velocity > 0
        ? 'Recent electricity-mix indicators show positive momentum toward lower-carbon generation.'
        : country.transition_velocity < 0
          ? 'Recent electricity-mix indicators show stalled or reversing decarbonisation momentum.'
          : 'Recent electricity-mix momentum is flat.',
    )
  }
  if (country.data_confidence_score !== null && country.data_confidence_score < 60) {
    parts.push('Data confidence for this country is comparatively low; treat the exact score with more caution.')
  }
  if (country.score_delta_v2_minus_v1 !== null && Math.abs(country.score_delta_v2_minus_v1) >= 5) {
    parts.push(
      `Including the energy-transition component changed the score by ${formatSignedPercent(country.score_delta_v2_minus_v1, 1).replace(' pp', ' points')} relative to the v1 comparison score.`,
    )
  }
  return parts.join(' ')
}

function ComponentChart({ components }: { components: { name: string; score: number | null }[] }) {
  const data = components.filter((c) => c.score !== null)
  const option: EChartsOption = {
    xAxis: { type: 'value', max: 100, splitLine: { lineStyle: { color: 'var(--color-chart-grid)' } } },
    yAxis: { type: 'category', data: data.map((d) => d.name) },
    series: [{ type: 'bar', data: data.map((d) => d.score), itemStyle: { color: '#144a6e' }, barMaxWidth: 20 }],
  }
  return <Chart option={option} ariaLabel="Risk score component decomposition" height={220} />
}

function TrajectoryChart({
  series,
  field,
  label,
}: {
  series: { year: number; carbon_intensity_gdp: number | null }[]
  field: 'carbon_intensity_gdp'
  label: string
}) {
  const points = series.filter((r) => r[field] !== null)
  const option: EChartsOption = {
    xAxis: { type: 'category', data: points.map((p) => p.year) },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: 'var(--color-chart-grid)' } } },
    series: [{ type: 'line', name: label, data: points.map((p) => p[field]), showSymbol: false, itemStyle: { color: '#1f5f8b' } }],
  }
  return <Chart option={option} ariaLabel={`${label} over time`} />
}

function EnergyMixChart({
  series,
}: {
  series: { year: number; low_carbon_share_elec: number | null; fossil_share_elec: number | null }[]
}) {
  const points = series.filter((r) => r.low_carbon_share_elec !== null || r.fossil_share_elec !== null)
  const option: EChartsOption = {
    legend: { top: 0, textStyle: { color: 'var(--color-text-muted)' } },
    xAxis: { type: 'category', data: points.map((p) => p.year) },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { color: 'var(--color-chart-grid)' } } },
    series: [
      { type: 'line', name: 'Low-carbon share', data: points.map((p) => p.low_carbon_share_elec), showSymbol: false, itemStyle: { color: '#1e8f6b' } },
      { type: 'line', name: 'Fossil share', data: points.map((p) => p.fossil_share_elec), showSymbol: false, itemStyle: { color: '#c0392b' } },
    ],
  }
  return <Chart option={option} ariaLabel="Low-carbon and fossil electricity share over time" />
}

function ScenarioFanChart({
  scenario,
}: {
  scenario: { origin_year: number; target_year: number; forecast_p05: number; forecast_p50: number; forecast_p95: number; deterministic_baseline: number | null }
}) {
  const categories = [String(scenario.origin_year), String(scenario.target_year)]
  const option: EChartsOption = {
    legend: { top: 0, textStyle: { color: 'var(--color-text-muted)' } },
    xAxis: { type: 'category', data: categories },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: 'var(--color-chart-grid)' } } },
    series: [
      { type: 'bar', name: 'P5', data: [null, scenario.forecast_p05], itemStyle: { color: '#8ab6d6' } },
      { type: 'bar', name: 'P50 (median)', data: [null, scenario.forecast_p50], itemStyle: { color: '#1f5f8b' } },
      { type: 'bar', name: 'P95', data: [null, scenario.forecast_p95], itemStyle: { color: '#144a6e' } },
    ],
  }
  return (
    <Chart
      option={option}
      ariaLabel="Scenario P5, median, and P95 forecast for the target year"
      summary={`P5 ${scenario.forecast_p05.toFixed(2)}, median ${scenario.forecast_p50.toFixed(2)}, P95 ${scenario.forecast_p95.toFixed(2)} for ${scenario.target_year}.`}
    />
  )
}
