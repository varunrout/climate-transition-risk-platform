# ADR 0009: M6 phase 3 -- evidence hardening, score v2 freeze, and production promotion

- Status: Accepted, promoted to production (local; Azure promotion tracked separately below)
- Date: 2026-08-22

## Context

ADR 0008 (M6 phase 2) reached an ACCEPT decision for an experimental
3-signal energy component using a 200-permutation test, and flagged two
caveats: (a) 200 permutations is a small null-distribution sample, and
(b) two of the three sub-signals (`low_carbon_share_elec`,
`fossil_persistence_mean_pct`) were found in the same redundancy cluster
(Spearman rho ~= -0.989). This ADR records the phase-3 work that addressed
both caveats with real computation against live data, froze a final
production specification, and promoted it into `cli.score()`/`cli.publish()`.

## 1. Strengthened permutation test

`climate-risk m6-harden --n-permutations 2000` (deterministic seed 42),
against the incumbent 3-signal component:

| | observed MAE improvement | permutation p | percentile within null | null mean | null std |
|---|---|---|---|---|---|
| 200 perms (ADR 0008) | 0.004785 | 0.045 | -- | 0.003322 | 0.000795 |
| **2000 perms** | 0.004785 | **0.052** | 94.8 | 0.003404 | 0.000794 |

The larger sample gives a more precise (and slightly weaker) p-value --
still under the ADR 0008 pre-declared 0.10 threshold, but honestly closer
to the boundary than the 200-permutation estimate suggested. This is
reported as-is, not re-run with a different methodology to chase
significance.

## 2. Redundancy-reduced component formulations

Three formulations compared on identical leave-one-country-out CV
(`climate_risk.research.m6_component_alternatives`,
`climate_risk.research.m6_phase3_harden`), 2000 permutations each:

| Formulation | LOCO MAE improvement | permutation p | leave-one-origin-out improvement | weight-robust min rho (+/-30%) | VIF |
|---|---|---|---|---|---|
| A: 3-signal (low_carbon + momentum + fossil_persistence) | 10.21% | 0.052 | 12.39% | 0.944 | up to 1.9-2.4 (clean) |
| **B: 2-signal (low_carbon + momentum) -- FROZEN** | 10.06% | 0.0545 | **13.13%** | 0.935 | 2.07 / 2.07 (clean) |
| C: 2-signal alternative (coal_share + momentum) | 4.90% | **0.987 (no signal)** | 11.87% | 0.942 | not computed (rejected on info content) |

Formulation C is a genuine negative result: a plausible-looking
alternative "less redundant" level signal (`coal_share_elec`, which stood
in its own redundancy cluster in ADR 0008) turned out to carry
essentially no incremental information (p=0.987 -- indistinguishable from
a random relationship). It was tested and rejected, not silently dropped.

Formulation B matches formulation A within noise on pooled LOCO MAE, is
*better* on leave-one-origin-out, has comparable (still well above the
0.85 threshold) weight robustness, and directly resolves the ADR 0008
redundancy finding by dropping `fossil_persistence_mean_pct`. Missing-data
behaviour was identical across all three (19/19 country coverage, 100%
mean confidence, current run). Per the explicit instruction to prefer the
simpler formulation when performance is statistically indistinguishable,
**formulation B is frozen as `energy_component_v2.1`**
(`climate_risk.scoring.energy_component`).

## 3. Lookback-window robustness

`lookback_instability_by_feature` (real data) shows the instability found
in ADR 0008 (mean Spearman 0.63 across 3/5/7yr windows) is **not evenly
distributed**:

| Feature | mean Spearman (3/5/7yr) | min Spearman |
|---|---|---|
| `fossil_persistence_mean_pct` | 0.989 | 0.981 |
| `coal_trend_pp_per_year` | 0.661 | 0.581 |
| `renewable_buildout_rate_pp_per_year` | 0.642 | 0.460 |
| `clean_power_momentum_pp_per_year` | **0.591** | **0.458** |

The windowed-mean feature (`fossil_persistence_mean_pct`, now dropped) was
actually the *most* stable of the four -- the instability is concentrated
in the OLS-slope ("momentum"/"trend") features, and `clean_power_momentum_pp_per_year`
(kept in the frozen spec) is the least stable of all four. **This caveat
is carried forward, not resolved**, by moving to the 2-signal formulation.

Country-level detail (`lookback_window_country_deltas`): Brazil is the
largest mover on momentum specifically, with the 3yr-vs-7yr slope even
flipping sign (-1.16 at 3yr vs +1.21 at 7yr pp/year).

A concrete "smoother construction" alternative was tested
(`theil_sen_vs_ols_lookback_stability`): a Theil-Sen robust slope in place
of OLS. Result: Theil-Sen did **not** improve stability (mean pairwise
Spearman 0.577 vs OLS's 0.591 on `low_carbon_share_elec`; identical
finding on `fossil_share_elec`) -- a genuine negative result. **The 5-year
OLS trailing window is retained as the canonical, frozen choice** --
because it is already used consistently elsewhere in this codebase
(v1's own `pace_recent_trend`), not because the instability was resolved.
No per-country tuning was introduced.

## 4. Temporal / origin robustness

Per-origin breakdown for the frozen formulation
(`leave_one_country_out_comparison_by_origin`):

| origin -> target | baseline MAE | augmented MAE | improvement |
|---|---|---|---|
| 2010 -> 2015 | 0.0607 | 0.0503 | +17.0% |
| 2012 -> 2017 | 0.0578 | 0.0398 | +31.1% |
| **2014 -> 2019** | 0.0437 | 0.0471 | **-7.8% (degrades)** |
| 2015 -> 2020 | 0.0409 | 0.0406 | +0.7% |
| 2016 -> 2021 | 0.0335 | 0.0326 | +2.6% |
| 2017 -> 2022 | 0.0447 | 0.0427 | +4.5% |

**Disclosed, not hidden**: energy features improve 5 of 6 historical
origins but materially *degrade* the 2014->2019 window. Leave-one-origin-out
CV (coarser, tests temporal generalisation) is still positive overall
(13.13% improvement, all formulations positive-direction), so the
degradation in one window doesn't flip the aggregate conclusion, but it is
a real limit on how uniformly this improvement should be trusted across
time.

## 5. Frozen v2 specification

`climate_risk.scoring.energy_component` (`ENERGY_COMPONENT_VERSION =
"energy_component_v2.1"`):

- **power_system_dependence**: `low_carbon_share_elec`, latest year, %
  of electricity generation. Higher = lower risk.
- **transition_momentum**: `clean_power_momentum_pp_per_year`, trailing
  5-year OLS slope, percentage points/year. Higher (rising) = lower risk.
- Combination: each converted to a 0-100 cross-sectional percentile
  (direction-adjusted), equal 1/2 weight, averaged over whichever
  sub-signals are present. `energy_confidence` = (signals present / 2) x 100.
- Minimum history: whatever `compute_energy_features`' `MIN_TRAILING_OBSERVATIONS`
  (3) requires for the momentum slope; no additional threshold added here.
- `climate_risk.scoring.risk_score_v2_energy`: `SCORE_VERSION = "v2_energy"`,
  `COMPONENT_VERSION = "energy_component_v2.1"`, `WEIGHTS_VERSION =
  "v2_weights_v1"`. Nominal weights: v1's already-reserved
  `NOMINAL_WEIGHTS["energy"] = 0.20`, all 5 nominal weights sum to 1.0.
  Missing energy data is renormalised per-country (v1's existing
  weighted_sum/weight_present pattern, unmodified) -- never fabricated as
  elevated risk; `weight_coverage` and `data_confidence_score` drop
  instead.

## 6-7. Production integration and versioning

`climate_risk.cli.score()` now computes **both**: v1 (unchanged
computation, written to `gold/country_transition_risk.parquet`, permanent
comparison artifact -- never deleted) and v2 (energy-augmented, written to
`gold/country_transition_risk_v2.parquet`). v2 computation is best-effort
inside `score()` (a missing energy silver table logs a warning and skips
v2; v1 is unaffected either way).

`climate_risk.cli.publish()` now **requires** both v1 and v2 artifacts
(added `country_transition_risk_v2.parquet` to the fail-closed barrier's
`required_artifacts`, and added `owid_energy` to the set of sources whose
ingestion manifest must be `ACCEPTED`). The publish manifest declares:
`score_version` = `v2_energy` (the active production score),
`comparison_score_version` = `v1`, `component_version`, `weights_version`,
`v1_artifact`/`v2_artifact` paths, `v1_countries_scored`/`v2_countries_scored`,
plus the existing `git_sha`/`config_hash`/`source_snapshot_ids`/`generated_at`.
`config_hash` now hashes both weight schemes and the component version.

## Local production run (real data, 2026-08-22)

Full `climate-risk run` (ingest -> build-silver -> energy-features ->
backtest -> score -> publish) against live upstream data. v1 unchanged
from every prior run (19 countries, same scores/ranks). v2: 19/19
countries scored, `energy_confidence=100`, `weight_coverage=1.0` for
every country (full current coverage).

| Country | v1 rank | v2 rank | rank delta | v1 score | v2 score | score_energy |
|---|---|---|---|---|---|---|
| MEX | 10 | 6 | **+4** | 57.57 | 62.89 | 84.21 |
| CHN | 7 | 10 | -3 | 65.13 | 58.95 | 34.21 |
| ITA | 11 | 14 | -3 | 39.47 | 34.21 | 13.16 |
| GBR | 13 | 16 | -3 | 35.53 | 31.05 | 13.16 |
| CAN | 18 | 15 | +3 | 27.30 | 32.37 | 52.63 |
| ARG | 6 | 8 | -2 | 72.04 | 62.89 | 26.32 |
| TUR | 2 | 4 | -2 | 80.26 | 70.53 | 31.58 |
| KOR, JPN | 14, 15 | 12, 13 | +2 each | -- | -- | -- |

Every mover is explainable directly from `score_energy` (the frozen
component's own 0-100 output): Mexico's energy component (84.2, high
risk -- persistently fossil-heavy, negative momentum) pulls it up from
v1's more moderate rank; China, Italy and the UK all have *lower*
energy-risk scores (34.2, 13.2, 13.2) than their v1-only rank implied,
pulling them down. Data confidence rose for every country
(e.g. Indonesia 27.22 -> 34.03) because `weight_coverage` moved from
v1's fixed 0.8 to v2's per-country 1.0 wherever energy data is complete
-- confidence, not risk, is what changed structurally.

`publish` succeeded: `active_score_version=v2_energy`, 19 v2 + 19 v1
countries, manifest fields verified present.

## 9. Regression tests

163 tests passing (was 140 before this phase; +23: strengthened
permutation/formulation-comparison tests, lookback diagnostic tests,
frozen-spec regression guards, and a new end-to-end CLI integration test
file, `tests/integration/test_publish_cli_v2_gate.py`, covering: publish
blocked when v2 missing, previous pointer left untouched when a
later run's v2 goes missing, and publish succeeding with the manifest
correctly declaring v2 as active). `ruff check`, `ruff format --check`,
`mypy src` all clean.

## Consequences

- v2 (`energy_component_v2.1` / `v2_energy` / `v2_weights_v1`) is now the
  **local production score** -- `cli.score()` and `cli.publish()` compute
  and require it. v1 remains permanently available as a comparison
  artifact and is provably byte-for-byte unaffected
  (`tests/unit/test_risk_score_v2_energy.py::test_v1_available_components_still_exclude_energy`).
- Two real, disclosed limitations travel forward with the frozen spec:
  the retained momentum feature's lookback-window sensitivity (not
  resolved; a robust-estimator alternative was tested and didn't help),
  and the 2014->2019 origin's negative energy-feature contribution. Both
  are documented here rather than smoothed over.
- Azure has **not** yet run this. Docker image build/push, Terraform
  update, and one manual Azure execution are the remaining steps before
  M6 can be marked COMPLETE -- tracked in the sections below / the final
  report.
