# Power BI (SUPERSEDED PRODUCT PROTOTYPE -- NOT CURRENT PRODUCT LAYER)

**As of ADR 0016, the native Power BI report is no longer the canonical M9
product.** The canonical, user-facing M9 product is the React/TypeScript
web dashboard under [`web/`](../../web/), fed by the `gold/web/` publication
layer (`climate-risk build-web`; see ADR 0017).

This directory is preserved as engineering history, not deleted:

- The `gold/bi/` publication tables this design describes are real and are
  still reused, unmodified, as the source for `gold/web/`.
- The semantic design (`semantic_model.md`, `measure_catalog.md`,
  `page_specs.md`, `design_system.md`) proved correct: the semantic model
  loads cleanly in a real, installed Power BI Desktop.
- `native_report_status.md` is the full, honest record of live Desktop
  debugging -- nine real bugs found and fixed, and the one unresolved
  report-canvas rendering defect that ended that effort.
- `refresh_and_auth.md` and `portfolio_story.md` document the intended
  refresh/auth path and portfolio narrative for this (superseded) route.

See [`docs/adr/0016-m9-react-web-supersedes-power-bi.md`](../adr/0016-m9-react-web-supersedes-power-bi.md)
for the full rationale: this is a distribution/portability decision (no
Desktop install required, directly linkable, deployable to a static host
at zero/near-zero cost), not a claim that Power BI is technically
impossible.
