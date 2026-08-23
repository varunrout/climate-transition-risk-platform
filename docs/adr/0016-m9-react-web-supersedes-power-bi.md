# ADR 0016: M9 Product Layer -- React/TypeScript Web Dashboard Supersedes Power BI

## Status

Accepted. The React/TypeScript web dashboard is now the canonical
user-facing M9 product. The Power BI project (`powerbi/`,
`docs/powerbi/`) is preserved as historical engineering evidence and is
explicitly marked superseded, not deleted.

## Context

ADR 0015 established a Power BI native-report M9 product on top of the
`gold/bi/` publication layer. That work produced a complete,
source-controlled PBIP/TMDL/PBIR project (9 tables, 9 relationships, 28
measures, 7 report pages, 49 visuals) and was later validated live
against a real, installed Power BI Desktop (2.157.879.0, August 2026)
across nine debugging rounds.

### What succeeded

- The `gold/bi/*.parquet` publication tables -- reused as-is by this ADR.
- The semantic design (tables, relationships, measure catalogue) from
  `docs/powerbi/semantic_model.md` -- proven correct: the semantic model
  loads cleanly in Desktop with all 8 tables, all measures, and no
  Power Query warnings.
- The static HTML portfolio preview (`docs/powerbi/portfolio_preview.html`).
- Real, Desktop-confirmed bug discovery and fixes: invalid multi-line DAX,
  a broken calculated table, Power Query type-inference and M-syntax
  errors, and several missing/incorrect PBIR schema references
  (`pages.json`, `report.json`, `definition.pbir`, `definition.pbism`).

### What blocked

After every diagnosable defect was found and fixed, the report canvas
itself still fails to render, throwing
`Cannot read properties of undefined (reading 'visualContainers')` from
`DesktopExplorationComponent.onExplorationActivated`. This was isolated
to be independent of visual content (reproduced with an empty visuals
folder) and independent of which page is active on load (reproduced by
changing `activePageName`), which rules out every page- or visual-level
authoring defect reachable from the file side. The remaining cause sits
somewhere in Desktop's report/model activation path that further static
inspection could not identify. See `docs/powerbi/native_report_status.md`
for the full defect log.

## Decision

**React/TypeScript becomes the canonical interactive M9 product.** This
is a product-layer decision, not a technical-impossibility claim: the
native Power BI route was superseded because React offers a more
controllable, portable, browser-native portfolio product with lower
distribution friction (no Desktop installation, no PBIX/report-server
dependency, directly linkable, deployable to a static host at
zero/near-zero cost) -- not because Power BI is technically unusable. The
underlying analytical logic, `gold/bi/` publication tables, and semantic
design remain valid and are reused, not rebuilt.

Architecture:

```text
Python pipeline -> gold/bi/*.parquet -> gold/web/*.json -> React static app
```

Python remains the sole source of analytical truth. The new `build-web`
publication stage selects, serializes, and validates -- it does not
recompute risk score, scenario, or structural-break logic.

## Consequences

- `powerbi/` and `docs/powerbi/` are retained, unmodified beyond adding a
  superseded-status notice, as evidence of real engineering work and
  live debugging methodology.
- A new `gold/web/` publication layer and `web/` React application are
  added; ADR 0015 remains historically accurate for the Power BI phase
  and is not retracted.
- No Azure production infrastructure changes as a result of this
  decision; `build-web` is a downstream, independently recoverable
  product-publication step (see the fail-closed design decision recorded
  separately for the web publication stage).
