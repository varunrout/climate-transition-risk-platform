# React Dashboard Screenshots

## Status: functionally verified live, pixel screenshots not captured this session

The dashboard was run against real data (`climate-risk build-web` output,
19 countries, the actual production `v2_energy` run) via a local Vite
preview server and inspected in-browser: every one of the 7 routes was
confirmed to render its real content (DOM text content read directly, and
for the 3 chart-bearing routes checked so far, confirmed the SVG chart
elements contain real painted child nodes, not empty containers -- see
`docs/adr` commit history / PR description for the exact verification
log). A real bug was found and fixed in this process (`echarts-for-react`
silently failed to ever call `setOption` under echarts v6 -- rewritten to
use ECharts directly; see `web/src/lib/useEcharts.ts`).

**Actual pixel screenshots were not captured**, because the automation
environment's Browser pane was not in a displayed/compositing state in
this session (`computer.screenshot` failed with "the Browser pane is not
displayed, so the page is not compositing frames"). Per this project's
no-fabrication rule, no screenshot files were faked to fill this gap.

## Exact steps to capture the real screenshots

```bash
cd climate-transition-risk
uv run climate-risk build-web
cp data/lake/gold/web/*.json web/public/data/
cd web
npm run build
npm run preview -- --port 5183
```

Then, with the app open at `http://localhost:5183/`, capture each route at
a desktop viewport (1440x900 recommended) and save with these exact
filenames:

| Route | File |
|---|---|
| `/` | `executive-overview.png` |
| `/country/<any real ISO3, e.g. IDN>` | `country-profile.png` |
| `/energy` | `energy-transition.png` |
| `/scenarios` | `scenario-explorer.png` |
| `/evidence` | `model-evidence.png` |
| `/diagnostics` | `structural-diagnostics.png` |
| `/provenance` | `provenance.png` |

Use a representative, real country selection (e.g. Indonesia, the current
highest-risk country) rather than the first alphabetical entry, so the
Country Profile and Scenario Explorer screenshots show meaningful,
non-trivial data.
