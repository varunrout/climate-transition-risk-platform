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

## Manual Power BI Desktop Steps Remaining

Power BI Desktop is not available in the current execution environment, so a
PBIX was not created.

Minimum manual steps:

1. Run `poetry run climate-risk --no-json-logs build-bi --scenario-target-year 2030`.
2. Open Power BI Desktop.
3. Import the eight Parquet tables from `data/lake/gold/bi/`.
4. Create relationships from `country_overview[country_iso3]` to each fact
   table's `country_iso3`.
5. Add the measures from `measure_catalog.md`.
6. Build the seven report pages from `page_specs.md`.
7. Use the colours and formatting rules from `design_system.md`.
8. Export screenshots/PDF for portfolio presentation.

## Status

Code/data layer: complete.

Desktop visual assembly: pending.

Full M9 product completion requires a usable report artifact, such as a PBIX,
PDF export, or accepted static portfolio render.
