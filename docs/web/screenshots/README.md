# React Dashboard Screenshots

## Status: captured, verified real

All 8 screenshots below were captured with Playwright (Chromium) directly
against the **live deployed production site**
(https://varunrout.github.io/climate-transition-risk-platform/), not
faked or mocked. The capture script waits for each page's charts to
actually paint (checks for non-empty SVG child nodes, not a fixed delay)
before taking the screenshot, and warns if a loading/error state is still
visible, so none of these show a loading spinner or blank chart.

| File | Route | Notes |
|---|---|---|
| `executive-overview.png` | `/` | 1440x2168 |
| `country-profile.png` | `/country/IDN` | 1440x1875 — Indonesia, the real current highest-risk country |
| `energy-transition.png` | `/energy` | 1440x1359 |
| `scenario-explorer.png` | `/scenarios` | 1440x1063 |
| `model-evidence.png` | `/evidence` | 1440x3113 |
| `structural-diagnostics.png` | `/diagnostics` | 1440x1107 |
| `provenance.png` | `/provenance` | 1440x1336 |
| `executive-overview-mobile.png` | `/` (mobile) | 390x3358, `isMobile` Chromium emulation |

Desktop captures use a 1440x900 viewport (full page, so several are taller
than 900px); the mobile capture uses 390x844 (iPhone/Android-class width)
with touch emulation enabled.

## Re-capturing

```bash
cd web
npm install
npm run screenshots                              # against the deployed production site
node scripts/capture-screenshots.mjs http://localhost:5183  # against a local build instead
```

The local-build variant requires `npm run build && npm run preview` to be
running first, and `web/public/data/*.json` to be a real, current bundle
(see the root README's "Web dashboard" section).
