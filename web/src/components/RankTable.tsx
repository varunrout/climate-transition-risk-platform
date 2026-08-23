import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { CountryOverview } from '../lib/schemas'
import { RiskBadge, ConfidenceBadge } from './Badges'
import { formatScore } from '../lib/format'

type SortKey = 'rank' | 'country_name' | 'score_total' | 'data_confidence_score'

export function RankTable({ countries }: { countries: CountryOverview[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('rank')
  const [ascending, setAscending] = useState(true)

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setAscending((a) => !a)
    } else {
      setSortKey(key)
      setAscending(true)
    }
  }

  const sorted = [...countries].sort((a, b) => {
    const av = a[sortKey]
    const bv = b[sortKey]
    const cmp =
      typeof av === 'string' && typeof bv === 'string' ? av.localeCompare(bv) : Number(av) - Number(bv)
    return ascending ? cmp : -cmp
  })

  const columns: { key: SortKey; label: string }[] = [
    { key: 'rank', label: 'Rank' },
    { key: 'country_name', label: 'Country' },
    { key: 'score_total', label: 'Risk score (v2)' },
    { key: 'data_confidence_score', label: 'Confidence' },
  ]

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px] border-collapse text-sm">
        <caption className="sr-only">
          G20 sovereign transition risk ranking, sortable by column, current production score
          v2_energy
        </caption>
        <thead>
          <tr className="border-b border-[var(--color-border)] text-left text-xs uppercase tracking-wide text-[var(--color-text-subtle)]">
            {columns.map((col) => (
              <th key={col.key} scope="col" className="py-2 pr-4">
                <button
                  type="button"
                  onClick={() => toggleSort(col.key)}
                  className="flex items-center gap-1 font-medium"
                  aria-label={`Sort by ${col.label}`}
                >
                  {col.label}
                  {sortKey === col.key && <span aria-hidden="true">{ascending ? '↑' : '↓'}</span>}
                </button>
              </th>
            ))}
            <th scope="col" className="py-2 pr-4">
              Risk band
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((country) => (
            <tr
              key={country.country_iso3}
              className="border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-surface-inset)]"
            >
              <td className="py-2 pr-4 tabular-nums">{country.rank}</td>
              <td className="py-2 pr-4">
                <Link
                  to={`/country/${country.country_iso3}`}
                  className="font-medium text-[var(--color-accent-strong)] underline-offset-2 hover:underline"
                >
                  {country.country_name}
                </Link>{' '}
                <span className="text-[var(--color-text-subtle)]">{country.country_iso3}</span>
              </td>
              <td className="py-2 pr-4 tabular-nums">{formatScore(country.score_total)}</td>
              <td className="py-2 pr-4">
                <ConfidenceBadge score={country.data_confidence_score} />
              </td>
              <td className="py-2 pr-4">
                <RiskBadge band={country.rank_band} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
