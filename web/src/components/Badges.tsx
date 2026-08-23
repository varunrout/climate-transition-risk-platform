import type { ReactNode } from 'react'
import { confidenceColor, confidenceLabel, riskColorForBand, riskLabelForBand } from '../lib/format'

/** Risk is encoded by colour AND label text -- never colour alone. */
export function RiskBadge({ band }: { band: string | null | undefined }) {
  const color = riskColorForBand(band)
  const label = riskLabelForBand(band)
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium"
      style={{ borderColor: color, color }}
    >
      <span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}

/**
 * Confidence uses a distinct shape (a filled square, not a dot) and a
 * separate colour family from risk, so the two are never visually
 * confusable even for a colour-blind reader relying on shape alone.
 */
export function ConfidenceBadge({ score }: { score: number | null | undefined }) {
  const color = confidenceColor(score)
  const label = confidenceLabel(score)
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border px-2.5 py-0.5 text-xs font-medium"
      style={{ borderColor: color, color }}
    >
      <span aria-hidden="true" className="h-2 w-2" style={{ backgroundColor: color }} />
      {label}
      {score !== null && score !== undefined ? ` (${Math.round(score)})` : ''}
    </span>
  )
}

export function ProductionTag({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-[var(--color-positive)]/10 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-positive)]">
      Production · {children}
    </span>
  )
}

export function ResearchTag({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-[var(--color-research)]/10 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-research)]">
      Research only · {children}
    </span>
  )
}

export function ComparisonTag({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-[var(--color-text-subtle)]/10 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-subtle)]">
      Comparison · {children}
    </span>
  )
}
