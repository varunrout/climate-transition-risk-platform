# v1.0.0 release scope

This document freezes what the v1.0.0 release covers and, just as
importantly, what it deliberately does not. It is a scope boundary, not a
roadmap — anything listed as out of scope is a considered exclusion, not a
promise of future work.

## In scope

**Data.** 19 sovereign G20 economies (the EU is a G20 member but an
aggregate region, not a sovereign country, and is deliberately excluded —
see `config/countries.yaml`). Annual panel data from three public sources:
OWID CO2, World Bank WDI, OWID Energy (see `docs/data-card.md`).

**Analytics.**
- Carbon intensity and GDP/CO2 decoupling analytics
- Energy-transition indicators (coal/fossil/renewables/low-carbon share of
  electricity, transition velocity, stalled-transition residual)
- Transition risk score `v2_energy` (production) with `v1` retained as a
  comparison baseline
- Empirical bootstrap production forward scenarios (`empirical_bootstrap_v1`)
- Rolling-origin backtesting and calibration evidence
- M7 structural-break diagnostics, explicitly **research-only evidence**,
  never a production score or scenario input

**Product.**
- React web dashboard (7 routes, production/research semantics enforced
  throughout)
- Versioned `gold/web` JSON publication bundle with a checksummed manifest
- Read-only FastAPI (`/api/v1/*`, OpenAPI-documented)

**Runtime.**
- Azure Container Apps Job (scheduled pipeline) + Azure Container App
  (scale-to-zero API), Azure Data Lake Storage Gen2, managed identity
  (no keys/SAS/connection strings), Terraform-managed infrastructure

**Delivery.**
- GitHub Actions (CI, container image builds, GitHub Pages deployment)
- GitHub Container Registry (public, immutable Git-SHA-tagged images)
- GitHub Pages (static dashboard hosting)

## Explicitly out of scope for v1

- **Physical climate risk** (flooding, heat, sea-level exposure) — this
  platform models transition risk (policy/market/technology shift away from
  fossil fuels) only, never physical hazard.
- **Corporate/entity-level transition risk** — sovereign-level only; no
  company, facility, or asset-level analysis.
- **Real-time or streaming data** — sources refresh weekly/monthly at the
  provider's own cadence; there is no live feed and no intraday update.
- **Tracking data or news-derived signals** — every input is a public,
  versioned statistical dataset, never a scraped or tracked signal.
- **Proprietary or licensed datasets** — every source is openly licensed
  (CC-BY-4.0) and publicly re-fetchable by anyone.
- **Regime-aware production forecasting** — researched under M7, evaluated,
  and explicitly not promoted (see `docs/governance.md` and ADR 0013).
- **Recency-weighted production forecasting** — same M7 research track,
  same explicit non-promotion decision (ADR 0014).
- **User-authenticated API** — the API is anonymous and read-only; there is
  no login, no per-user state, no write path.
- **Write API / data mutation endpoints** — the API can only ever serve an
  already-published bundle, never accept or store new data.
- **Commercial SLA** — this is a portfolio/demonstration system on
  Azure Consumption-tier, scale-to-zero infrastructure with no uptime
  guarantee.
- **High-scale serving architecture** — max 1 API replica, no CDN, no load
  balancer, no autoscaling beyond the Container Apps default; appropriate
  for portfolio/light-research traffic, not production financial workloads.

## Versioning note

`1.0.0` is the **product release version** — it describes this repository's
release maturity, not the analytical methodology. It is deliberately
distinct from:

| Concept | Value | What it means |
|---|---|---|
| Product release version | `1.0.0` | This repository/deployment's release |
| Risk score version | `v2_energy` | The production scoring methodology |
| Energy component version | `energy_component_v2.1` | The production energy-transition sub-model |
| Scenario method | `empirical_bootstrap_v1` | The production forward-scenario method |
| Data/web schema version | existing contract versions (`schema_version` in `gold/web/manifest.json`) | The publication bundle's own contract |

Bumping the product release version never implies a change to any
analytical method version, and vice versa.
