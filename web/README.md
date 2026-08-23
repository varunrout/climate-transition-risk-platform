# Climate Transition Risk Intelligence -- Web Dashboard

The canonical M9 product (see [ADR 0016](../docs/adr/0016-m9-react-web-supersedes-power-bi.md)):
a React/TypeScript static dashboard over the `gold/web/` JSON publication
bundle (see [ADR 0017](../docs/adr/0017-m9-web-bundle-snapshot-and-publication-boundary.md)).

Python (`climate_risk`) remains the sole source of analytical truth --
this app selects, validates, and renders already-computed output; it does
not reimplement risk scoring, scenarios, backtesting, or diagnostics.

## Develop

```bash
npm install
npm run dev
```

To point at fresh data, from the repo root:

```bash
uv run climate-risk build-bi
uv run climate-risk build-web
cp data/lake/gold/web/*.json web/public/data/
```

## Quality gates

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

## Stack

Vite, React 19, TypeScript, React Router, TanStack Query, Zod (runtime
bundle-schema validation), Tailwind CSS v4 (design tokens in
`src/index.css`), Apache ECharts (direct binding, see
`src/lib/useEcharts.ts` -- not `echarts-for-react`, which does not work
correctly with echarts v6, see that file's comment), Vitest + React
Testing Library.

See the repository root [README.md](../README.md) for the full project
context and [`docs/web/screenshots/README.md`](../docs/web/screenshots/README.md)
for how to capture portfolio screenshots.
