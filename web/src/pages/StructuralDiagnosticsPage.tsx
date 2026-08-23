import { useState } from 'react'
import { useCountries, useRegimeDiagnostics } from '../lib/queries'
import { LoadingState, ErrorState, ChartUnavailable } from '../components/StatusStates'
import { Card } from '../components/Card'
import { ResearchTag } from '../components/Badges'
import { formatNumber } from '../lib/format'

export function StructuralDiagnosticsPage() {
  const countries = useCountries()
  const regimes = useRegimeDiagnostics()
  const [selected, setSelected] = useState('')

  if (countries.isPending || regimes.isPending) return <LoadingState label="Loading structural diagnostics…" />
  if (countries.isError) return <ErrorState error={countries.error} />
  if (regimes.isError) return <ErrorState error={regimes.error} />

  const activeIso3 = selected || countries.data[0]?.country_iso3 || ''
  const rows = regimes.data.filter((r) => r.country_iso3 === activeIso3)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Structural Change Diagnostics</h1>
          <p className="mt-1 text-sm">
            <ResearchTag>M7 structural-break research</ResearchTag>
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

      <Card>
        <p className="rounded-md bg-[var(--color-research)]/10 p-3 text-sm font-semibold text-[var(--color-research)]">
          STRUCTURAL-BREAK DIAGNOSTICS ARE RESEARCH/INTERPRETATION ONLY. THEY DO NOT SELECT THE
          PRODUCTION FORECAST.
        </p>
        <p className="mt-3 text-sm text-[var(--color-text-muted)]">
          Formal regime-aware modelling was tested in M7 and did <strong>not</strong> outperform the
          simpler production controls sufficiently for promotion: recency and regime-aware bootstrap
          variants showed small gains that failed leave-one-country-out and leave-one-origin-out
          robustness checks, so the existing <code className="rounded bg-[var(--color-surface-inset)] px-1">empirical_bootstrap_v1</code>{' '}
          remains in production. This negative result is preserved here, not hidden.
        </p>
      </Card>

      <Card title="Detected regimes by series">
        {rows.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left text-xs uppercase tracking-wide text-[var(--color-text-subtle)]">
                  <th className="py-2 pr-4">Series</th>
                  <th className="py-2 pr-4">Regime label</th>
                  <th className="py-2 pr-4">Direction</th>
                  <th className="py-2 pr-4">Break count</th>
                  <th className="py-2 pr-4">Break year</th>
                  <th className="py-2 pr-4">Pre-break slope</th>
                  <th className="py-2 pr-4">Post-break slope</th>
                  <th className="py-2 pr-4">Slope delta</th>
                  <th className="py-2 pr-4">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.series_name} className="border-b border-[var(--color-border)] last:border-0">
                    <td className="py-2 pr-4 font-medium">{r.series_name}</td>
                    <td className="py-2 pr-4">{r.current_regime_label ?? '—'}</td>
                    <td className="py-2 pr-4">{r.regime_direction ?? '—'}</td>
                    <td className="py-2 pr-4 tabular-nums">{r.break_count}</td>
                    <td className="py-2 pr-4 tabular-nums">{r.strongest_break_year ?? '—'}</td>
                    <td className="py-2 pr-4 tabular-nums">{formatNumber(r.pre_break_slope, 4)}</td>
                    <td className="py-2 pr-4 tabular-nums">{formatNumber(r.post_break_slope, 4)}</td>
                    <td className="py-2 pr-4 tabular-nums">{formatNumber(r.slope_delta, 4)}</td>
                    <td className="py-2 pr-4 tabular-nums">{formatNumber(r.regime_confidence, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <ChartUnavailable reason="No structural diagnostics available for this country." />
        )}
      </Card>

      <Card title="Production-usage flags">
        {rows.length > 0 ? (
          <ul className="flex flex-col gap-1 text-sm">
            {rows.map((r) => (
              <li key={r.series_name}>
                <span className="font-medium">{r.series_name}</span>: used in production score —{' '}
                <strong>{r.used_in_production_score ? 'yes' : 'no'}</strong>; used in production
                scenario — <strong>{r.used_in_production_scenario ? 'yes' : 'no'}</strong> ({r.diagnostic_status})
              </li>
            ))}
          </ul>
        ) : (
          <ChartUnavailable />
        )}
      </Card>
    </div>
  )
}
