import { useManifest, useRunMetadata, useCountries } from '../lib/queries'
import { LoadingState, ErrorState } from '../components/StatusStates'
import { Card, StatCard } from '../components/Card'
import { formatDate } from '../lib/format'

export function ProvenancePage() {
  const manifest = useManifest()
  const runMetadata = useRunMetadata()
  const countries = useCountries()

  if (manifest.isPending || runMetadata.isPending || countries.isPending) {
    return <LoadingState label="Loading provenance…" />
  }
  if (manifest.isError) return <ErrorState error={manifest.error} />
  if (runMetadata.isError) return <ErrorState error={runMetadata.error} />
  if (countries.isError) return <ErrorState error={countries.error} />

  const m = manifest.data
  const r = runMetadata.data

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Data Quality &amp; Provenance</h1>
        <p className="mt-1 max-w-2xl text-sm text-[var(--color-text-muted)]">
          Not a real-time system. This page makes reproducibility of the published run tangible.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <StatCard label="Publish status" value={r.publish_status ?? '—'} />
        <StatCard label="Run ID" value={<span className="font-mono text-sm">{r.run_id?.slice(0, 12) ?? '—'}</span>} />
        <StatCard label="Completed at" value={formatDate(r.completed_at)} />
        <StatCard label="Git SHA" value={<span className="font-mono text-sm">{r.git_sha?.slice(0, 12) ?? '—'}</span>} />
        <StatCard label="Image digest" value={<span className="font-mono text-xs">{r.image_digest ?? 'not set'}</span>} />
        <StatCard label="Model-eligible year" value={r.latest_model_eligible_year ?? '—'} />
        <StatCard label="Active score version" value={r.active_score_version ?? '—'} />
        <StatCard label="Component version" value={r.component_version ?? '—'} />
        <StatCard label="Production scenario" value={r.production_scenario_method ?? '—'} />
        <StatCard label="Country coverage" value={countries.data.length} />
      </div>

      <Card title="Source snapshots">
        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {Object.entries(m.source_snapshot_ids).map(([source, id]) => (
            <div key={source}>
              <dt className="text-xs text-[var(--color-text-subtle)]">{source}</dt>
              <dd className="font-mono text-sm">{id ?? '—'}</dd>
            </div>
          ))}
        </dl>
      </Card>

      <Card title="Web bundle manifest" subtitle={`schema ${m.schema_version} · generated ${formatDate(m.generated_at)}`}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-xs uppercase tracking-wide text-[var(--color-text-subtle)]">
                <th className="py-2 pr-4">File</th>
                <th className="py-2 pr-4">Rows</th>
                <th className="py-2 pr-4">SHA-256</th>
              </tr>
            </thead>
            <tbody>
              {m.files.map((f) => (
                <tr key={f.name} className="border-b border-[var(--color-border)] last:border-0">
                  <td className="py-2 pr-4">{f.name}</td>
                  <td className="py-2 pr-4 tabular-nums">{f.row_count}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{f.sha256.slice(0, 16)}…</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 font-mono text-xs text-[var(--color-text-subtle)]">
          Bundle hash: {m.web_bundle_hash}
        </p>
        <p className="mt-1 text-xs text-[var(--color-text-subtle)]">
          Config hash: {m.config_hash ?? '—'}
        </p>
      </Card>
    </div>
  )
}
