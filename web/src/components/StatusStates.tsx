import { BundleError } from '../lib/dataClient'

export function LoadingState({ label = 'Loading data…' }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-6 text-[var(--color-text-muted)]"
    >
      <span
        className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-border-strong)] border-t-[var(--color-accent)]"
        aria-hidden="true"
      />
      <span>{label}</span>
    </div>
  )
}

export function ErrorState({ error, title = 'Could not load data' }: { error: unknown; title?: string }) {
  const isBundleError = error instanceof BundleError
  const detail = error instanceof Error ? error.message : String(error)
  const guidance = isBundleError
    ? bundleErrorGuidance(error)
    : 'An unexpected error occurred while loading this page.'

  return (
    <div
      role="alert"
      className="rounded-lg border border-[var(--color-negative)]/40 bg-[var(--color-surface)] p-6"
    >
      <p className="font-semibold text-[var(--color-negative)]">{title}</p>
      <p className="mt-1 text-sm text-[var(--color-text-muted)]">{guidance}</p>
      <details className="mt-3 text-xs text-[var(--color-text-subtle)]">
        <summary className="cursor-pointer select-none">Technical detail</summary>
        <pre className="mt-2 whitespace-pre-wrap break-words">{detail}</pre>
      </details>
    </div>
  )
}

function bundleErrorGuidance(error: BundleError): string {
  switch (error.kind) {
    case 'missing':
      return 'The published data bundle could not be found. If you are running this locally, run `climate-risk build-web` and copy data/lake/gold/web/*.json into web/public/data/.'
    case 'invalid_json':
      return 'A data file was found but is not valid JSON. The bundle may be corrupted or truncated.'
    case 'schema_mismatch':
      return 'This build of the dashboard does not support the published bundle schema version. Rebuild the frontend against a compatible bundle.'
    case 'schema_invalid':
      return 'A data file does not match the shape this dashboard expects. The publisher and frontend contracts may be out of sync.'
    default:
      return 'The data bundle could not be loaded.'
  }
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface)] p-6 text-center text-[var(--color-text-muted)]">
      {message}
    </div>
  )
}

export function CountryNotFound({ iso3 }: { iso3: string }) {
  return (
    <div role="alert" className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-8 text-center">
      <p className="text-lg font-semibold">Country not found</p>
      <p className="mt-2 text-sm text-[var(--color-text-muted)]">
        No country with ISO3 code "{iso3}" exists in the current published bundle.
      </p>
    </div>
  )
}

export function ChartUnavailable({ reason = 'Insufficient data to render this chart.' }: { reason?: string }) {
  return (
    <div className="flex h-full min-h-[160px] items-center justify-center rounded-md border border-dashed border-[var(--color-border)] p-4 text-center text-sm text-[var(--color-text-subtle)]">
      {reason}
    </div>
  )
}
