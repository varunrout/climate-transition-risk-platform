export function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toLocaleString('en-GB', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function formatScore(value: number | null | undefined): string {
  return formatNumber(value, 1)
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${formatNumber(value, digits)}%`
}

export function formatSignedPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${formatNumber(value, digits)} pp`
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('en-GB', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
    timeZoneName: 'short',
  })
}

export function formatRank(rank: number | null | undefined, total: number): string {
  if (rank === null || rank === undefined) return '—'
  return `#${rank} of ${total}`
}

const RISK_COLORS: Record<string, string> = {
  high: 'var(--color-risk-high)',
  elevated: 'var(--color-risk-elevated)',
  moderate: 'var(--color-risk-moderate)',
  low: 'var(--color-risk-low)',
}

export function riskColorForBand(band: string | null | undefined): string {
  return RISK_COLORS[(band ?? '').toLowerCase()] ?? RISK_COLORS.low
}

export function riskLabelForBand(band: string | null | undefined): string {
  switch ((band ?? '').toLowerCase()) {
    case 'high':
      return 'High risk'
    case 'elevated':
      return 'Elevated risk'
    case 'moderate':
      return 'Moderate risk'
    default:
      return 'Lower risk'
  }
}

export function confidenceLabel(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'Unknown confidence'
  if (score >= 80) return 'High confidence'
  if (score >= 50) return 'Medium confidence'
  return 'Low confidence'
}

export function confidenceColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'var(--color-confidence-low)'
  if (score >= 80) return 'var(--color-confidence-high)'
  if (score >= 50) return 'var(--color-confidence-medium)'
  return 'var(--color-confidence-low)'
}
