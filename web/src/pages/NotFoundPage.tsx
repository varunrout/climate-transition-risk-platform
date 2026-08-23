import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div role="alert" className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-8 text-center">
      <p className="text-lg font-semibold">Page not found</p>
      <p className="mt-2 text-sm text-[var(--color-text-muted)]">
        The page you requested does not exist.{' '}
        <Link to="/" className="text-[var(--color-accent-strong)] underline-offset-2 hover:underline">
          Return to Executive Overview
        </Link>
        .
      </p>
    </div>
  )
}
