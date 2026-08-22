# M7 Phase 1 Report: Structural-Break / Regime Diagnostics

Date: 2026-08-22

Status: Phase 1 complete; Phase 2 justified. This is research evidence only.
No production score, scenario engine, Azure schedule, or publish contract was
changed.

## 1. Methods evaluated

- `threshold_baseline`: interpretable recent-vs-prior five-observation slope
  comparison. Assumes a break is only credible when the slope change exceeds
  the global economic-effect threshold and is large relative to historical
  year-to-year variation.
- `rolling_slope_change`: scans adjacent five-observation windows and chooses
  the strongest local slope change. Sensitive by design, useful as a diagnostic
  warning flag rather than a final break declaration.
- `cusum_stability`: fits one linear trend and checks cumulative standardized
  residual deviation. Useful for broad instability evidence; weak on precise
  break timing.
- `segmented_regression`: one-break piecewise linear scan with five-observation
  minimum segments, fit-improvement threshold, and effect-size threshold. This
  is the Phase 1 profile method because it is interpretable and parsimonious
  for annual sovereign data.

PELT, binary segmentation, and Bai-Perron-style multiple-break logic were
considered but not implemented in Phase 1. The current annual panel is small;
allowing multiple breaks before stability/backtest evidence would overfit
timing noise. Phase 2 can revisit a constrained two-break variant only if the
single-break evidence proves stable and useful.

## 2. Assumptions

- Annual country-level data is low-frequency and small-sample.
- Phase 1 allows at most one break per country-series profile.
- Break detection is statistical structural-change evidence, not causal policy
  attribution.
- All historical-origin use must be recomputed with observations at or before
  the origin year only.
- Synthetic data appears only in unit tests.

## 3. Minimum-history rules

- Minimum total observations: 12.
- Minimum observations per segment: 5.
- Recent/prior threshold windows: 5 observations each.
- Phase 1 maximum breaks: 1.
- Phase 1 bootstrap stability sample: 12 country-series profiles, selected
  deterministically from the strongest segmented-regression candidates.

## 4. Candidate variables

The implemented candidate set is:

- `carbon_intensity_gdp`
- `carbon_intensity_log_change`
- `co2_gdp_decoupling_gap`
- `low_carbon_share_elec`
- `clean_power_momentum_pp_per_year`
- `fossil_share_elec`
- `coal_share_elec`

Level, trend, and annual-change phenomena are kept separate. M6 score v2 inputs
remain unchanged.

## 5. Coverage

All seven candidate series have 19/19 country coverage.

| Series | Rows | Year range |
|---|---:|---|
| `carbon_intensity_gdp` | 475 | 2000-2024 |
| `carbon_intensity_log_change` | 456 | 2001-2024 |
| `co2_gdp_decoupling_gap` | 456 | 2001-2024 |
| `low_carbon_share_elec` | 777 | 1985-2025 |
| `clean_power_momentum_pp_per_year` | 701 | 1989-2025 |
| `fossil_share_elec` | 777 | 1985-2025 |
| `coal_share_elec` | 777 | 1985-2025 |

## 6. Detected breaks by method

`country_breaks.parquet` contains 532 country-series-method rows.

Segmented-regression detected breaks:

- `carbon_intensity_gdp`: 5/19.
- `carbon_intensity_log_change`: 0/19.
- `co2_gdp_decoupling_gap`: 0/19.
- `low_carbon_share_elec`: 1/19.
- `clean_power_momentum_pp_per_year`: 6/19.
- `fossil_share_elec`: 2/19.
- `coal_share_elec`: 3/19.

Rolling slope diagnostics detected many more breaks, especially in energy
momentum and coal share, confirming that local slope scans are sensitive and
should not be used alone as a regime declaration.

## 7. Method agreement

Only 1 of 133 country-series profiles was robust across methods in Phase 1:

- Mexico, `clean_power_momentum_pp_per_year`, modal break year 2021, three
  methods detecting a break within one year.

The broader result is method-sensitive. This is not a failure of the research;
it is a warning that Phase 2 must evaluate stability and forecasting value
before regime-aware scenarios are accepted.

## 8. Representative country cases

Mechanically selected examples from segmented-regression profiles:

- Strong acceleration: Australia, `low_carbon_share_elec`, break year 2017,
  post-break slope +2.97 percentage points/year, confidence 1.00.
- Persistent transition: Argentina, `clean_power_momentum_pp_per_year`, break
  year 1994, current direction improving, but not accelerating versus the
  prior regime.
- Apparent stall: Saudi Arabia, `coal_share_elec`, no credible break, flat
  current slope.
- Deterioration: Mexico, `clean_power_momentum_pp_per_year`, break year 2021,
  post-break slope -0.96 percentage points/year, confidence 0.85.
- No credible break: Argentina, `carbon_intensity_gdp`, no segmented break,
  steady improvement.

## 9. Instability / uncertainty findings

Residual-bootstrap stability was run on 12 deterministic country-series
profiles, 30 iterations each, seed 42. Under the single-trend residual-bootstrap
null, break detection probability was 0.0 for all 12 profiles. Interpretation:
the current segmented breaks are not reproduced by resampled single-trend noise,
but Phase 1 does not yet establish precise breakpoint timing or forward-looking
usefulness. Phase 2 should replace this with historical-origin stability and
scenario backtesting.

## 10. Proposed regime feature contract

Phase 1 emits one row per country-series profile with:

- `latest_regime_start_year`
- `years_in_current_regime`
- `break_count`
- `strongest_break_year`
- `strongest_break_strength`
- `pre_break_slope`
- `post_break_slope`
- `slope_delta`
- `regime_direction`
- `regime_confidence`
- `current_regime_label`
- `break_method`
- `break_version`

Current labels are defined by slope direction, directionality, and credible
break evidence:

- `ACCELERATING_TRANSITION`
- `STEADY_IMPROVEMENT`
- `STALLED_TRANSITION`
- `DETERIORATING_TRANSITION`
- `INSUFFICIENT_EVIDENCE`

## 11. Tests added

Added 13 M7 unit tests covering insufficient history, minimum segment length,
no-break behavior, deterministic synthetic break detection, slope direction,
break strength/confidence, no future leakage, method agreement, bootstrap
determinism, candidate-series construction, unchanged v2 score constants, and
production run isolation.

Current focused M7 test result: 13 passed.

## 12. Git commit

`90cd446ef3d7be4b40baee30606d9aaf5eb45421` (`feat: add structural-break research framework`).

## 13. Phase 2 justification

Phase 2 is justified, but not production promotion. Phase 1 found real
candidate breaks and one robust method-agreement case, while also showing
substantial method sensitivity. The next gate must be historical-origin
recomputation and regime-aware scenario backtesting with calibration metrics.
