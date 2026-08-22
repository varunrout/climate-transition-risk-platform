# ADR 0012: M7 phase 2 historical-origin regime stability

- Status: Accepted as research evidence; not promoted to production
- Date: 2026-08-22

## Context

ADR 0011 implemented M7 Phase 1 structural-break diagnostics and found
candidate breaks, but also strong method sensitivity. Phase 2 tests whether
regime evidence can be recomputed at historical origins without future leakage
and whether break signals are temporally stable enough to justify scenario
experiments.

## Decision

Add Phase 2 historical-origin diagnostics:

- `climate-risk m7-phase2`
- `climate_risk.research.m7_regimes.run_phase2_diagnostics`
- outputs under `gold/research/m7/phase2/`

The command recomputes every M7 detector at origins
2010, 2012, 2014, 2015, 2016, and 2017. Each run uses only observations
available at or before that origin year.

## Outputs

Local run:

```text
climate-risk --no-json-logs m7-phase2
```

Artifacts:

- `gold/research/m7/phase2/origin_regime_results.parquet`
- `gold/research/m7/phase2/origin_method_agreement.parquet`
- `gold/research/m7/phase2/temporal_stability.parquet`
- `gold/research/m7/phase2/decision.json`

Measured local output:

- origin-regime rows: 3,192
- method-agreement rows: 741
- temporal-stability rows: 133
- origins: 2010, 2012, 2014, 2015, 2016, 2017

Eligible detector rows by origin:

| Origin | Eligible rows |
|---:|---:|
| 2010 | 304 |
| 2012 | 532 |
| 2014 | 532 |
| 2015 | 532 |
| 2016 | 532 |
| 2017 | 532 |

Segmented-regression break detection across eligible historical origins:

| Series | Eligible profiles | Break detections | Detection rate |
|---|---:|---:|---:|
| `carbon_intensity_gdp` | 95 | 20 | 0.211 |
| `carbon_intensity_log_change` | 95 | 0 | 0.000 |
| `co2_gdp_decoupling_gap` | 95 | 0 | 0.000 |
| `clean_power_momentum_pp_per_year` | 114 | 33 | 0.289 |
| `low_carbon_share_elec` | 114 | 33 | 0.289 |
| `fossil_share_elec` | 114 | 27 | 0.237 |
| `coal_share_elec` | 114 | 26 | 0.228 |

Examples of temporally stable profiles:

- Italy, `carbon_intensity_gdp`: break detection rate 1.0, modal break year
  2005, zero label switches.
- Russia, `coal_share_elec`: break detection rate 1.0, modal break year 2000,
  one-year break-year spread.
- Korea, `fossil_share_elec` and `low_carbon_share_elec`: break detection
  rate 1.0, modal break year 1990, zero label switches.

Examples of remaining instability:

- South Africa, `low_carbon_share_elec`: break detection rate 1.0, but
  break-year spread 23 years and two label switches.
- Several annual-change series show no segmented-regression break detections,
  suggesting those are poor candidates for regime conditioning.

## Consequences

Phase 2 confirms that leakage-safe historical-origin recomputation works and
that some regime signals are temporally stable. It does not prove that regime
conditioning improves forecasts or uncertainty intervals.

The Phase 2 mechanical decision is `PHASE3_JUSTIFIED`, not production
promotion.

No production changes are approved:

- `risk_score_v2_energy` remains unchanged.
- The scenario engine remains unchanged.
- `climate-risk run` does not call M7.
- Azure infrastructure and the Monday 03:00 UTC schedule remain unchanged.

The next gate is Phase 3: regime-aware scenario experiments and historical
backtesting, evaluating MAE, median absolute error, interval coverage, interval
width, calibration gap, country-level improvements, and origin-level
improvements.
