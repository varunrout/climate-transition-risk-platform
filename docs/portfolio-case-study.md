# Case study: Climate Transition Risk Intelligence Platform

## Problem

Sovereign climate transition risk — the risk a country's economy faces
from the shift away from fossil fuels, not from physical climate hazards —
is discussed constantly but rarely quantified transparently. Existing
commercial products are opaque, proprietary, and expensive. Could a
reproducible, evidence-backed version be built entirely on public data,
with every claim traceable back to a specific dataset and a specific
evaluation?

## Why sovereign transition risk

Transition risk is genuinely measurable from public data in a way physical
climate risk (which needs proprietary geospatial/insurance data) usually
isn't: emissions, GDP, and energy-mix statistics are published annually by
OWID and the World Bank for every country, openly licensed. That made it
possible to build the whole pipeline — ingestion through published product
— without a single proprietary or paid data source.

## Data

Three sources (OWID CO2, World Bank WDI, OWID Energy), 19 G20 sovereign
economies, annual panel data. Every fetch is content-hashed and persisted
so a later data revision is detectable, not silently absorbed. See
`docs/data-card.md`.

## Analytical approach

A five-component risk score (pace, coupling, volatility, forward downside,
plus an energy-transition component added later) combined into a single
0-100 score, backed by rolling-origin backtesting against three candidate
forecast models and a weight-perturbation robustness check on every run.

## Evidence

The energy component wasn't added because it seemed reasonable — it was
proposed as a research candidate and had to pass a pre-registered gate
(coverage fixed in advance, permutation-test `p <= 0.10`, weight-robust
Spearman rho `>= 0.85`) before being promoted to production. See
`docs/governance.md` and ADR 0008/0009.

## Energy expansion

M6 added the energy-transition component (`energy_component_v2.1`) after
a three-phase evaluation: source verification and ingestion, an evidence
gate, and a 2000-permutation robustness hardening pass that froze the
final 2-signal, redundancy-reduced specification.

## Research decisions

M7 evaluated two further candidates — regime-aware and recency-weighted
forward scenarios — against the same evidence standard, and **rejected
both**. Structural-break diagnostics are kept visible on the dashboard as
interpretive, research-only evidence; they never feed the production
score or scenario. This negative result is preserved deliberately, not
buried, because a project that only ever reports positive results isn't
credible about its evaluation process.

## Production architecture

Azure Container Apps (a scheduled pipeline job + a scale-to-zero API),
ADLS Gen2, Terraform-managed infrastructure, managed identity throughout
(no keys, SAS tokens, or connection strings anywhere in the running
system). Container images are built by GitHub Actions and pushed to a
public GHCR registry with immutable Git-SHA tags — nothing about the
production supply chain depends on a local machine.

## Product

A React/TypeScript dashboard (7 routes) and a read-only FastAPI, both
served from a single deterministic, checksummed JSON publication bundle
(`gold/web`) — the dashboard and API can never disagree with each other
because they read the exact same files.

## Engineering incidents and lessons

Framed as validation of the architecture's failure modes, not as
embarrassments:

- **The silent-success storage incident (M6).** An early Azure promotion
  appeared to succeed but had silently fallen back to local ephemeral
  storage instead of ADLS — the job reported success while writing nothing
  durable. The fix was a fail-closed invariant
  (`validate_cloud_storage_invariant`) that now refuses to run rather than
  silently degrade, plus an ADR (0010) documenting exactly how the failure
  happened. This is the single most important lesson in the codebase: a
  green checkmark that means nothing is worse than a red one.
- **Power BI superseded by React (M9).** Nine real Desktop bugs were found
  and fixed building a native Power BI report; one report-canvas defect
  proved unresolvable and ended that route. The work is preserved as
  engineering history (`powerbi/`, `docs/powerbi/`), not deleted, and the
  decision to move to a web dashboard was a distribution/portability
  choice, not a claim Power BI is technically impossible (ADR 0015/0016).
- **The missing production `gold/web` (M10).** The scheduled Azure job
  computed valid analytics but never ran the downstream product-publication
  step — the API crash-looped on a dataset that had only ever existed
  locally. Rejected a one-off manual override (which would have repeated
  the M6 silent-fallback pattern) in favor of making product publication
  a persistent stage of the normal scheduled run (ADR 0019).
- **GitHub Actions replacing local Docker as the canonical build path.**
  Once local Docker Desktop repeatedly became the bottleneck (disk
  exhaustion mid-session, slow rebuilds), moving image builds to
  GitHub-hosted runners removed an entire class of "works on my machine"
  risk from the deployment pipeline — the production images are now built
  the same way regardless of which machine (or whether any machine) is
  driving the release.

## Result

A reproducible, evidence-backed sovereign transition-risk platform, live
end to end: public data in, a versioned analytical release, a checksummed
product bundle, a live dashboard, and a live read-only API — with every
number traceable back to the run that produced it.

## Limitations

Stated plainly, not hidden: annual (not real-time) data; a small 19-country
panel; historical values that can shift on upstream revision; measured
90% interval undercoverage (76.3% observed); a model that estimates
association and historical trajectory, not causal mechanism. See
`docs/model_cards/model-card.md` for the complete list.
