from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from climate_risk.api.app import get_bundle
from climate_risk.api.models import RankingEntry, RankingResponse
from climate_risk.api.repository import Bundle

router = APIRouter()

MAX_LIMIT = 19  # dataset is exactly the 19 covered sovereigns; no need for a larger cap


@router.get(
    "/rankings",
    response_model=RankingResponse,
    summary="Sovereign risk ranking",
    description="Current ranking on the production (v2_energy) score.",
)
def get_rankings(
    bundle: Bundle = Depends(get_bundle),
    sort: Literal["risk_asc", "risk_desc"] = Query(default="risk_desc"),
    limit: int = Query(default=MAX_LIMIT, ge=1, le=MAX_LIMIT),
) -> RankingResponse:
    rows = sorted(
        bundle.country_overview,
        key=lambda r: r["score_total"],
        reverse=(sort == "risk_desc"),
    )[:limit]
    return RankingResponse(
        active_score_version=bundle.manifest.get("active_score_version") or "",
        total_count=len(bundle.country_overview),
        entries=[
            RankingEntry(
                rank=r["rank"],
                country_iso3=r["country_iso3"],
                country_name=r["country_name"],
                risk_score=r["score_total"],
                data_confidence_score=r["data_confidence_score"],
            )
            for r in rows
        ],
    )
