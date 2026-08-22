"""Typed configuration domain models.

These mirror the config-registry contracts in the specification
(config/sources.yaml, config/countries.yaml) so that malformed config
fails fast at load time rather than deep inside a pipeline stage.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SourceTier(StrEnum):
    CORE = "core"
    OPTIONAL = "optional"


class LicenceReviewStatus(StrEnum):
    APPROVED = "approved"
    PENDING_VERIFICATION = "pending_verification"
    REJECTED = "rejected"


class SourceConfig(BaseModel):
    """One entry in config/sources.yaml — mirrors 06_data_sources_and_licensing.md."""

    model_config = ConfigDict(frozen=True)

    key: str
    owner: str
    tier: SourceTier
    access: str
    refresh_check: str
    licence: str | None = None
    licence_review_status: LicenceReviewStatus = LicenceReviewStatus.APPROVED
    attribution_required: bool = False
    adapter: str
    enabled: bool = True
    url: str


class CountryConfig(BaseModel):
    """One entry in config/countries.yaml — controlled ISO-3 mapping, not fuzzy-matched."""

    model_config = ConfigDict(frozen=True)

    country_iso3: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    country_name: str
    g20_flag: bool = False
    region: str
    income_group: str | None = None
    # Name variants seen across sources (OWID, World Bank) that must map to this ISO-3.
    source_name_aliases: list[str] = Field(default_factory=list)
