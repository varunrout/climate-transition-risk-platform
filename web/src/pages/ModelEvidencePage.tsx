import type { EChartsOption } from 'echarts'
import { useBacktestMetrics } from '../lib/queries'
import { LoadingState, ErrorState, ChartUnavailable } from '../components/StatusStates'
import { Card } from '../components/Card'
import { Chart } from '../components/Chart'
import { formatNumber, formatPercent } from '../lib/format'

export function ModelEvidencePage() {
  const backtest = useBacktestMetrics()

  if (backtest.isPending) return <LoadingState label="Loading model evidence…" />
  if (backtest.isError) return <ErrorState error={backtest.error} />

  const summaryRows = backtest.data.filter((r) => r.metric_grain === 'summary')
  const detailRows = backtest.data.filter((r) => r.metric_grain === 'country_origin')

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Model Evidence</h1>
        <p className="mt-1 max-w-2xl text-sm text-[var(--color-text-muted)]">
          Rolling-origin backtest results across historical splits. Better point forecasts do{' '}
          <strong>not</strong> automatically imply calibrated uncertainty -- both are shown separately
          below.
        </p>
      </div>

      <Card title="Model variant comparison" subtitle="Rolling-origin summary metrics">
        {summaryRows.length > 0 ? (
          <SummaryTable rows={summaryRows} />
        ) : (
          <ChartUnavailable reason="No summary backtest metrics available." />
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Mean absolute error by model variant">
          {summaryRows.length > 0 ? <MaeChart rows={summaryRows} /> : <ChartUnavailable />}
        </Card>
        <Card
          title="90% interval coverage vs nominal"
          subtitle="Gap below the dashed line indicates historical undercoverage"
        >
          {summaryRows.length > 0 ? <CoverageChart rows={summaryRows} /> : <ChartUnavailable />}
        </Card>
      </div>

      <Card title="Coverage calibration">
        <p className="text-sm text-[var(--color-text-muted)]">
          The production empirical bootstrap's realised 90% interval coverage across rolling-origin
          splits has historically come in <strong>below the nominal 90% target</strong> -- this
          calibration gap is not hidden. See{' '}
          <code className="rounded bg-[var(--color-surface-inset)] px-1">docs/m7_phase4_report.md</code>{' '}
          for the full evidence behind the decision to keep the existing empirical bootstrap in
          production rather than promote a regime-aware or recency-weighted variant.
        </p>
      </Card>

      <Card title="Country / origin breakdown" subtitle="Individual rolling-origin splits, production model variant">
        {detailRows.length > 0 ? (
          <DetailTable rows={detailRows.slice(0, 50)} total={detailRows.length} />
        ) : (
          <ChartUnavailable reason="No per-split backtest detail available." />
        )}
      </Card>
    </div>
  )
}

type SummaryRow = {
  model_variant: string
  mae: number | null
  rmse: number | null
  coverage_90: number | null
  nominal_coverage_90: number | null
  calibration_gap_90: number | null
  n_splits: number | null
}

function SummaryTable({ rows }: { rows: SummaryRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-sm">
        <thead>
          <tr className="border-b border-[var(--color-border)] text-left text-xs uppercase tracking-wide text-[var(--color-text-subtle)]">
            <th className="py-2 pr-4">Model variant</th>
            <th className="py-2 pr-4">MAE</th>
            <th className="py-2 pr-4">RMSE</th>
            <th className="py-2 pr-4">90% coverage</th>
            <th className="py-2 pr-4">Calibration gap</th>
            <th className="py-2 pr-4">Splits</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.model_variant} className="border-b border-[var(--color-border)] last:border-0">
              <td className="py-2 pr-4 font-medium">{r.model_variant}</td>
              <td className="py-2 pr-4 tabular-nums">{formatNumber(r.mae, 4)}</td>
              <td className="py-2 pr-4 tabular-nums">{formatNumber(r.rmse, 4)}</td>
              <td className="py-2 pr-4 tabular-nums">{formatPercent((r.coverage_90 ?? 0) * 100)}</td>
              <td className="py-2 pr-4 tabular-nums">{formatPercent((r.calibration_gap_90 ?? 0) * 100)}</td>
              <td className="py-2 pr-4 tabular-nums">{r.n_splits ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function MaeChart({ rows }: { rows: SummaryRow[] }) {
  const withMae = rows.filter((r) => r.mae !== null)
  const option: EChartsOption = {
    xAxis: { type: 'value', splitLine: { lineStyle: { color: 'var(--color-chart-grid)' } } },
    yAxis: { type: 'category', data: withMae.map((r) => r.model_variant) },
    series: [{ type: 'bar', data: withMae.map((r) => r.mae), itemStyle: { color: '#1f5f8b' }, barMaxWidth: 20 }],
  }
  return <Chart option={option} ariaLabel="Mean absolute error by model variant" />
}

function CoverageChart({ rows }: { rows: SummaryRow[] }) {
  const withCoverage = rows.filter((r) => r.coverage_90 !== null)
  const option: EChartsOption = {
    xAxis: { type: 'category', data: withCoverage.map((r) => r.model_variant) },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { color: 'var(--color-chart-grid)' } } },
    series: [
      {
        type: 'bar',
        data: withCoverage.map((r) => (r.coverage_90 ?? 0) * 100),
        itemStyle: { color: '#e67e22' },
        barMaxWidth: 24,
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { type: 'dashed', color: 'var(--color-text-subtle)' },
          data: [{ yAxis: 90, label: { formatter: 'Nominal 90%' } }],
        },
      },
    ],
  }
  return (
    <Chart
      option={option}
      ariaLabel="Realised 90% interval coverage compared to the nominal 90% target"
      summary={withCoverage
        .map((r) => `${r.model_variant}: ${((r.coverage_90 ?? 0) * 100).toFixed(1)}% vs 90% nominal`)
        .join('; ')}
    />
  )
}

type DetailRow = {
  country_iso3: string | null
  origin_year: number | null
  target_year: number | null
  absolute_error: number | null
  forecast_p50: number | null
  actual: number | null
}

function DetailTable({ rows, total }: { rows: DetailRow[]; total: number }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-sm">
        <thead>
          <tr className="border-b border-[var(--color-border)] text-left text-xs uppercase tracking-wide text-[var(--color-text-subtle)]">
            <th className="py-2 pr-4">Country</th>
            <th className="py-2 pr-4">Origin → target</th>
            <th className="py-2 pr-4">Actual</th>
            <th className="py-2 pr-4">Forecast (P50)</th>
            <th className="py-2 pr-4">Abs. error</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-[var(--color-border)] last:border-0">
              <td className="py-2 pr-4">{r.country_iso3 ?? '—'}</td>
              <td className="py-2 pr-4 tabular-nums">
                {r.origin_year ?? '—'} → {r.target_year ?? '—'}
              </td>
              <td className="py-2 pr-4 tabular-nums">{formatNumber(r.actual, 3)}</td>
              <td className="py-2 pr-4 tabular-nums">{formatNumber(r.forecast_p50, 3)}</td>
              <td className="py-2 pr-4 tabular-nums">{formatNumber(r.absolute_error, 3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {total > rows.length && (
        <p className="mt-2 text-xs text-[var(--color-text-subtle)]">
          Showing {rows.length} of {total} splits.
        </p>
      )}
    </div>
  )
}
