import { describe, expect, it } from 'vitest'
import { buildWorldGeoJson, NUMERIC_TO_ISO3 } from './worldMap'

describe('worldMap', () => {
  it('covers exactly the 19 G20 sovereigns this platform reports on', () => {
    expect(Object.keys(NUMERIC_TO_ISO3)).toHaveLength(19)
    expect(new Set(Object.values(NUMERIC_TO_ISO3)).size).toBe(19) // no duplicate ISO3 targets
  })

  it('resolves every mapped ISO3 to exactly one feature in the built topology', () => {
    const geojson = buildWorldGeoJson()
    const isoCounts = new Map<string, number>()
    for (const f of geojson.features) {
      const iso3 = (f.properties as { iso3?: string } | null)?.iso3
      if (!iso3) continue
      isoCounts.set(iso3, (isoCounts.get(iso3) ?? 0) + 1)
    }
    for (const iso3 of Object.values(NUMERIC_TO_ISO3)) {
      expect(isoCounts.get(iso3)).toBe(1)
    }
  })

  it('leaves non-covered countries without an iso3 property (rendered as unhighlighted base geography)', () => {
    const geojson = buildWorldGeoJson()
    const covered = new Set(Object.values(NUMERIC_TO_ISO3))
    const uncovered = geojson.features.filter(
      (f) => !covered.has((f.properties as { iso3?: string } | null)?.iso3 ?? ''),
    )
    // The 110m Natural Earth topology has ~170+ countries; only 19 are covered.
    expect(uncovered.length).toBeGreaterThan(100)
    for (const f of uncovered) {
      expect((f.properties as { iso3?: string } | null)?.iso3).toBeUndefined()
    }
  })

  it('produces geometry for every covered country that a geoPath renderer can project without throwing', async () => {
    const { geoNaturalEarth1, geoPath } = await import('d3-geo')
    const geojson = buildWorldGeoJson()
    const projection = geoNaturalEarth1().fitSize([960, 500], geojson)
    const path = geoPath(projection)
    const covered = geojson.features.filter((f) =>
      Object.values(NUMERIC_TO_ISO3).includes((f.properties as { iso3?: string } | null)?.iso3 ?? ''),
    )
    expect(covered).toHaveLength(19)
    for (const f of covered) {
      expect(() => path(f)).not.toThrow()
      expect(path(f)).toBeTruthy()
    }
  })

  it('is cached across calls (same reference, not rebuilt every render)', () => {
    expect(buildWorldGeoJson()).toBe(buildWorldGeoJson())
  })

  it('excludes Antarctica -- its extreme-southern-latitude geometry rendered as a wide band artifact', () => {
    const geojson = buildWorldGeoJson()
    const antarctica = geojson.features.find((f) => String(f.id) === '010')
    expect(antarctica).toBeUndefined()
  })

  it('produces no single-ring path segment with an implausibly long straight jump (antimeridian/pole streak regression guard)', async () => {
    const { geoNaturalEarth1, geoPath } = await import('d3-geo')
    const geojson = buildWorldGeoJson()
    const projection = geoNaturalEarth1().fitSize([960, 500], geojson)
    const path = geoPath(projection)
    for (const f of geojson.features) {
      const d = path(f)
      if (!d) continue
      for (const ring of d.split('M').filter((s) => s.trim().length > 0)) {
        const nums = ring.match(/-?\d+\.?\d*/g)?.map(Number) ?? []
        for (let i = 2; i < nums.length; i += 2) {
          const dx = nums[i] - nums[i - 2]
          const dy = nums[i + 1] - nums[i - 1]
          const jump = Math.hypot(dx, dy)
          // 960x500 viewBox: a single-ring point-to-point jump anywhere near
          // the map's own width would be a visible streak, not real coastline.
          expect(jump).toBeLessThan(200)
        }
      }
    }
  })
})
