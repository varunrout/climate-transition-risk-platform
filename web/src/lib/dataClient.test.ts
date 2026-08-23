import { beforeEach, describe, expect, it } from 'vitest'
import { fetchManifest, fetchCountryOverview, BundleError } from './dataClient'
import { installFetchMock } from '../test/fixtures'
import { fixtureManifest } from '../test/fixtures'

describe('dataClient', () => {
  beforeEach(() => {
    installFetchMock()
  })

  it('parses a valid manifest', async () => {
    const manifest = await fetchManifest()
    expect(manifest.schema_version).toBe('1.0.0')
    expect(manifest.active_score_version).toBe('v2_energy')
  })

  it('parses country overview rows against the schema', async () => {
    const rows = await fetchCountryOverview()
    expect(rows).toHaveLength(2)
    expect(rows[0].country_iso3).toBe('AAA')
  })

  it('rejects an incompatible schema version rather than rendering it', async () => {
    installFetchMock({ 'manifest.json': { ...fixtureManifest, schema_version: '99.0.0' } })
    await expect(fetchManifest()).rejects.toThrow(BundleError)
    await expect(fetchManifest()).rejects.toThrow(/schema version/i)
  })

  it('surfaces a typed error when a file is missing', async () => {
    installFetchMock({})
    vi.stubGlobal('fetch', vi.fn(async () => new Response('not found', { status: 404 })))
    await expect(fetchManifest()).rejects.toBeInstanceOf(BundleError)
  })

  it('surfaces a typed error for a row that fails schema validation', async () => {
    installFetchMock({ 'country-overview.json': [{ country_iso3: 'AAA' }] })
    await expect(fetchCountryOverview()).rejects.toThrow(BundleError)
  })
})
