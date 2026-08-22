# Portfolio Story

## Narrative

1. Which countries are most exposed?
2. What drives that exposure?
3. Is the transition improving?
4. What is happening in the energy system?
5. What could the future look like under the production scenario engine?
6. How much should we trust the model?
7. Which data and method limitations remain?

## Portfolio Assets Available From Code

Generated BI tables:

- `gold/bi/country_overview.parquet`
- `gold/bi/country_timeseries.parquet`
- `gold/bi/risk_components.parquet`
- `gold/bi/scenario_quantiles.parquet`
- `gold/bi/backtest_metrics.parquet`
- `gold/bi/energy_indicators.parquet`
- `gold/bi/regime_diagnostics.parquet`
- `gold/bi/run_metadata.parquet`

Documentation:

- semantic model
- measure catalogue
- seven-page report specification
- refresh/auth strategy
- design system

## Native Power BI Project

A source-controlled PBIP project (`powerbi/ClimateTransitionRisk.pbip`) now
exists: 9 tables (the 8 `gold/bi/` tables plus a calculated `dim_year`), 9
relationships, 28 DAX measures, and all 7 report pages with 49 visual
containers, built directly from `semantic_model.md`, `measure_catalog.md`
and `page_specs.md` -- no redesign. See
`docs/powerbi/native_report_status.md` for exactly what was authored, what
automated cross-checks were run against it (and what they caught and
fixed), and what remains unverifiable without Power BI Desktop.

## Manual Power BI Desktop Steps Remaining

Power BI Desktop is still not available in this execution environment, so
the project above has never been opened, and no PBIX or screenshot has
been produced. Minimum manual steps (the project no longer needs to be
built from scratch, only opened and verified):

1. Run `uv run climate-risk build-bi --scenario-target-year 2030` if the
   `gold/bi/` tables aren't already current.
2. Install Power BI Desktop and open `powerbi/ClimateTransitionRisk.pbip`.
3. Point the `GoldBiFolderPath` parameter at the local `data/lake/gold/bi/`
   folder if prompted.
4. Fix whatever Desktop reports on first load (see
   `docs/powerbi/native_report_status.md` for what was and wasn't already
   checked without Desktop).
5. Export the screenshots listed in `docs/powerbi/screenshots/README.md`.
6. Optionally save as PBIX for distribution.

## Status

Code/data layer: complete.

Native Power BI project (PBIP/TMDL/PBIR): authored, internally
cross-checked, **not opened in Desktop** (not installed in this
environment) -- see `docs/powerbi/native_report_status.md`.

Desktop visual validation, PBIX export, and screenshots: pending, blocked
on the same cause.

A static portfolio render is available at `docs/powerbi/portfolio_preview.html`.
