import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useRunMetadata } from '../lib/queries'
import { formatDate } from '../lib/format'

const NAV_ITEMS = [
  { to: '/', label: 'Executive Overview', end: true },
  { to: '/energy', label: 'Energy Transition' },
  { to: '/scenarios', label: 'Scenario Explorer' },
  { to: '/evidence', label: 'Model Evidence' },
  { to: '/diagnostics', label: 'Structural Diagnostics' },
  { to: '/provenance', label: 'Data Quality & Provenance' },
]

export function Layout() {
  const [navOpen, setNavOpen] = useState(false)
  const { data: runMetadata } = useRunMetadata()

  return (
    <div className="min-h-screen">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-[var(--color-accent)] focus:px-4 focus:py-2 focus:text-white"
      >
        Skip to main content
      </a>
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold tracking-tight">
              Climate Transition Risk Intelligence
            </p>
            <p className="truncate text-xs text-[var(--color-text-subtle)]">
              G20 sovereign transition risk · as of{' '}
              {runMetadata ? formatDate(runMetadata.completed_at) : '…'}
            </p>
          </div>
          <button
            type="button"
            className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm sm:hidden"
            aria-expanded={navOpen}
            aria-controls="primary-nav"
            onClick={() => setNavOpen((open) => !open)}
          >
            Menu
          </button>
          <nav id="primary-nav" aria-label="Primary" className="hidden gap-1 sm:flex">
            {NAV_ITEMS.map((item) => (
              <NavItem key={item.to} {...item} />
            ))}
          </nav>
        </div>
        {navOpen && (
          <nav
            aria-label="Primary (mobile)"
            className="flex flex-col gap-1 border-t border-[var(--color-border)] px-4 py-2 sm:hidden"
          >
            {NAV_ITEMS.map((item) => (
              <NavItem key={item.to} {...item} onClick={() => setNavOpen(false)} />
            ))}
          </nav>
        )}
      </header>
      <main id="main-content" className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>
      <footer className="mx-auto max-w-7xl px-4 py-8 text-xs text-[var(--color-text-subtle)] sm:px-6">
        <p>
          Not real-time analytics. Reflects the latest successful published run
          {runMetadata?.run_id ? ` (${runMetadata.run_id.slice(0, 8)})` : ''}. Git SHA{' '}
          {runMetadata?.git_sha ? runMetadata.git_sha.slice(0, 12) : 'unknown'}.
        </p>
      </footer>
    </div>
  )
}

function NavItem({
  to,
  label,
  end,
  onClick,
}: {
  to: string
  label: string
  end?: boolean
  onClick?: () => void
}) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      className={({ isActive }) =>
        `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
          isActive
            ? 'bg-[var(--color-accent)]/10 text-[var(--color-accent-strong)]'
            : 'text-[var(--color-text-muted)] hover:bg-[var(--color-surface-inset)]'
        }`
      }
    >
      {label}
    </NavLink>
  )
}
