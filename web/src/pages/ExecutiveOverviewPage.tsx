import { Suspense, lazy, useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import { useCountries, useCountryOverview, useRiskComponents, useRunMetadata } from '../lib/queries'
import { LoadingState, ErrorState } from '../components/StatusStates'
import { Card, StatCard } from '../components/Card'
import { RankTable } from '../components/RankTable'
import { CountrySearch } from '../components/CountrySearch'
import { Chart } from '../components/Chart'
import { ProductionTag } from '../components/Badges'
import { formatDate, formatScore } from '../lib/format'

const RiskMap = lazy(() => import('../components/RiskMap').then((m) => ({ default: m.RiskMap })))

export function ExecutiveOverviewPage() {
  const overview = useCountryOverview()
  const countries = useCountries()
  const runMetadata = useRunMetadata()
  const components = useRiskComponents()

  if (overview.isPending || countries.isPending || runMetadata.isPending) {
    return <LoadingState label="Loading executive overview…" />
  }
  if (overview.isError) return <ErrorState error={overview.error} />
  if (countries.isError) return <ErrorState error={countries.error} />
  if (runMetadata.isError) return <ErrorState error={runMetadata.error} />

  const rows = overview.data
  const avgConfidence = mean(rows.map((r) => r.data_confidence_score))
  const highest = [...rows].sort((a, b) => a.rank - b.rank).slice(0, 3)
  const lowest = [...rows].sort((a, b) => b.rank - a.rank).slice(0, 3)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Executive Overview</h1>
          <p className="mt-1 max-w-2xl text-sm text-[var(--color-text-muted)]">
            Which G20 sovereigns currently carry the greatest climate transition risk, and why?
            Ranked by the production <ProductionTag>v2_energy</ProductionTag> score, model-eligible
            year {runMetadata.data.latest_model_eligible_year ?? '—'}, published{' '}
            {formatDate(runMetadata.data.completed_at)}.
          </p>
        </div>
        <CountrySearch countries={countries.data} />
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Countries covered" value={rows.length} />
        <StatCard
          label="Highest risk"
          value={highest[0]?.country_iso3 ?? '—'}
          hint={highest[0] ? formatScore(highest[0].score_total) : undefined}
        />
        <StatCard
          label="Lowest risk"
          value={lowest[0]?.country_iso3 ?? '—'}
          hint={lowest[0] ? formatScore(lowest[0].score_total) : undefined}
        />
        <StatCard label="Avg. data confidence" value={Math.round(avgConfidence)} hint="out of 100" />
      </div>

      <Card title="Risk by country" subtitle="Click a country to open its profile.">
        <Suspense fallback={<LoadingState label="Loading map…" />}>
          <RiskMap countries={rows} />
        </Suspense>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Transition risk distribution">
          <DistributionChart scores={rows.map((r) => r.score_total)} />
        </Card>
        <Card title="Average risk-driver contribution" subtitle="Mean component score across all countries, active score">
          {components.isPending && <LoadingState label="Loading component breakdown…" />}
          {components.isError && <ErrorState error={components.error} />}
          {components.data && <DriverPreviewChart components={components.data} />}
        </Card>
      </div>

      <Card title="Sovereign risk ranking" subtitle="Sortable. Confidence encoded separately from risk.">
        <RankTable countries={rows} />
      </Card>
    </div>
  )
}

function mean(values: (number | null)[]): number {
  const numeric = values.filter((v): v is number => v !== null && !Number.isNaN(v))
  if (numeric.length === 0) return 0
  return numeric.reduce((a, b) => a + b, 0) / numeric.length
}

function DistributionChart({ scores }: { scores: number[] }) {
  const buckets = useMemo(() => {
    const bucketSize = 10
    const counts = new Array(10).fill(0)
    for (const s of scores) {
      const idx = Math.min(9, Math.max(0, Math.floor(s / bucketSize)))
      counts[idx] += 1
    }
    return counts
  }, [scores])

  const option: EChartsOption = {
    xAxis: {
      type: 'category',
      data: buckets.map((_, i) => `${i * 10}-${i * 10 + 9}`),
      axisLine: { lineStyle: { color: 'var(--color-chart-axis)' } },
    },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: 'var(--color-chart-grid)' } } },
    series: [{ type: 'bar', data: buckets, itemStyle: { color: '#1f5f8b' }, barMaxWidth: 28 }],
  }
  return (
    <Chart
      option={option}
      ariaLabel="Histogram of transition risk scores across covered countries"
      summary={`Score distribution across ${scores.length} countries, in bins of 10 points from 0 to 100.`}
    />
  )
}

function DriverPreviewChart({
  components,
}: {
  components: { component_name: string; component_score: number | null; is_active_score: boolean }[]
}) {
  const active = components.filter((c) => c.is_active_score && c.component_score !== null)
  const byComponent = new Map<string, number[]>()
  for (const c of active) {
    const list = byComponent.get(c.component_name) ?? []
    list.push(c.component_score as number)
    byComponent.set(c.component_name, list)
  }
  const entries = [...byComponent.entries()].map(([name, values]) => ({
    name,
    avg: values.reduce((a, b) => a + b, 0) / values.length,
  }))

  const option: EChartsOption = {
    xAxis: { type: 'value', max: 100, splitLine: { lineStyle: { color: 'var(--color-chart-grid)' } } },
    yAxis: { type: 'category', data: entries.map((e) => e.name) },
    series: [{ type: 'bar', data: entries.map((e) => e.avg), itemStyle: { color: '#e67e22' }, barMaxWidth: 20 }],
  }
  return (
    <Chart
      option={option}
      ariaLabel="Average contribution of each risk component to the production score"
      summary={entries.map((e) => `${e.name}: ${e.avg.toFixed(1)}`).join(', ')}
    />
  )
}
