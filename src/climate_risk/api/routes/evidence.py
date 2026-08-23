from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from climate_risk.api.app import get_bundle
from climate_risk.api.models import BacktestRecord
from climate_risk.api.repository import Bundle, normalize_iso3

router = APIRouter()

MAX_LIMIT = 500


@router.get(
    "/backtests",
    response_model=list[BacktestRecord],
    summary="Rolling-origin model evidence",
    description="Production model evidence: MAE/RMSE/interval coverage by model variant, with "
    "optional per-country/origin-year detail. Historical undercoverage is not filtered out.",
)
def get_backtests(
    bundle: Bundle = Depends(get_bundle),
    model_variant: str | None = Query(default=None),
    country: str | None = Query(default=None, description="ISO3 filter, case-insensitive."),
    origin_year: int | None = Query(default=None),
    limit: int = Query(default=MAX_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[BacktestRecord]:
    rows = bundle.backtest_metrics
    if model_variant is not None:
        rows = [r for r in rows if r["model_variant"] == model_variant]
    if country is not None:
        iso3 = normalize_iso3(country)
        rows = [r for r in rows if r["country_iso3"] == iso3]
    if origin_year is not None:
        rows = [r for r in rows if r["origin_year"] == origin_year]
    rows = rows[offset : offset + limit]
    return [
        BacktestRecord(
            model_variant=r["model_variant"],
            production_model_variant=r["production_model_variant"],
            metric_grain=r["metric_grain"],
            country_iso3=r["country_iso3"],
            origin_year=r["origin_year"],
            target_year=r["target_year"],
            horizon_years=r["horizon_years"],
            actual=r["actual"],
            forecast_p50=r["forecast_p50"],
            forecast_p05=r["forecast_p05"],
            forecast_p95=r["forecast_p95"],
            absolute_error=r["absolute_error"],
            covered_90=r["covered_90"],
            interval_width_90=r["interval_width_90"],
            n_splits=r["n_splits"],
            mae=r["mae"],
            rmse=r["rmse"],
            coverage_90=r["coverage_90"],
            nominal_coverage_90=r["nominal_coverage_90"],
            calibration_gap_90=r["calibration_gap_90"],
        )
        for r in rows
    ]
