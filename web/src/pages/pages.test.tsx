import { beforeEach, describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import App from '../App'
import { renderWithProviders } from '../test/renderWithProviders'
import { installFetchMock } from '../test/fixtures'

describe('production vs research semantics and key page content', () => {
  beforeEach(() => {
    installFetchMock()
  })

  it('labels the active score as v2_energy production and keeps v1 visible as comparison', async () => {
    renderWithProviders(<App />, { route: '/country/AAA' })
    await screen.findByRole('heading', { name: /alphaland/i })
    expect(screen.getAllByText(/v2_energy/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/comparison score \(v1\)/i)).toBeInTheDocument()
  })

  it('labels the production scenario method explicitly on the Scenario Explorer', async () => {
    renderWithProviders(<App />, { route: '/scenarios' })
    await screen.findByRole('heading', { name: /scenario explorer/i })
    expect(screen.getAllByText(/empirical_bootstrap_v1/i).length).toBeGreaterThan(0)
  })

  it('renders P5 <= P50 <= P95 forecast values on the Scenario Explorer', async () => {
    renderWithProviders(<App />, { route: '/scenarios' })
    await screen.findByRole('heading', { name: /scenario explorer/i })
    expect(await screen.findByText('0.500')).toBeInTheDocument() // P5
    expect(screen.getByText('0.800')).toBeInTheDocument() // P50
    expect(screen.getByText('1.200')).toBeInTheDocument() // P95
  })

  it('never presents research scenario variants as production on the Scenario Explorer', async () => {
    renderWithProviders(<App />, { route: '/scenarios' })
    await screen.findByRole('heading', { name: /scenario explorer/i })
    expect(screen.getByText(/rejected/i)).toBeInTheDocument()
  })

  it('marks structural diagnostics as research-only with the required banner', async () => {
    renderWithProviders(<App />, { route: '/diagnostics' })
    await screen.findByRole('heading', { name: /structural change diagnostics/i })
    expect(
      screen.getByText(/STRUCTURAL-BREAK DIAGNOSTICS ARE RESEARCH\/INTERPRETATION ONLY/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/do not select the/i)).toBeInTheDocument()
  })

  it('shows real provenance values, not placeholders', async () => {
    renderWithProviders(<App />, { route: '/provenance' })
    await screen.findByRole('heading', { name: /data quality/i })
    expect(screen.getByText('PUBLISHED')).toBeInTheDocument()
    expect(screen.getAllByText(/abc123def456/).length).toBeGreaterThan(0)
    expect(screen.getByText(/^v2_energy$/)).toBeInTheDocument()
  })

  it('shows the historical undercoverage on Model Evidence rather than hiding it', async () => {
    renderWithProviders(<App />, { route: '/evidence' })
    await screen.findByRole('heading', { name: /model evidence/i })
    expect(screen.getByText(/below the nominal 90% target/i)).toBeInTheDocument()
  })
})
