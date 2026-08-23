import { useId, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { CountryIndexEntry } from '../lib/schemas'

export function CountrySearch({ countries }: { countries: CountryIndexEntry[] }) {
  const [query, setQuery] = useState('')
  const navigate = useNavigate()
  const listId = useId()

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return []
    return countries
      .filter(
        (c) => c.country_name.toLowerCase().includes(q) || c.country_iso3.toLowerCase().includes(q),
      )
      .slice(0, 8)
  }, [countries, query])

  function go(iso3: string) {
    setQuery('')
    navigate(`/country/${iso3}`)
  }

  return (
    <div className="relative w-full max-w-xs">
      <label htmlFor="country-search" className="sr-only">
        Search countries
      </label>
      <input
        id="country-search"
        type="search"
        role="combobox"
        aria-expanded={matches.length > 0}
        aria-controls={listId}
        autoComplete="off"
        placeholder="Search country…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm"
      />
      {matches.length > 0 && (
        <ul
          id={listId}
          className="absolute z-10 mt-1 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] shadow-lg"
        >
          {matches.map((c) => (
            <li key={c.country_iso3}>
              <button
                type="button"
                onClick={() => go(c.country_iso3)}
                className="block w-full px-3 py-2 text-left text-sm hover:bg-[var(--color-surface-inset)]"
              >
                {c.country_name} <span className="text-[var(--color-text-subtle)]">({c.country_iso3})</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
