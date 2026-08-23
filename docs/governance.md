# Governance

How this project decides what reaches production, how it handles data
revisions and score-version changes, and what happens when something fails.
This consolidates decisions already made across the ADRs (`docs/adr/`) into
one release-facing reference — it does not introduce new criteria.

## Research vs production distinction

Every analytical method in this repository is one of exactly two states:

- **Production** — actively used to compute the score/scenario values the
  API and dashboard serve, labelled as such everywhere it appears
  (`ProductionTag` component in the dashboard, explicit versioned fields
  in every API response).
- **Research-only** — evaluated, documented, and either rejected or held
  pending further evidence. Displayed, when shown at all, behind an
  explicit "research/diagnostic only" label. Never silently promoted.

M7's structural-break diagnostics are the clearest example: they are
genuinely useful for interpretation (understanding *why* a country's
trajectory looks the way it does) and are kept visible on the dashboard,
but are never fed into the production score or scenario.

## Model-promotion criteria (as actually applied)

The energy component (`energy_component_v2.1`, promoted to production as
`v2_energy`) is the one case in this project's history where a new
production method was proposed and evaluated end to end. The gate it had
to pass (ADR 0008), preserved exactly, not tightened after the fact:

1. **Coverage gate**: fixed *before* evaluation ran, not adjusted afterward
   to fit the result.
2. **Incremental-information / permutation test**: `p <= 0.10` — actual
   result `p = 0.045`, with a `10.2%` MAE improvement (`0.0048` absolute)
   over the four-component `v1` baseline.
3. **Weight-perturbation robustness**: minimum Spearman rank correlation
   `>= 0.85` at +/-30% weight perturbation — actual result `0.944`.

All three had to pass simultaneously; a REJECT or REVISE decision was the
default outcome had any one failed. This is the standard this project holds
itself to for any future production-score change, not a one-off bar cleared
once and forgotten.

M7's two candidate promotions (regime-aware and recency-weighted forward
scenarios) were evaluated against comparable evidence standards and
**rejected** — see ADR 0013 and ADR 0014, and `docs/model_cards/model-card.md`'s
"Research negative results" section. Rejection is treated as a valid,
reportable outcome of the evaluation process, not a failure to hide.

## Source revision handling

Every raw fetch is content-hashed (`source_snapshot_id`) and persisted,
never overwritten (`docs/data_cards/data-card.md`). This makes source
revisions **detectable by construction**: comparing the current
production `source_snapshot_ids` against a fresh fetch's hashes is how
`docs/reproducibility.md`'s data revision analysis works. When a revision
is detected:

1. The revision is documented — snapshot hash change, row count change,
   affected country-years — **before** any interpretation.
2. A release-materiality threshold, fixed here rather than chosen after
   seeing a candidate's results, is applied to a controlled candidate run
   built from the revised data: **mean absolute score delta > 2.0 points,
   OR max score delta > 5.0 points, OR Spearman rank correlation < 0.98,
   OR any country's rank moving by more than 2 positions**. Crossing any
   one of these is material.
3. Immaterial revisions are documented and the release proceeds
   unmodified. Material revisions (a threshold crossed, or a rank
   reordering that would change the reported "highest risk" country) block
   the release until reported and reviewed — never silently absorbed.

## Score-version changes

A new production score version follows the same path the energy component
did: proposed as a research candidate, evaluated against a pre-registered
gate, and only promoted on passing evidence. `v1` remains visible as a
comparison score in the product indefinitely after `v2_energy`'s
promotion — a score-version change is additive to the public record, not
a silent replacement of history.

## Evidence gates

Every production claim in this project is backed by a gate that can be
independently re-run:

- Rolling-origin backtesting (walk-forward, not in-sample)
- Baseline comparison (`empirical_bootstrap` vs `deterministic_trend` vs
  `no_change`, re-computed every run, never asserted once)
- Weight-perturbation robustness (Monte Carlo, reported per run)
- The energy-component incremental-information/permutation gate above

## Fail-closed analytical publication

`climate_risk.publishing.barrier`'s fail-closed rule: a `publish()` that
would produce an incomplete or invalid release (missing v2 scores, a
storage-runtime invariant violation, a validation failure) **cannot
overwrite the previously published release**. The pointer to "the current
release" only ever advances on a fully successful publish. Verified on the
real CLI path, not just in unit tests
(`tests/integration/test_publish_cli_v2_gate.py`).

## Downstream product publication

`gold/bi`/`gold/web` (the product layer the dashboard and API serve) is
published by a separate, downstream stage (`publish_product`, ADR 0019)
that runs only after core analytical publication has already succeeded.
A product-publication failure is reported loudly (non-zero exit, logged
error) but **never** rolls back or corrupts the already-valid core
release — the two layers fail independently, and a broken product layer
never causes a broken analytical layer to appear published, or vice versa.

## Rollback principles

- **Core analytical release**: the fail-closed barrier above means there
  is rarely anything to "roll back" — a bad publish attempt simply never
  becomes the current release. Recovering from a genuinely bad *promoted*
  release means re-running `publish()` with corrected inputs/code, which
  produces a new release, not a patch to the old one; the old release's
  manifest remains in `gold/manifests/` as an audit trail.
- **Container images**: immutable, full-Git-SHA-tagged. Rolling back the
  running application means repointing Terraform's `image_tag`/
  `image_digest` variables at an earlier already-built image and
  re-applying — no rebuild required, and the change is a single reviewable
  Terraform plan.
- **Infrastructure**: every infrastructure change goes through
  `terraform plan` before `apply`; an unexpected destroy/replace in a plan
  is a stop condition, not something to apply through.

## ADR discipline

Every non-trivial architectural or analytical-promotion decision in this
project has a corresponding ADR in `docs/adr/` (19 at the time of the
v1.0.0 release), written at the time the decision was made, not
retroactively reconstructed to justify an outcome. ADRs are never rewritten
to make a past decision look better in hindsight — an ADR that turned out
to be wrong (e.g. ADR 0010's Azure promotion failure) stays as-written,
with a follow-up ADR recording the fix.

## Release tagging

A release is tagged (`vX.Y.Z`, annotated) only after: local quality gates
pass, GitHub Actions CI is green on the exact commit being tagged, and (for
a release with runtime-affecting changes) a final production run has been
verified end-to-end against live Azure infrastructure. The tag always
points at the exact commit whose CI passed — never at a later or earlier
commit, and never while CI is red.
