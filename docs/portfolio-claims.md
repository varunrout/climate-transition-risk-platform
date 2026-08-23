# Portfolio claims reference

Internal reference for how to describe this project accurately and
consistently. Anything not listed here as a valid claim area should be
checked against `docs/scope-v1.md` before use.

## A. Two-line project summary

A reproducible, evidence-backed sovereign climate transition-risk platform
built entirely on public data — from ingestion through a live, versioned
API and dashboard, deployed on serverless Azure infrastructure with
managed-identity-only authentication and GitHub Actions delivery.

## B. Three CV bullets

- Designed and deployed a reproducible sovereign climate-transition-risk
  platform (19 G20 economies) on Azure, combining a scoring model,
  backtested forward scenarios, and a fail-closed publication pipeline
  with full data/code provenance.
- Built a public-data ingestion and multi-layer (raw/bronze/silver/gold)
  data architecture with content-addressed source snapshots, a
  pre-registered model-promotion evidence gate, and rolling-origin
  backtesting against three candidate forecast models.
- Deployed a serverless Azure pipeline and read-only API using Terraform,
  managed identity (zero keys/SAS/connection strings), and GitHub
  Actions-built immutable container images; shipped a React analytics
  dashboard consuming a checksummed, versioned publication bundle.

## C. Longer project description

The Climate Transition Risk Intelligence Platform estimates sovereign
climate transition risk — the economic risk from the shift away from
fossil fuels — for 19 G20 economies, using only public, openly-licensed
data (Our World in Data, World Bank). It combines historical
decarbonisation pace, GDP/CO2 decoupling, volatility, forward scenario
exposure, and an energy-transition component into a single risk score,
validated by rolling-origin backtesting against multiple baseline models
and a pre-registered evidence gate for any new production method.
Research candidates that didn't clear that bar (regime-aware and
recency-weighted forecasting) were evaluated and explicitly not promoted
— a negative result the project reports rather than hides. The system
runs end to end on Azure (Container Apps, ADLS Gen2, Terraform-managed,
managed-identity-authenticated, zero keys/secrets), with container images
built by GitHub Actions and a React dashboard plus read-only FastAPI
serving a single deterministic, checksummed publication bundle so the two
surfaces can never disagree with each other.

## D. Technical stack

**Data/analytics**: Python 3.12, pandas, NumPy, SciPy, statsmodels,
Pydantic v2. **Pipeline**: Typer CLI, structlog, content-addressed
ingestion, fail-closed publication barrier. **API**: FastAPI, versioned
`/api/v1` contracts. **Frontend**: React 19, TypeScript, Vite, TanStack
Query, Zod, ECharts, d3-geo. **Infrastructure**: Terraform, Azure
Container Apps (Jobs + scale-to-zero API), Azure Data Lake Storage Gen2,
Azure managed identity, Azure Log Analytics. **Delivery**: GitHub Actions,
GitHub Container Registry, GitHub Pages. **Testing**: pytest, Vitest,
Playwright (live-deployment screenshot verification).

## E. Claims that must not be made

- **Not** a production financial investment or trading system — no
  investment recommendation, no execution capability.
- **Not** causal climate forecasting — the model estimates statistical
  association and historical trajectory, never a causal mechanism.
- **Not** physical climate risk — transition risk only (policy/market/
  technology shift), never flood/heat/sea-level/physical hazard exposure.
- **Not** a proprietary or institutional deployment — this is a public,
  openly-licensed portfolio project on Consumption-tier Azure
  infrastructure with no SLA.
- **Not** perfectly calibrated uncertainty — the production scenario
  method's measured 90% interval coverage is 76.3%, a known, published,
  unresolved undercoverage finding, not something to imply is solved.
- **Not** enterprise-scale — max 1 API replica, no CDN, no autoscaling
  beyond Container Apps defaults; appropriate for portfolio/research
  traffic, not high-volume commercial serving.

## F. Interview-ready explanation

"I built a system that turns three public datasets — CO2 emissions, GDP,
and energy-mix statistics — into a sovereign climate transition-risk score
for 19 G20 economies, with the full pipeline running on Azure end to end.
The interesting engineering problem wasn't the model itself, it was making
every stage of the pipeline honest about failure: an early version
silently fell back to local storage in Azure and reported success anyway,
so I built a fail-closed invariant that refuses to run rather than
silently degrade — and that's now the pattern the whole system follows,
including how a new model gets promoted to production (a pre-registered
evidence gate it either passes or doesn't) and how a data revision gets
detected (every source fetch is content-hashed, so a later run can prove
whether the underlying data actually changed). The result is a system
where I can point to exactly which commit, which data snapshot, and which
evidence produced any number the dashboard shows."
