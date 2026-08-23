# Model card: sovereign climate transition risk score

**Production version:** `v2_energy` · **Energy component:** `energy_component_v2.1` · **Production scenario method:** `empirical_bootstrap_v1` · **Comparison baseline:** `v1`

## Model purpose

This model estimates **climate *transition* risk** for sovereign
economies: the risk a country's economy faces from the policy, market, and
technology shift away from fossil fuels — not the risk from physical
climate hazards (flooding, heat, sea-level rise). It combines historical
decarbonisation pace, GDP/CO2 decoupling strength, volatility, forward
downside scenario exposure, and an energy-system transition component into
a single 0-100 risk score, plus a rank and a separately-reported data
confidence score.

## Scope

19 sovereign G20 economies (`config/countries.yaml`). The EU is a G20
member but an aggregate region, not a sovereign country, and is
deliberately excluded — aggregates must never leak into a sovereign
ranking. Annual panel, historical years through the latest model-eligible
year (published at `/api/v1/meta` as `model_eligible_year`).

## Intended use

Portfolio, research, and analytical demonstration of sovereign
transition-risk exploration: comparing countries' transition trajectories,
exploring forward scenario uncertainty, and understanding which drivers
(pace, coupling, volatility, forward downside, energy) contribute most to
a given country's score.

## Not intended for

- **Investment execution without independent validation.** This is not a
  licensed financial product and carries no investment recommendation.
- **Credit decisions or regulatory capital calculations.**
- **Physical climate risk assessment** — this model does not estimate
  flood, heat, drought, or sea-level exposure.
- **Individual company or facility-level assessment** — sovereign-level
  only.

## Inputs

- **Economic**: GDP (constant local currency-free 2015 US$), population
  (World Bank WDI)
- **Emissions**: CO2 emissions, carbon intensity of GDP (OWID CO2)
- **Energy system**: coal/fossil/renewables/low-carbon share of
  electricity generation (OWID Energy, re-published from Ember + Energy
  Institute Statistical Review of World Energy)

See `docs/data-card.md` for full provenance, licensing, and missingness
handling per source.

## Outputs

- `score_total` (0-100, higher = higher transition risk) and `rank`
  (1 = highest risk among covered countries)
- `rank_band` (qualitative: high / elevated / moderate / lower)
- Five score components: pace, coupling, volatility, forward_downside,
  energy
- `data_confidence_score` (0-100), reported **separately** from risk —
  low confidence never implies higher risk, and the two must never be
  conflated in any presentation of this model's output
- Forward scenario quantiles (P5/P50/P95) under the production
  `empirical_bootstrap_v1` method
- `v1` comparison score and rank, retained alongside every `v2_energy`
  record so a reader can see exactly what the energy-system expansion
  changed
- M7 structural-break diagnostics, clearly labelled research-only,
  presented for interpretation but never as a production forecast input

## Production methods

- **`v2_energy`** — the active production score. Adds an energy-transition
  component (`energy_component_v2.1`) to the four components already
  present in `v1` (pace, coupling, volatility, forward_downside).
- **`energy_component_v2.1`** — a 2-signal, redundancy-reduced
  specification (coal-share trend + clean-power momentum), frozen after a
  2000-permutation robustness hardening pass (ADR 0009).
- **`empirical_bootstrap_v1`** — the production forward-scenario method:
  seeded bootstrap resampling of historical year-over-year changes,
  producing P5/P50/P95 forecast quantiles. Chosen in production over a
  deterministic-trend baseline after backtesting showed materially better
  interval coverage (see Validation below).

## Validation

- **Rolling-origin backtesting**: origins spanning multiple historical
  years, walked forward against actual realized values, comparing
  `empirical_bootstrap`, `deterministic_trend`, and a `no_change` naive
  baseline. Reported metrics: MAE, RMSE, median absolute error, and (for
  `empirical_bootstrap`) 90% interval coverage and mean interval width.
  Live values are always available at `/api/v1/backtests` and on the
  Model Evidence dashboard page — this card intentionally does not
  hard-code numbers that would go stale; read them from the running
  system, not this document.
- **Baseline comparison**: `empirical_bootstrap` is only kept in
  production because it beats both `deterministic_trend` and `no_change`
  on MAE; the comparison is re-computed and re-published on every run,
  not asserted once and assumed to hold forever.
- **Energy component evidence gate** (ADR 0008): the energy component was
  only promoted to production after a pre-registered acceptance gate
  (`p <= 0.10` on a permutation test, positive MAE improvement over the
  four-component `v1` baseline, weight-perturbation robustness) — see
  `docs/governance.md` for the exact criteria preserved unmodified.
- **Score robustness**: weight-perturbation Monte Carlo (Spearman rank
  correlation and maximum rank movement under randomized weight
  perturbation) run on every score, reported in pipeline logs and the
  run manifest.

## Known limitations

- **Annual data** — no intra-year or real-time signal; a fast-moving
  policy shift will not appear until the next annual data release.
- **Small sovereign panel (n=19)** — statistical power for cross-country
  inference is limited; results should be read as descriptive/comparative
  evidence, not as a large-sample statistical claim.
- **Source revisions** — upstream providers (OWID, World Bank) revise
  historical values as their own methodology and reporting improve; a
  country's historical score can shift on a later run purely from a
  source revision, not a model change. See `docs/reproducibility.md` for
  how this is detected and reported.
- **Uncertainty undercoverage** — backtested 90% interval coverage from
  `empirical_bootstrap_v1` is below the nominal 90% target (see the live
  `coverage_90` figure at `/api/v1/backtests` and the Model Evidence
  page); intervals should be read as informative, not as calibrated
  confidence bounds in the strict statistical sense.
- **Historical extrapolation limits** — bootstrap resampling of
  historical changes cannot anticipate genuinely novel future dynamics
  (e.g. an unprecedented policy shock) that has no analogue in the
  historical record it resamples from.
- **Public-data dependency** — the model's accuracy and coverage are
  bounded by what OWID and the World Bank publish; a source outage or a
  country's temporary removal from a source directly degrades that
  country's `data_confidence_score` and the model fails closed rather
  than silently filling gaps (see Governance).
- **M7 regime-aware methods not promoted** — structural-break-aware and
  recency-weighted scenario variants were researched and evaluated (ADR
  0011-0014) and are **not** in production; see Research negative results
  below.

## Research negative results (preserved, not hidden)

M7 evaluated two production candidates and rejected both, on evidence:

- **Regime-aware scenario forecasting** (ADR 0013): decision
  `RECENCY_WEIGHTING_ONLY` — full regime-switching was not promoted.
- **Recency-weighted scenario forecasting** (ADR 0014): decision
  `KEEP_EXISTING_EMPIRICAL_BOOTSTRAP_IN_PRODUCTION` — recency weighting
  showed only small accuracy gains, failed a country-level robustness
  check, and did not close the P5-P95 coverage gap below the nominal 90%
  target. Structural-break diagnostics are retained as interpretive,
  research-only evidence (visible on the Structural Diagnostics dashboard
  page, clearly labelled), never as a production score or scenario input.

This negative result is preserved deliberately: it is evidence the
evaluation process works, not a gap to be quietly closed by re-running the
experiment until it looks better.

## Ethical / decision limitations

This model estimates statistical association and historical trajectory,
not causal mechanism. A high transition-risk score does not mean a
specific policy caused it, and a low score does not mean a country's
transition is causally "on track" for any particular future outcome. The
model should inform further investigation, not substitute for it, and
should never be the sole input to an investment, credit, or policy
decision.
