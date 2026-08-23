# ADR 0018: M10 Read-Only API

## Status

Accepted.

## Context

M9 (ADR 0016) delivered a React static dashboard reading a committed
`gold/web` JSON snapshot -- deliberately independent of any backend. M10
adds a genuine serving layer for programmatic access, API/portfolio
demonstration, and future integrations, without changing that
independence: the dashboard must keep working unmodified from static
data regardless of whether this API exists, is deployed, or is down.

## Decision

### Source of truth: gold/web, not gold/bi

The API reads `gold/web/*.json` -- the same publication contract the
React dashboard already consumes (ADR 0017) -- rather than reading
`gold/bi/*.parquet` directly. Two reasons: (1) it means the API and the
dashboard can never drift into two different shapes of "the truth", and
(2) it means the API automatically inherits the `run_metadata` safelist
already enforced there, instead of needing a second, independently
maintained one. See `docs/api/contracts.md`.

### Fail-closed startup, not per-request validation

`climate_risk.api.repository.load_bundle()` performs a comprehensive set
of invariant checks (schema version, active score/scenario version,
per-file SHA-256/row-count integrity against the manifest, no duplicate
country keys, no unsafe `run_metadata` fields) once, at process startup,
inside FastAPI's `lifespan`. A failure here aborts startup entirely --
there is no state in which the process is "up" and serving from a known-
bad bundle. This mirrors the existing fail-closed publication barrier
(`climate_risk.publishing.barrier`) philosophy at the serving layer.

### Plain Python, not pandas, for the in-memory cache

The bundle is loaded once into `list[dict]`, not a pandas DataFrame.
`gold/web` is already JSON-safe (no NaN -- see
`climate_risk.bi.web_publish.json_safe`); round-tripping it through a
DataFrame would silently reintroduce NaN for missing values on the way
back out, which is exactly the class of bug `json_safe` exists to
prevent. Filtering/sorting/pagination is plain Python list comprehensions
-- the dataset (19 countries, a few thousand rows total) does not
justify pandas' overhead or its footguns here.

### Dedicated read-only Azure identity

A new `id-climate-risk-api` managed identity, `Storage Blob Data Reader`
only, distinct from the existing pipeline job's `Storage Blob Data
Contributor` identity. The API cannot write to the lake even if a future
code change tried to -- enforced by Azure RBAC, not application
convention alone. See `docs/api/security.md`.

### Scale-to-zero Container App, reusing all existing infrastructure

One new `azurerm_container_app` (`min_replicas = 0`, 0.5 vCPU / 1Gi, same
shape as the existing pipeline job) in the *same* Container Apps
Environment, against the *same* Log Analytics workspace and storage
account. Verified plan: 3 resources to add, 0 to change, 0 to destroy.
No new Container Apps Environment, Log Analytics workspace, storage
account, database, API Management, or Application Gateway. See
`docs/api/deployment.md` for the cost analysis.

### Frontend independence preserved

No change was made to `web/` to depend on this API. The deployed
GitHub Pages dashboard (M9) continues to load `web/public/data/*.json`
directly, unchanged. This API is additive, not a replacement for that
data path.

## Consequences

- A schema/version drift between `gold/web` and this API's expectations
  (`EXPECTED_ACTIVE_SCORE_VERSION`, `EXPECTED_PRODUCTION_SCENARIO_METHOD`
  in `climate_risk.api.repository`) is a hard startup failure, by design
  -- upgrading the API alongside a genuine score/scenario version change
  is a deliberate, visible step, not a silent pass-through.
- The API's Docker image (`Dockerfile.api`) is versioned and deployed
  independently of the pipeline image (`Dockerfile`) -- they can be
  rebuilt/redeployed on different cadences without coupling.
- Response contracts (`climate_risk.api.models`) are a second place that
  must be kept in sync with `gold/web`'s shape if a new field is added
  there; `tests/integration/test_api.py::TestContractAgainstPublishedArtifacts`
  exists specifically to catch drift, not prevent it structurally.
