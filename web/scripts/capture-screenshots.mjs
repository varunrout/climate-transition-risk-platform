// Captures real, non-fabricated portfolio screenshots of the dashboard.
//
// Usage:
//   node scripts/capture-screenshots.mjs [baseUrl]
//
// Defaults to the deployed production site; pass a local preview URL
// (e.g. http://localhost:5183) to capture from a local production build
// instead (`npm run build && npm run preview`).
//
// Waits for each route's charts to actually paint (SVG child nodes
// present) before capturing, rather than a fixed delay, so screenshots
// never show a loading/empty state.
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const BASE = process.argv[2] ?? 'https://varunrout.github.io/climate-transition-risk-platform'
const OUT_DIR = resolve(__dirname, '../../docs/web/screenshots')
mkdirSync(OUT_DIR, { recursive: true })

// waitForSvgMin: how many painted (non-empty) SVGs the route must have
// before it's considered fully rendered. 0 = no chart on this page.
const ROUTES = [
  { path: '/', file: 'executive-overview.png', waitForSvgMin: 3 },
  { path: '/country/IDN', file: 'country-profile.png', waitForSvgMin: 4 },
  { path: '/energy', file: 'energy-transition.png', waitForSvgMin: 1 },
  { path: '/scenarios', file: 'scenario-explorer.png', waitForSvgMin: 1 },
  { path: '/evidence', file: 'model-evidence.png', waitForSvgMin: 2 },
  { path: '/diagnostics', file: 'structural-diagnostics.png', waitForSvgMin: 0 },
  { path: '/provenance', file: 'provenance.png', waitForSvgMin: 0 },
]

async function waitForChartsPainted(page, minSvgWithContent) {
  if (minSvgWithContent === 0) {
    await page.waitForTimeout(500)
    return
  }
  await page.waitForFunction(
    (min) => {
      const svgs = Array.from(document.querySelectorAll('svg'))
      return svgs.filter((s) => s.querySelectorAll('*').length > 0).length >= min
    },
    minSvgWithContent,
    { timeout: 15000 },
  )
  await page.waitForTimeout(400) // let final paint/animation settle
}

async function main() {
  console.log('Capturing screenshots from', BASE)
  const browser = await chromium.launch()

  const desktopContext = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await desktopContext.newPage()

  for (const route of ROUTES) {
    const url = `${BASE}${route.path}`
    console.log('Navigating to', url)
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 })
    await page.waitForSelector('main', { timeout: 15000 })
    await waitForChartsPainted(page, route.waitForSvgMin)

    const bodyText = await page.locator('main').innerText()
    if (/loading|could not load data/i.test(bodyText.slice(0, 200))) {
      console.warn('WARNING: possible loading/error state still visible for', route.path)
    }

    const outPath = `${OUT_DIR}/${route.file}`
    await page.screenshot({ path: outPath, fullPage: true })
    console.log('Saved', outPath)
  }
  await desktopContext.close()

  const mobileContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    userAgent:
      'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36',
  })
  const mobilePage = await mobileContext.newPage()
  await mobilePage.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 30000 })
  await mobilePage.waitForSelector('main', { timeout: 15000 })
  await waitForChartsPainted(mobilePage, 1)
  const mobileOut = `${OUT_DIR}/executive-overview-mobile.png`
  await mobilePage.screenshot({ path: mobileOut, fullPage: true })
  console.log('Saved', mobileOut)
  await mobileContext.close()

  await browser.close()
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
