# ADR 0008: M6 phase 2 -- energy feature evaluation and score-integration gate

- Status: Accepted (decision recorded; NOT yet promoted to production)
- Date: 2026-08-22

## Context

ADR 0007 (M6 phase 1) ingested OWID electricity-mix data and computed
diagnostic energy-transition features, explicitly stopping short of
touching `scoring/risk_score.py`. This ADR records M6 phase 2: a
pre-registered, mechanical evidence gate that decides whether an energy
component should exist at all, using real computation against the live
local lake -- no numbers in this document are invented or estimated.

v1 (`gold/country_transition_risk.parquet`, `climate_risk.scoring.risk_score`)
is **untouched**. Everything in this ADR lives in
`climate_risk.research.m6_*`, `climate_risk.scoring.energy_component`, and
`climate_risk.scoring.risk_score_v2_energy` -- new, additive modules that
v1 does not import and `cli.score()`/`cli.publish()` do not call. `climate-risk
m6-evaluate` is a new, separate, research-only CLI command.

## 1. Baseline freeze

`gold/research/m6/baseline_v1_frozen.json` captures v1's score version,
nominal/effective weights, `weight_coverage=0.8`, every country's score/
rank/confidence, the rank-stability result, and the latest publish
manifest -- frozen at this commit and never overwritten by anything below.

## 2-3. Evaluation panel + coverage

`gold/research/m6/evaluation_panel.parquet` joins the existing v1 raw
metrics (`carbon_intensity_trend`, `coupling_elasticity`) with 10 candidate
energy features across all 19 countries. Full provenance (source columns,
unit, transformation, directionality, lookback, notes) for every candidate
is in `gold/research/m6/feature_catalog.parquet`
(`climate_risk.research.m6_panel.FEATURE_CATALOG`).

Coverage thresholds were fixed in code *before* this evaluation ran
(`climate_risk.research.m6_coverage`): `MIN_COUNTRY_COVERAGE_PCT=90%`,
`MIN_COUNTRY_YEAR_COVERAGE_PCT_10YR=85%`, `MAX_STALE_DATA_RATE=10%`,
`MIN_HISTORY_YEARS_FOR_TREND=5`. Result: the three source features behind
the eventual compact component (`low_carbon_share_elec`,
`clean_power_momentum_pp_per_year`, `fossil_persistence_mean_pct`) each hit
**100% country coverage** (19/19), 0% stale rate, and 98.9% country-year
coverage over the trailing 10 years for the raw level. **Coverage gate:
PASSED.**

## 4. Stability

- One-year revision sensitivity (drop each country's own latest year and
  recompute): mean shift 0.14 deciles, max 1.58 deciles, 0 countries
  dropped from the panel entirely -- small and not concerning.
- Trailing-window sensitivity (3yr vs 5yr vs 7yr) for the trend/momentum
  features: mean Spearman rank correlation across window pairs **0.63**,
  minimum **0.46**. This is a genuine caveat, not a pass: the trend/momentum
  features are moderately sensitive to the lookback window choice, and a
  5-year window (this evaluation's default, matching the rest of the
  codebase) is a defensible but not uniquely-correct choice.

## 5. Redundancy / collinearity

Hierarchical clustering (Spearman distance, threshold 0.7) on the 12
candidate features found **7 redundancy groups**, confirming the M6 brief's
expectation that mechanically related shares don't carry independent
information: `{fossil_persistence_mean_pct, fossil_share_elec,
low_carbon_share_elec, renewables_share_elec}` cluster together (group 4),
and `{clean_power_momentum_pp_per_year, renewable_buildout_rate_pp_per_year,
transition_velocity}` cluster together (group 3). `coal_share_elec`,
`coal_trend_pp_per_year`, `stalled_transition_residual_pp`,
`carbon_intensity_trend` and `coupling_elasticity` each stood alone.

VIF on the full 12-feature design matrix is degenerate as expected at
n=19 with mechanically dependent shares (`fossil_share_elec` VIF ~3e14,
`fossil_persistence_mean_pct` VIF ~3e14, `clean_power_momentum_pp_per_year`
VIF ~1e12) -- this is exactly why a compact, one-signal-per-concept
component was designed rather than scoring every candidate. **Honest
caveat carried into the component design below**: `low_carbon_share_elec`
and `fossil_persistence_mean_pct`, the two "level" signals chosen for the
compact component, are themselves in the *same* redundancy group (Spearman
rho = -0.989, near-mechanical). The compact component described in
section 8 therefore has closer to 2 independent degrees of freedom (level,
momentum) than 3 -- this is disclosed, not hidden by picking a
better-sounding second feature after the fact.

## 6-7. Incremental information + temporal backtest (one evaluation, both questions)

Target/proxy stated explicitly: observed `carbon_intensity_gdp` at each of
the same 6 rolling origins already used by `climate_risk.backtesting.rolling_origin`
(2010->2015 ... 2017->2022), baseline = the existing deterministic
log-linear trend forecast. Energy features are computed from a panel
truncated to `year <= origin_year` using the exact same production
function (`compute_energy_features`) that would run in inference -- so
"no future leakage" is structural, not just tested for (and is tested for
explicitly in `tests/unit/test_m6_incremental.py::test_no_future_leakage_in_energy_features`).

Method: fit a linear correction from the 3 compact energy features to the
baseline's log-residual, evaluated via **leave-one-country-out
cross-validation** (114 splits across 19 countries):

| | baseline only | baseline + energy correction |
|---|---|---|
| MAE (carbon_intensity_gdp) | 0.046877 | 0.042091 |

Improvement: **0.004785 (10.2%)**. A 200-permutation null-distribution test
(shuffle the energy features across the same rows, refit, remeasure) gives
**p = 0.045** -- i.e. a random relationship between these features and the
outcome would produce an improvement this large only 4.5% of the time.
Ablation (`gold/research/m6/incremental_ablation.parquet`) shows the
improvement is not driven by a single feature alone; the combined set
outperforms each in isolation.

## 8. Energy component definition

`climate_risk.scoring.energy_component.compute_energy_component` -- three
sub-signals, equal 1/3 weight, each a cross-sectional percentile score
(0-100, direction-adjusted so higher always means higher risk), averaged
over whichever sub-signals are present for a country (`energy_confidence`
records how many of the 3 were available):

- **power_system_dependence**: `low_carbon_share_elec` (latest year; higher share = lower risk)
- **transition_momentum**: `clean_power_momentum_pp_per_year` (trailing 5yr OLS slope; higher = lower risk)
- **fossil_persistence**: `fossil_persistence_mean_pct` (trailing 5yr mean fossil share; higher = higher risk)

## 9. Score v2 experiment

`climate_risk.scoring.risk_score_v2_energy` adds this as a 5th component
using the weight already reserved in v1's `NOMINAL_WEIGHTS["energy"]=0.20`
(v1's other four weights sum to 0.80 exactly, so v2's five nominal weights
already sum to 1.0 -- no rescaling needed). Written to
`gold/research/m6/score_v2_energy_experimental.parquet`, **never**
overwriting `gold/country_transition_risk.parquet`.

All 19 countries had `energy_confidence=100` and `weight_coverage=1.0` in
this run (matches the coverage-gate result). Comparison
(`gold/research/m6/score_v1_vs_v2.parquet`):

| Country | score v1 | rank v1 | score v2 | rank v2 | score_energy | delta | rank delta |
|---|---|---|---|---|---|---|---|
| BRA | 73.36 | 5 | 62.54 | 7 | 19.30 | -10.81 | -2 |
| TUR | 80.26 | 2 | 70.88 | 4 | 33.33 | -9.39 | -2 |
| ARG | 72.04 | 6 | 64.65 | 5 | 35.09 | -7.39 | +1 |
| JPN | 32.24 | 15 | 37.72 | 13 | 59.65 | +5.48 | +2 |
| AUS | 21.38 | 19 | 26.58 | 19 | 47.37 | +5.20 | 0 |
| MEX | 57.57 | 10 | 62.54 | 8 | 82.46 | +4.98 | +2 |

Every mover is explainable directly from the source data: Brazil and
Turkey both score low on the new energy component (Brazil already runs a
mostly-hydro/renewable grid -- low_carbon_share_elec is high, i.e. low
energy risk -- while its *other* four v1 components rank it in the
"elevated" band; adding a genuinely-lower-risk energy signal pulls its
total down and its rank falls). Japan and Mexico move up because their
energy-component scores (59.65, 82.46) are *higher risk* than their v1
scores implied, based on real fossil-persistence/momentum data, not an
artifact.

**v1 vs v2 Spearman rank correlation: 0.951** -- a real, non-trivial shift
for a handful of countries, but not a reordering of the whole panel.

## 10. Weight robustness (v2)

Same methodology as v1's `weight_perturbation_analysis`, run at three
perturbation magnitudes:

| Perturbation | mean Spearman rho | min Spearman rho | mean max rank movement |
|---|---|---|---|
| +/-10% | 0.9959 | 0.9842 | 0.98 |
| +/-20% | 0.9912 | 0.9649 | 1.48 |
| +/-30% | 0.9851 | 0.9439 | 1.94 |

Comparable to v1's own +/-30% result (mean 0.989, min 0.953) -- v2 is not
meaningfully less weight-robust than v1.

## 11. Missing-data behaviour

Tested explicitly (`tests/unit/test_risk_score_v2_energy.py::test_missing_energy_does_not_inflate_risk`
and `test_energy_confidence_zero_when_component_missing`): a country
missing its energy component gets `weight_coverage < 1.0` and a
correspondingly lower `data_confidence_score`, but `score_total` is still
computed from the renormalised remaining four components -- absence of
energy data is never scored as elevated risk. In this run every country
had full energy coverage, so this behaviour was exercised only in tests,
not in the real evaluation panel.

## 12. Governance

`SCORE_VERSION = "v2_energy_experimental"` is a distinct, explicit field on
every v2 row. v1's gold artifacts, manifests, and
`gold/research/m6/baseline_v1_frozen.json` are untouched and remain the
production score. No historical artifact was rewritten.

## 14. Decision

Applying the fixed, pre-declared decision rule
(coverage gate -> incremental-information evidence -> weight robustness,
`cli.m6_evaluate`'s decision block) to the real results above:

**ACCEPT** -- coverage gate passed; leave-one-country-out MAE improved by
0.0048 (10.2%) with permutation p=0.045 (<=0.10 threshold); weight-robust
at +/-30% (min Spearman rho 0.944 >= 0.85 threshold).

This is a real, mechanically-applied outcome of the evaluation, not a
predetermined result -- the same code would have printed DIAGNOSTICS_ONLY
or REVISE had the coverage, permutation, or robustness checks failed.

## 16. Azure / production status

**Not deployed.** `cli.score()` and `cli.publish()` are unchanged and
still compute only v1. The Azure Container Apps Job continues running the
last verified production image (ADR 0006) unmodified. Promoting
`score_v2_energy_experimental` to be the default production score --
updating `cli.score()`, rebuilding/pushing a new image, and redeploying --
is a distinct, not-yet-taken decision that would change live production
output and was explicitly out of scope for this evaluation pass.

## Consequences

- M6 phase 2's evidence gate concluded ACCEPT with real numbers; the
  compact energy component is a candidate 5th score component with
  genuine (if modest, 10.2% MAE improvement, p=0.045) out-of-sample
  support, comparable weight-robustness to v1, and full current-run
  coverage.
- The lookback-window sensitivity (mean Spearman 0.63 across 3/5/7yr
  windows) and the near-mechanical redundancy between the two "level"
  sub-signals are real caveats carried forward, not resolved by this ADR.
- v1 remains the sole production score. Promoting v2 requires a separate,
  explicit decision and deployment step -- not implied by this ADR.
