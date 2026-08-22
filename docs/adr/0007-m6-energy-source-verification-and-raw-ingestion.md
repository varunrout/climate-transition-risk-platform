# ADR 0007: M6 phase 1 — energy source verification and raw ingestion

- Status: Accepted
- Date: 2026-08-22

## Context

M6 ("energy-system transition expansion") required source feasibility
research *before* any ingestion, per an explicit brief: verify licensing,
programmatic access, country/year coverage, update cadence and units for
every candidate source, keep raw indicators separate from modelled/risk-score
components, and gate any risk-score change behind coverage/collinearity/
incremental-information/backtest checks. This ADR records what was verified,
what was implemented, and what deliberately was not.

## Source verification

Full detail: `docs/m6_source_feasibility.md`. Summary:

| Source | Verdict |
|---|---|
| OWID `energy-data` | **PASS** — CC-BY-4.0, live access verified (`owid-public.owid.io` returns 200), full 1985–2024/25 coverage measured directly for all 19 configured countries |
| Ember (direct) | Licence OK, access path not verified (403 on direct fetch, no confirmed stable CSV URL) — deferred |
| World Bank WDI energy indicators | Verified but redundant with OWID for this project's countries — not ingested |
| IEA | Licence fails — free datasets are CC BY-NC-SA 4.0 (non-commercial only) — excluded |
| IRENA | Licence OK, access unverified, narrower/different (capacity, not mix) — deferred |

## What was implemented

- `config/sources.yaml`: new `owid_energy` entry, `approved`, enabled.
- `climate_risk.ingestion.owid_energy.OwidEnergyAdapter` — same pattern as
  the existing `OwidCo2Adapter`, fetches
  `https://owid-public.owid.io/data/energy/owid-energy-data.csv`, filters to
  the 19-country G20 scope, carries `coal_share_elec`, `gas_share_elec`,
  `oil_share_elec`, `fossil_share_elec`, `renewables_share_elec`,
  `low_carbon_share_elec`, `nuclear_share_elec`, plus sub-technology shares.
- `climate_risk.transforms.silver.build_fact_country_year_energy` — a new,
  independent silver table (`fact_country_year_energy`), raw pass-through
  only, no derived math. `build-silver` builds it best-effort: its absence
  never blocks `fact_country_year_transition`, which M0–M5 already depend on.
- `climate_risk.features.energy_transition` — diagnostic feature families
  (coal/fossil/renewable/low-carbon latest levels, coal trend, clean-power
  momentum, renewable build-out rate, fossil persistence, transition
  velocity, stalled-transition residual, cross-country percentile
  positioning). New `climate-risk energy-features` CLI command writes
  `gold/energy_transition_features.parquet`. Wired into `run()` as a
  best-effort stage (failure here does not block backtest/score/publish).
- Two feature families from the brief were **not** computed and are recorded
  as explicit gaps rather than approximated: electricity carbon intensity
  (gCO2/kWh — not in OWID `energy-data`'s ingested columns) and absolute
  electricity-demand growth (source columns are shares, not absolute
  generation levels).

## What was deliberately not done

- `scoring/risk_score.py` is untouched. `weight_coverage` is still `0.8`.
  No coverage/collinearity/incremental-information/backtest analysis has
  been run on the new features, so none of the M6 brief's score-gating
  prerequisites are satisfied yet — this is phase 1 (raw ingestion +
  diagnostics) only.
- `publish` does not read or require `gold/energy_transition_features.parquet`
  — it remains outside the fail-closed barrier's required-artifact set.

## Verification

- 99 tests passing (was 84 before this change): 5 new adapter contract
  tests, 4 new silver-table integration tests, 6 new feature-module unit
  tests, plus the existing suite unchanged and still green.
- `ruff check`, `ruff format --check`, `mypy src` all clean.
- Full local pipeline re-run against live upstream data
  (`ingest → build-silver → energy-features → backtest → score → publish`):
  `owid_energy` ingested 2307 rows (ACCEPTED); `fact_country_year_energy`
  built with 2307 rows; `energy-features` produced diagnostic rows for all
  19 countries; `backtest`/`score`/`publish` completed unchanged in
  structure (19 countries scored, `weight_coverage=0.8`, 4-of-5 components)
  — confirming the M6 additions are additive and don't perturb the existing
  M0–M5 outputs' code path. Exact backtest MAE/coverage numbers differ
  slightly from the figures recorded in ADR 0002/README at the time they
  were written; this pipeline pulls live weekly-refreshed upstream data
  (`refresh_check: weekly` in `config/sources.yaml`), so month-over-month
  numeric drift from upstream revisions is expected and is not attributable
  to this change — no code in `backtesting/` or `scoring/` was touched.

## Consequences

- A new, licence-clean, access-verified electricity-mix dataset is now
  ingested and available for exploratory analysis, with no change to Azure
  infrastructure, cost posture, or the existing risk score.
- M6 remains **partially implemented**: raw ingestion and diagnostics are
  done; the score-gating analysis and any resulting `scoring/` change are a
  separate, not-yet-started follow-on phase.
