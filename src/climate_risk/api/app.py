"""Climate Transition Risk Intelligence API -- read-only FastAPI serving layer.

Serves already-published `gold/web` analytical output. Never recomputes
risk scoring, scenario generation, backtesting, or diagnostics -- the
Python analytical pipeline (`climate_risk.bi`, `climate_risk.scoring`,
etc.) remains the sole source of truth. See docs/api/ for the full
architecture and security notes.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from climate_risk.api.repository import Bundle, StartupValidationError, load_bundle
from climate_risk.observability.logging import get_logger
from climate_risk.storage.runtime import prepare_lake_from_env

API_VERSION = "1.0.0"

DESCRIPTION = """
Read-only analytical serving API for the Climate Transition Risk
Intelligence platform: sovereign transition risk for the 19 non-EU G20
economies.

**Scope.** Country-level, annual-cadence analytics. Not real-time --
every response reflects the latest *published* analytical run; see
`GET /api/v1/meta` for its exact provenance (run ID, Git SHA, source
snapshots, generated_at).

**Production vs research semantics (non-negotiable).**
- Production risk score: `v2_energy` (energy-augmented). `v1` is kept
  permanently available for comparison, never silently dropped.
- Production forward-scenario method: `empirical_bootstrap_v1`.
  Recency-weighted and regime-aware scenario variants were researched
  (M7) but were **not promoted** -- they are never returned as if they
  were production.
- M7 structural-break/regime diagnostics are **research/interpretation
  only**. Every diagnostic response carries `production_use: false` and
  `status: "research_diagnostic"` -- they never select the production
  forecast.

**Limitations.** Historical 90% prediction-interval coverage for the
production scenario method has measured below the nominal 90% target
(see `GET /api/v1/backtests`) -- better point forecasts do not imply
calibrated uncertainty. Data confidence is reported separately from
risk and must never be read as a risk signal itself.

**Update cadence.** Weekly, tied to the upstream Azure production
pipeline's schedule. This API does not poll live external sources.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log = get_logger(stage="api-startup")
    started = time.monotonic()
    lake = prepare_lake_from_env(log)
    try:
        bundle = load_bundle(lake)
    except StartupValidationError:
        log.error("startup validation failed")
        raise
    app.state.bundle = bundle
    log.info(
        "bundle loaded",
        country_count=len(bundle.country_overview),
        source_run_id=bundle.manifest.get("source_run_id"),
        startup_seconds=round(time.monotonic() - started, 3),
    )
    yield


def get_bundle(request: Request) -> Bundle:
    return request.app.state.bundle  # type: ignore[no-any-return]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Climate Transition Risk Intelligence API",
        version=API_VERSION,
        description=DESCRIPTION,
        lifespan=lifespan,
    )

    # Public, unauthenticated, read-only GET API serving already-public
    # analytical output (no PII, no secrets -- see docs/api/security.md).
    # A permissive origin policy is a deliberate, documented choice for a
    # portfolio API, not an oversight; it does not allow credentialed
    # requests (no cookies/auth headers are ever used by this API).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
        log = get_logger(stage="api-request")
        started = time.monotonic()
        response = await call_next(request)
        log.info(
            "request handled",
            path=request.url.path,
            method=request.method,
            status_code=response.status_code,
            duration_ms=round((time.monotonic() - started) * 1000, 2),
        )
        return response

    @app.exception_handler(StartupValidationError)
    async def _startup_error_handler(request: Request, exc: StartupValidationError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    from climate_risk.api.routes import countries, diagnostics, evidence, meta, rankings

    app.include_router(meta.router, prefix="/api/v1", tags=["meta"])
    app.include_router(countries.router, prefix="/api/v1", tags=["countries"])
    app.include_router(rankings.router, prefix="/api/v1", tags=["rankings"])
    app.include_router(evidence.router, prefix="/api/v1", tags=["evidence"])
    app.include_router(diagnostics.router, prefix="/api/v1", tags=["diagnostics"])

    @app.get("/health", tags=["meta"], summary="Liveness check")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
