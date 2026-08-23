from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from climate_risk.api.app import API_VERSION, get_bundle
from climate_risk.api.models import ApiMetadata
from climate_risk.api.repository import Bundle
from climate_risk.bi.web_publish import WEB_SCHEMA_VERSION
from climate_risk.contracts.run import resolve_git_sha

router = APIRouter()


@router.get(
    "/meta",
    response_model=ApiMetadata,
    summary="API and published-data provenance",
    description=(
        "Identifies exactly which analytical run this API instance is serving: "
        "active score/component/scenario versions, source snapshots, and generation time. "
        "data_git_sha (the pipeline commit that produced the served data) and api_git_sha "
        "(this API application's own image commit) are distinct provenance concepts and "
        "commonly differ -- the data pipeline and this API are built and deployed "
        "independently."
    ),
)
def get_meta(bundle: Bundle = Depends(get_bundle)) -> ApiMetadata:
    m = bundle.manifest
    return ApiMetadata(
        api_version=API_VERSION,
        active_score_version=m.get("active_score_version") or "",
        component_version=m.get("active_component_version"),
        production_scenario_method=m.get("active_scenario_method"),
        model_eligible_year=m.get("model_eligible_year"),
        source_run_id=m.get("source_run_id"),
        data_git_sha=m.get("source_git_sha"),
        api_git_sha=resolve_git_sha(),
        api_image_digest=os.environ.get("CLIMATE_RISK_API_IMAGE_DIGEST") or None,
        source_snapshot_ids=m.get("source_snapshot_ids") or {},
        generated_at=m.get("generated_at") or "",
        data_schema_version=m.get("schema_version") or WEB_SCHEMA_VERSION,
        country_count=m.get("country_count") or len(bundle.country_overview),
    )
