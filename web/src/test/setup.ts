import '@testing-library/jest-dom/vitest'
import { configure } from '@testing-library/react'

// Lazy-loaded route chunks (React.lazy/import()) can take longer than the
// 1000ms default to resolve on a cold test run.
configure({ asyncUtilTimeout: 5000 })

// jsdom has no ResizeObserver; echarts-for-react uses one to auto-resize
// the chart container. A no-op stub is enough for tests that only assert
// on surrounding page content, not chart pixels.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
;(globalThis as any).ResizeObserver = ResizeObserverStub
