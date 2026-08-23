# M10: Read-Only API

## What this is

A read-only FastAPI serving layer over the platform's already-published
`gold/web` analytical output. It exists for programmatic access, an
API/portfolio demonstration, and future integrations -- it is **not**
required by the React dashboard (`web/`), which remains a fully
independent static site reading its own committed data snapshot. See
ADR 0018 for the full architecture decision.

## What it is not

- Not a second analytical implementation. Every value returned comes
  directly from the published `gold/web/*.json` bundle -- no risk
  scoring, scenario generation, backtesting, or diagnostic logic is
  reimplemented here. See `contracts.md`.
- Not a write API. Strictly `GET` -- no mutation endpoints exist.
- Not a live/real-time system. It serves the latest *published* run;
  see `GET /api/v1/meta` for exactly which one.

## Quickstart

```bash
uv sync --extra api
uv run climate-risk build-bi && uv run climate-risk build-web   # if not already published
uv run climate-risk api            # http://127.0.0.1:8000
```

Docs: http://127.0.0.1:8000/docs (Swagger) or `/redoc`. Machine-readable
contract: `/openapi.json`.

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/meta
curl http://127.0.0.1:8000/api/v1/countries/GBR
curl http://127.0.0.1:8000/api/v1/countries/IND/scenario
curl http://127.0.0.1:8000/api/v1/diagnostics/regimes/MEX
```

## Documents in this directory

- [`endpoints.md`](endpoints.md) -- full endpoint list and what each returns.
- [`contracts.md`](contracts.md) -- data source strategy, response contract
  design, and the startup-validation invariants that make this a
  fail-closed service.
- [`deployment.md`](deployment.md) -- local run, Docker, and the Azure
  Container Apps deployment design (cost gate, identity, scale-to-zero).
- [`security.md`](security.md) -- what is and is not exposed, CORS
  posture, and the managed-identity-only Azure access rule.
