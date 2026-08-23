import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { geoNaturalEarth1, geoPath } from 'd3-geo'
import { buildWorldGeoJson } from '../lib/worldMap'
import type { CountryOverview } from '../lib/schemas'

const VIEWBOX_WIDTH = 960
const VIEWBOX_HEIGHT = 500

// Mirrors the --color-risk-* tokens as literal hex values (kept in sync
// manually; see src/index.css) -- the risk fill is computed per-country
// from a numeric score, so it cannot be a static CSS custom property the
// way the uncovered-country fill below is.
const RISK_COLOR_STOPS: [number, string][] = [
  [0, '#2e86ab'],
  [1 / 3, '#d4ac0d'],
  [2 / 3, '#e67e22'],
  [1, '#c0392b'],
]

function riskColor(score: number, min: number, max: number): string {
  const t = max > min ? (score - min) / (max - min) : 0
  const clamped = Math.min(1, Math.max(0, t))
  for (let i = 0; i < RISK_COLOR_STOPS.length - 1; i++) {
    const [t0, c0] = RISK_COLOR_STOPS[i]
    const [t1, c1] = RISK_COLOR_STOPS[i + 1]
    if (clamped >= t0 && clamped <= t1) {
      const localT = t1 > t0 ? (clamped - t0) / (t1 - t0) : 0
      return mixHex(c0, c1, localT)
    }
  }
  return RISK_COLOR_STOPS[RISK_COLOR_STOPS.length - 1][1]
}

function mixHex(a: string, b: string, t: number): string {
  const pa = hexToRgb(a)
  const pb = hexToRgb(b)
  const r = Math.round(pa.r + (pb.r - pa.r) * t)
  const g = Math.round(pa.g + (pb.g - pa.g) * t)
  const bl = Math.round(pa.b + (pb.b - pa.b) * t)
  return `rgb(${r}, ${g}, ${bl})`
}

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const n = Number.parseInt(hex.slice(1), 16)
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 }
}

type HoverInfo = { iso3: string; name: string; score: number; rank: number; x: number; y: number }

/**
 * Static-projection SVG choropleth (no roam/zoom/pan) using d3-geo's
 * geoPath, which clips every feature against the projection sphere before
 * producing path data -- this is what actually fixes the antimeridian
 * streak the previous ECharts `map` series renderer produced for Russia
 * (see worldMap.ts's buildWorldGeoJson doc comment): a plain equirectangular
 * projection with no sphere-aware clipping draws a straight line connecting
 * a geometry's two antimeridian-split halves; geoPath does not.
 */
export function RiskMap({ countries }: { countries: CountryOverview[] }) {
  const navigate = useNavigate()
  const [hover, setHover] = useState<HoverInfo | null>(null)

  const byIso3 = useMemo(() => new Map(countries.map((c) => [c.country_iso3, c])), [countries])
  const scores = countries.map((c) => c.score_total)
  const min = Math.min(...scores)
  const max = Math.max(...scores)

  const paths = useMemo(() => {
    const geojson = buildWorldGeoJson()
    const proj = geoNaturalEarth1().fitSize([VIEWBOX_WIDTH, VIEWBOX_HEIGHT], geojson)
    const path = geoPath(proj)
    return geojson.features.map((f) => ({
      iso3: (f.properties as { iso3?: string } | null)?.iso3,
      d: path(f) ?? '',
    }))
  }, [])

  function openCountry(iso3: string) {
    if (byIso3.has(iso3)) navigate(`/country/${iso3}`)
  }

  return (
    <div role="img" aria-label="World map coloured by transition risk score for covered G20 sovereigns">
      <div style={{ position: 'relative' }}>
        <svg
          viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
          style={{ width: '100%', height: 'auto', display: 'block' }}
          role="presentation"
        >
          {paths.map(({ iso3, d }, i) => {
            const country = iso3 ? byIso3.get(iso3) : undefined
            const fill = country
              ? riskColor(country.score_total, min, max)
              : 'var(--color-surface-inset)'
            const interactive = Boolean(country)
            return (
              <path
                key={iso3 ?? `feature-${i}`}
                d={d}
                fill={fill}
                stroke="var(--color-surface)"
                strokeWidth={0.5}
                tabIndex={interactive ? 0 : undefined}
                role={interactive ? 'button' : undefined}
                aria-label={
                  country
                    ? `${country.country_name}: risk score ${country.score_total.toFixed(1)}, rank ${country.rank} of ${countries.length}`
                    : undefined
                }
                style={interactive ? { cursor: 'pointer' } : undefined}
                onClick={() => iso3 && openCountry(iso3)}
                onKeyDown={(e) => {
                  if (iso3 && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault()
                    openCountry(iso3)
                  }
                }}
                onMouseEnter={(e) => {
                  if (!country || !iso3) return
                  const rect = e.currentTarget.ownerSVGElement?.getBoundingClientRect()
                  setHover({
                    iso3,
                    name: country.country_name,
                    score: country.score_total,
                    rank: country.rank,
                    x: rect ? e.clientX - rect.left : 0,
                    y: rect ? e.clientY - rect.top : 0,
                  })
                }}
                onFocus={() => {
                  if (!country || !iso3) return
                  setHover({ iso3, name: country.country_name, score: country.score_total, rank: country.rank, x: 0, y: 0 })
                }}
                onMouseLeave={() => setHover(null)}
                onBlur={() => setHover(null)}
              />
            )
          })}
        </svg>
        {hover && (
          <div
            className="pointer-events-none absolute z-10 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-xs shadow-md"
            style={{ left: hover.x + 12, top: hover.y + 12 }}
          >
            <strong>{hover.name}</strong>
            <br />
            Transition risk score: {hover.score.toFixed(1)}
            <br />
            Rank #{hover.rank} of {countries.length}
          </div>
        )}
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
        <span>Lower risk</span>
        <span
          className="h-2 flex-1 rounded"
          style={{
            background: `linear-gradient(to right, ${RISK_COLOR_STOPS.map(([, c]) => c).join(', ')})`,
            maxWidth: 200,
          }}
        />
        <span>Higher risk</span>
      </div>
      <p className="sr-only">
        Interactive map, {countries.length} covered countries, coloured by transition risk score.
        Each covered country is keyboard-focusable and activates with Enter or Space. Use the
        sortable ranking table below for the same information in accessible tabular form.
      </p>
    </div>
  )
}
