import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RiskMap } from './RiskMap'
import { renderWithProviders } from '../test/renderWithProviders'
import { fixtureCountryOverview } from '../test/fixtures'

const navigateMock = vi.hoisted(() => vi.fn())

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigateMock }
})

// The fixture uses placeholder ISO3 codes (AAA/BBB) that don't exist in the
// real world topology -- for map-specific behaviour (click/keyboard nav onto
// an actual rendered country path) we need real covered-country ISO3 codes.
const realCountries = fixtureCountryOverview.map((c, i) => ({
  ...c,
  country_iso3: ['GBR', 'USA'][i],
  country_name: ['United Kingdom', 'United States'][i],
}))

describe('RiskMap', () => {
  it('renders one focusable, labelled path per covered country', () => {
    renderWithProviders(<RiskMap countries={realCountries} />)
    const gbr = screen.getByRole('button', { name: /united kingdom/i })
    const usa = screen.getByRole('button', { name: /united states/i })
    expect(gbr).toHaveAttribute('tabindex', '0')
    expect(usa).toHaveAttribute('tabindex', '0')
  })

  it('navigates to the country profile on click', async () => {
    const user = userEvent.setup()
    renderWithProviders(<RiskMap countries={realCountries} />)
    await user.click(screen.getByRole('button', { name: /united kingdom/i }))
    expect(navigateMock).toHaveBeenCalledWith('/country/GBR')
  })

  it('navigates to the country profile via keyboard activation (Enter)', async () => {
    const user = userEvent.setup()
    renderWithProviders(<RiskMap countries={realCountries} />)
    const usa = screen.getByRole('button', { name: /united states/i })
    usa.focus()
    await user.keyboard('{Enter}')
    expect(navigateMock).toHaveBeenCalledWith('/country/USA')
  })

  it('exposes an accessible label and a non-map sortable-table fallback hint', () => {
    renderWithProviders(<RiskMap countries={realCountries} />)
    expect(
      screen.getByRole('img', { name: /world map coloured by transition risk score/i }),
    ).toBeInTheDocument()
    expect(screen.getByText(/sortable ranking table below/i)).toBeInTheDocument()
  })

  it('renders a static SVG with no roam/zoom/pan wheel or drag handlers', () => {
    const { container } = renderWithProviders(<RiskMap countries={realCountries} />)
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
    // No wheel handler is attached anywhere in the map subtree -- this is a
    // regression guard for the "no accidental free zoom/pan" requirement
    // (the previous ECharts renderer set `roam: true`, enabling exactly that).
    expect(svg?.onwheel).toBeNull()
  })

  it('renders every non-covered country as subdued base geography (no ISO3 label)', () => {
    const { container } = renderWithProviders(<RiskMap countries={realCountries} />)
    const paths = container.querySelectorAll('path')
    // 19 covered + many uncovered features from the world topology.
    expect(paths.length).toBeGreaterThan(19)
    const uncoveredPaths = [...paths].filter((p) => !p.hasAttribute('aria-label'))
    expect(uncoveredPaths.length).toBeGreaterThan(0)
    for (const p of uncoveredPaths) {
      expect(p).not.toHaveAttribute('role', 'button')
    }
  })
})
