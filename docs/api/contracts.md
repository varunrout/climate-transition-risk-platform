# Data Source Strategy and Response Contracts

## Source of truth

```
Python analytical pipeline -> gold/bi -> gold/web (climate_risk.bi.web_publish)
                                              |
                                              v
                              climate_risk.api.repository.load_bundle()
                                              |
                                              v
                                   in-memory, request-served
```

The API reads `gold/web/*.json` -- the **same publication contract the
React dashboard consumes** (ADR 0017) -- not `gold/bi` directly. This is
deliberate: it means the API and the dashboard can never drift into two
different shapes of "the truth", and it means the API automatically
inherits `gold/web`'s existing safety property (the `run_metadata`
safelist, see `security.md`) instead of needing a second one.

The request path is always:

```
published artifact (gold/web/*.json) -> validation -> API response
```

**Never** `HTTP request -> rerun model`. `climate_risk.api.repository`
loads the bundle exactly once, at process startup (see below), and every
request thereafter is served from that in-memory copy. Deliberately plain
Python `list[dict]`, not pandas -- the bundle is already JSON-safe (no
NaN; see `climate_risk.bi.web_publish.json_safe`), and round-tripping it
through a DataFrame would silently reintroduce NaN for missing values,
which is exactly the class of bug that module exists to prevent.

## Startup validation (fail-closed)

`climate_risk.api.repository.load_bundle()` raises `StartupValidationError`
-- which aborts FastAPI's `lifespan` and prevents the process from ever
accepting a request -- if any of the following don't hold:

1. Every expected `gold/web/*.json` file exists.
2. `manifest.json` parses as valid JSON.
3. `manifest.schema_version` is one this API build supports.
4. `manifest.active_score_version == "v2_energy"` (the expected
   production score -- see `climate_risk.scoring.risk_score_v2_energy.SCORE_VERSION`).
5. `manifest.active_scenario_method == "empirical_bootstrap_v1"`.
6. Every file's actual SHA-256 and row count match what the manifest
   declares (catches a corrupted or partially-written bundle).
7. `country-overview.json` has no duplicate `country_iso3` keys.
8. `run-metadata.json` has at least one row, and every field in it is on
   the public safelist (`RUN_METADATA_SAFE_FIELDS`).

There is deliberately no "serve anyway with a warning" path. A bundle
that fails any of these checks is not servable, full stop -- see
`docs/adr/0018-m10-read-only-api.md` for the rationale.

## Response contracts

Every public response is an explicit Pydantic v2 model
(`climate_risk.api.models`) -- never a bare `dict[str, Any]`. Field names
are deliberately **not** a 1:1 mirror of the internal `gold/web` column
names where a clearer public shape exists (e.g. `score_total` ->
`risk_score`); the *values* always come straight from the bundle,
unmodified.

Key models: `ApiMetadata`, `CountrySummary`, `CountryProfile` (composed
of `ScoreComparison`, `RiskComponent`, `LatestTransitionSnapshot`,
`LatestEnergySnapshot`, `ScenarioSummary`, `ProvenanceRef`),
`CountryTimeseriesPoint`, `EnergyTimeseriesPoint`, `BacktestRecord`,
`RegimeDiagnostic`, `RankingResponse`.

## Contract testing

`tests/integration/test_api.py::TestContractAgainstPublishedArtifacts`
builds a real `gold/bi` -> `gold/web` bundle (via the actual
`climate_risk.bi.publish` / `climate_risk.bi.web_publish` code, not
hand-written fixtures) and asserts representative API fields --
risk score, rank, confidence, scenario quantiles, energy values,
component contributions -- are byte-identical to the source JSON. This
is the guard against the API silently becoming a second analytical
implementation.
