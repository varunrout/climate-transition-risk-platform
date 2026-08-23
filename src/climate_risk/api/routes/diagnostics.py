from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from climate_risk.api.app import get_bundle
from climate_risk.api.models import RegimeDiagnostic
from climate_risk.api.repository import Bundle, normalize_iso3

router = APIRouter()


@router.get(
    "/diagnostics/regimes/{iso3}",
    response_model=list[RegimeDiagnostic],
    responses={404: {"description": "Unknown ISO3 code"}},
    summary="Structural-break / regime diagnostics (M7, research only)",
    description="RESEARCH/INTERPRETATION ONLY. Every entry carries production_use=false and "
    "status='research_diagnostic' -- these diagnostics never select the production forecast.",
)
def get_regime_diagnostics(
    iso3: str, bundle: Bundle = Depends(get_bundle)
) -> list[RegimeDiagnostic]:
    iso3 = normalize_iso3(iso3)
    if not bundle.country_exists(iso3):
        raise HTTPException(status_code=404, detail=f"Unknown country ISO3 code: {iso3!r}")

    rows = [r for r in bundle.regime_diagnostics if r["country_iso3"] == iso3]
    return [
        RegimeDiagnostic(
            country_iso3=r["country_iso3"],
            series_name=r["series_name"],
            as_of_year=r["as_of_year"],
            current_regime_label=r["current_regime_label"],
            regime_direction=r["regime_direction"],
            regime_confidence=r["regime_confidence"],
            break_count=r["break_count"],
            strongest_break_year=r["strongest_break_year"],
            strongest_break_strength=r["strongest_break_strength"],
            pre_break_slope=r["pre_break_slope"],
            post_break_slope=r["post_break_slope"],
            slope_delta=r["slope_delta"],
            break_method=r["break_method"],
            break_version=r["break_version"],
            diagnostic_status=r["diagnostic_status"],
            production_use=False,
            status="research_diagnostic",
        )
        for r in rows
    ]
