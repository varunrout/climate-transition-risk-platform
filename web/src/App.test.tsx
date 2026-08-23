import { beforeEach, describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { renderWithProviders } from './test/renderWithProviders'
import { installFetchMock } from './test/fixtures'

describe('App boot and routing', () => {
  beforeEach(() => {
    installFetchMock()
  })

  it('boots and renders the Executive Overview by default', async () => {
    renderWithProviders(<App />)
    expect(await screen.findByRole('heading', { name: /executive overview/i })).toBeInTheDocument()
  })

  it('renders the sovereign risk ranking table with both fixture countries', async () => {
    renderWithProviders(<App />)
    expect(await screen.findByText('Alphaland')).toBeInTheDocument()
    expect(await screen.findByText('Betaland')).toBeInTheDocument()
  })

  it('navigates to Energy Transition via the primary nav', async () => {
    const user = userEvent.setup()
    renderWithProviders(<App />)
    await screen.findByRole('heading', { name: /executive overview/i })
    await user.click(screen.getByRole('link', { name: 'Energy Transition' }))
    expect(await screen.findByRole('heading', { name: /energy transition/i })).toBeInTheDocument()
  })

  it('renders a valid country profile route', async () => {
    renderWithProviders(<App />, { route: '/country/AAA' })
    expect(await screen.findByRole('heading', { name: /alphaland/i })).toBeInTheDocument()
  })

  it('shows a graceful not-found state for an unknown country', async () => {
    renderWithProviders(<App />, { route: '/country/ZZZ' })
    expect(await screen.findByText(/country not found/i)).toBeInTheDocument()
    expect(await screen.findByText(/ZZZ/)).toBeInTheDocument()
  })

  it('shows a not-found page for an unknown route', async () => {
    renderWithProviders(<App />, { route: '/this-route-does-not-exist' })
    await waitFor(() => expect(screen.getByText(/page not found/i)).toBeInTheDocument())
  })
})
