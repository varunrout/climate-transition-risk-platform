"""Curated Power BI publication tables.

The BI layer is downstream of silver/gold analytics. It reshapes already
computed outputs for reporting, but does not recompute risk scoring,
regime detection, or model evaluation logic in DAX.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pandas as pd

from climate_risk.config.loader import load_countries
from climate_risk.scenarios.engine import run_country_scenario
from climate_risk.scoring.risk_score import EFFECTIVE_WEIGHTS, NOMINAL_WEIGHTS
from climate_risk.scoring.risk_score_v2_energy import (
    COMPONENT_VERSION,
    EFFECTIVE_WEIGHTS_V2,
    SCORE_VERSION,
    WEIGHTS_VERSION,
)
from climate_risk.storage import LakeStorage, read_json, read_parquet, write_parquet
from climate_risk.transforms.silver import latest_silver_energy_panel, latest_silver_panel

BI_VERSION = "bi_semantic_v1"
BI_PREFIX = "bi"
PRODUCTION_SCENARIO_METHOD = "empirical_bootstrap_v1"
DEFAULT_SCENARIO_TARGET_YEAR = 2030
ACTIVE_SCORE_VERSION = SCORE_VERSION


@dataclass(frozen=True)
class BiArtifacts:
    country_overview: pd.DataFrame
    country_timeseries: pd.DataFrame
    risk_components: pd.DataFrame
    scenario_quantiles: pd.DataFrame
    backtest_metrics: pd.DataFrame
    energy_indicators: pd.DataFrame
    regime_diagnostics: pd.DataFrame
    run_metadata: pd.DataFrame

    def as_dict(self) -> dict[str, pd.DataFrame]:
        return {
            "country_overview": self.country_overview,
            "country_timeseries": self.country_timeseries,
            "risk_components": self.risk_components,
            "scenario_quantiles": self.scenario_quantiles,
            "backtest_metrics": self.backtest_metrics,
            "energy_indicators": self.energy_indicators,
            "regime_diagnostics": self.regime_diagnostics,
            "run_metadata": self.run_metadata,
        }


def build_bi_artifacts(
    lake: LakeStorage, *, scenario_target_year: int = DEFAULT_SCENARIO_TARGET_YEAR
) -> BiArtifacts:
    dim_country = read_parquet(lake.silver, "dim_country/data.parquet")
    transition, transition_path = _required_latest(
        latest_silver_panel(lake), "fact_country_year_transition"
    )
    energy, energy_path = _required_latest(
        latest_silver_energy_panel(lake), "fact_country_year_energy"
    )
    risk_v1 = read_parquet(lake.gold, "country_transition_risk.parquet")
    risk_v2 = read_parquet(lake.gold, "country_transition_risk_v2.parquet")
    energy_features = read_parquet(lake.gold, "energy_transition_features.parquet")
    backtest_country_origin = read_parquet(lake.gold, "backtest_country_origin.parquet")
    backtest_summary = read_parquet(lake.gold, "backtest_summary.parquet")
    regime_profiles = _read_optional_parquet(lake, "research/m7/regime_profiles.parquet")
    latest_run = _read_optional_json(lake, "latest_successful_run.json")
    manifest = _manifest_for_latest_run(lake, latest_run)

    countries = sorted(load_countries().keys())
    return BiArtifacts(
        country_overview=build_country_overview(
            dim_country, transition, risk_v1, risk_v2, energy_features, latest_run, manifest
        ),
        country_timeseries=build_country_timeseries(dim_country, transition, energy),
        risk_components=build_risk_components(risk_v1, risk_v2),
        scenario_quantiles=build_scenario_quantiles(
            dim_country,
            transition,
            countries=countries,
            target_year=scenario_target_year,
        ),
        backtest_metrics=build_backtest_metrics(backtest_country_origin, backtest_summary),
        energy_indicators=build_energy_indicators(dim_country, energy, energy_features),
        regime_diagnostics=build_regime_diagnostics(dim_country, regime_profiles),
        run_metadata=build_run_metadata(latest_run, manifest, transition_path, energy_path),
    )


def write_bi_artifacts(lake: LakeStorage, artifacts: BiArtifacts) -> None:
    for name, frame in artifacts.as_dict().items():
        write_parquet(lake.gold, f"{BI_PREFIX}/{name}.parquet", frame)


def build_country_overview(
    dim_country: pd.DataFrame,
    transition: pd.DataFrame,
    risk_v1: pd.DataFrame,
    risk_v2: pd.DataFrame,
    energy_features: pd.DataFrame,
    latest_run: dict[str, Any],
    manifest: dict[str, Any],
) -> pd.DataFrame:
    latest_transition = _latest_by_country(
        transition,
        [
            "country_iso3",
            "year",
            "carbon_intensity_gdp",
            "co2_per_capita",
            "energy_intensity_gdp",
            "is_core_complete",
            "missing_feature_count",
            "snapshot_set_id",
        ],
    ).rename(
        columns={"year": "latest_transition_year", "snapshot_set_id": "transition_snapshot_id"}
    )
    overview = (
        dim_country.merge(risk_v2, on="country_iso3", how="inner")
        .merge(
            risk_v1[["country_iso3", "score_total", "rank"]].rename(
                columns={"score_total": "score_total_v1", "rank": "rank_v1"}
            ),
            on="country_iso3",
            how="left",
        )
        .merge(latest_transition, on="country_iso3", how="left")
        .merge(
            energy_features[
                [
                    "country_iso3",
                    "latest_year",
                    "coal_share_elec",
                    "fossil_share_elec",
                    "low_carbon_share_elec",
                    "renewables_share_elec",
                    "transition_velocity",
                    "stalled_transition_residual_pp",
                ]
            ].rename(columns={"latest_year": "latest_energy_year"}),
            on="country_iso3",
            how="left",
        )
    )
    overview["active_score_version"] = ACTIVE_SCORE_VERSION
    overview["is_active_score"] = True
    overview["score_delta_v2_minus_v1"] = overview["score_total"] - overview["score_total_v1"]
    overview["rank_delta_v2_minus_v1"] = overview["rank"] - overview["rank_v1"]
    overview["risk_segment"] = overview["rank_band"].map(_risk_segment)
    overview["latest_successful_run_id"] = latest_run.get("run_id")
    overview["latest_successful_run_completed_at"] = latest_run.get("completed_at")
    overview["publish_status"] = manifest.get("publish_status", latest_run.get("status"))
    overview["bi_version"] = BI_VERSION
    return overview.sort_values("rank").reset_index(drop=True)


def build_country_timeseries(
    dim_country: pd.DataFrame, transition: pd.DataFrame, energy: pd.DataFrame
) -> pd.DataFrame:
    frame = transition.merge(
        energy, on=["country_iso3", "year"], how="left", suffixes=("", "_energy")
    )
    frame = frame.merge(_country_labels(dim_country), on="country_iso3", how="left")
    frame["bi_version"] = BI_VERSION
    return frame.sort_values(["country_iso3", "year"]).reset_index(drop=True)


def build_risk_components(risk_v1: pd.DataFrame, risk_v2: pd.DataFrame) -> pd.DataFrame:
    rows = []
    component_columns = {
        "pace": "score_pace",
        "coupling": "score_coupling",
        "volatility": "score_volatility",
        "forward_downside": "score_forward_downside",
        "energy": "score_energy",
    }
    for score_version, frame, weights in (
        ("v1", risk_v1, EFFECTIVE_WEIGHTS),
        (ACTIVE_SCORE_VERSION, risk_v2, EFFECTIVE_WEIGHTS_V2),
    ):
        for row in frame.to_dict(orient="records"):
            for component, column in component_columns.items():
                if column not in row or pd.isna(row[column]):
                    continue
                rows.append(
                    {
                        "country_iso3": row["country_iso3"],
                        "score_version": score_version,
                        "component_name": component,
                        "component_score": float(row[column]),
                        "nominal_weight": NOMINAL_WEIGHTS[component],
                        "effective_weight": weights.get(component),
                        "is_active_score": score_version == ACTIVE_SCORE_VERSION,
                        "component_version": row.get("component_version"),
                        "weights_version": row.get("weights_version"),
                        "bi_version": BI_VERSION,
                    }
                )
    return pd.DataFrame(rows).sort_values(["country_iso3", "score_version", "component_name"])


def build_scenario_quantiles(
    dim_country: pd.DataFrame,
    transition: pd.DataFrame,
    *,
    countries: list[str],
    target_year: int,
    n_simulations: int = 10_000,
    random_seed: int = 42,
) -> pd.DataFrame:
    rows = []
    labels = _country_labels(dim_country)
    for country_iso3 in countries:
        scenario = run_country_scenario(
            transition,
            country_iso3=country_iso3,
            target_year=target_year,
            n_simulations=n_simulations,
            random_seed=random_seed,
        )
        if scenario is None:
            continue
        rows.append(
            {
                "country_iso3": country_iso3,
                "origin_year": scenario.bootstrap.origin_year,
                "target_year": target_year,
                "scenario_horizon_years": target_year - scenario.bootstrap.origin_year,
                "scenario_method": PRODUCTION_SCENARIO_METHOD,
                "scenario_status": "production",
                "forecast_p05": scenario.bootstrap.p05,
                "forecast_p50": scenario.bootstrap.p50,
                "forecast_p95": scenario.bootstrap.p95,
                "deterministic_baseline": scenario.deterministic.forecast_value,
                "prob_below_origin_value": scenario.bootstrap.prob_below_baseline,
                "simulation_count": scenario.bootstrap.simulation_count,
                "random_seed": scenario.bootstrap.random_seed,
                "experimental_variant": False,
                "bi_version": BI_VERSION,
            }
        )
    return pd.DataFrame(rows).merge(labels, on="country_iso3", how="left")


def build_backtest_metrics(country_origin: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    detail = country_origin.copy()
    detail["metric_grain"] = "country_origin"
    detail["nominal_coverage_90"] = 0.90
    detail["calibration_gap_90"] = (detail["covered_90"].astype(float) - 0.90).abs()
    summary_rows = summary.copy()
    summary_rows["metric_grain"] = "summary"
    summary_rows["nominal_coverage_90"] = 0.90
    summary_rows["calibration_gap_90"] = (summary_rows["coverage_90"] - 0.90).abs()
    for column in detail.columns.difference(summary_rows.columns):
        summary_rows[column] = pd.NA
    for column in summary_rows.columns.difference(detail.columns):
        detail[column] = pd.NA
    combined = pd.concat([detail[summary_rows.columns], summary_rows], ignore_index=True)
    combined["production_model_variant"] = "empirical_bootstrap"
    combined["bi_version"] = BI_VERSION
    return combined


def build_energy_indicators(
    dim_country: pd.DataFrame, energy: pd.DataFrame, energy_features: pd.DataFrame
) -> pd.DataFrame:
    frame = energy.merge(_country_labels(dim_country), on="country_iso3", how="left")
    latest = energy_features.add_prefix("latest_feature_").rename(
        columns={"latest_feature_country_iso3": "country_iso3"}
    )
    frame = frame.merge(latest, on="country_iso3", how="left")
    frame["bi_version"] = BI_VERSION
    return frame.sort_values(["country_iso3", "year"]).reset_index(drop=True)


def build_regime_diagnostics(
    dim_country: pd.DataFrame, regime_profiles: pd.DataFrame
) -> pd.DataFrame:
    if regime_profiles.empty:
        return pd.DataFrame(
            columns=[
                "country_iso3",
                "series_name",
                "as_of_year",
                "diagnostic_status",
                "used_in_production_score",
                "used_in_production_scenario",
                "bi_version",
            ]
        )
    frame = regime_profiles.merge(_country_labels(dim_country), on="country_iso3", how="left")
    frame["diagnostic_status"] = "diagnostic_only_not_production_forecast_selector"
    frame["used_in_production_score"] = False
    frame["used_in_production_scenario"] = False
    frame["bi_version"] = BI_VERSION
    return frame.sort_values(["country_iso3", "series_name", "as_of_year"]).reset_index(drop=True)


def build_run_metadata(
    latest_run: dict[str, Any],
    manifest: dict[str, Any],
    transition_path: str,
    energy_path: str,
) -> pd.DataFrame:
    source_snapshot_ids = manifest.get("source_snapshot_ids", {})
    row = {
        "run_id": latest_run.get("run_id") or manifest.get("run_id"),
        "started_at": manifest.get("started_at", latest_run.get("started_at")),
        "completed_at": manifest.get("completed_at", latest_run.get("completed_at")),
        "generated_at": manifest.get("generated_at"),
        "publish_status": manifest.get("publish_status", latest_run.get("status")),
        "active_score_version": manifest.get("score_version", ACTIVE_SCORE_VERSION),
        "component_version": manifest.get("component_version", COMPONENT_VERSION),
        "weights_version": manifest.get("weights_version", WEIGHTS_VERSION),
        "production_scenario_method": manifest.get("model_variant", PRODUCTION_SCENARIO_METHOD),
        "git_sha": manifest.get("git_sha") or latest_run.get("git_commit"),
        "image_ref": manifest.get("container_image_ref"),
        "image_digest": manifest.get("container_image_digest"),
        "config_hash": manifest.get("config_hash", latest_run.get("config_hash")),
        "azure_job_execution_id": manifest.get("azure_job_execution_id"),
        "transition_silver_path": transition_path,
        "energy_silver_path": energy_path,
        "transition_snapshot_id": latest_run.get("snapshot_set_id"),
        "owid_co2_snapshot_id": source_snapshot_ids.get("owid_co2"),
        "world_bank_wdi_snapshot_id": source_snapshot_ids.get("world_bank_wdi"),
        "owid_energy_snapshot_id": source_snapshot_ids.get("owid_energy"),
        "latest_model_eligible_year": manifest.get("latest_model_eligible_year"),
        "latest_model_eligible_year_completeness": manifest.get(
            "latest_model_eligible_year_completeness"
        ),
        "bi_version": BI_VERSION,
    }
    return pd.DataFrame([row])


def _latest_by_country(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return frame[columns].sort_values(["country_iso3", "year"]).groupby("country_iso3").tail(1)


def _country_labels(dim_country: pd.DataFrame) -> pd.DataFrame:
    return dim_country[["country_iso3", "country_name", "region", "income_group"]]


def _risk_segment(rank_band: object) -> str:
    if rank_band in {"high", "elevated"}:
        return "High transition risk"
    if rank_band in {"moderate"}:
        return "Medium transition risk"
    return "Lower transition risk"


def _required_latest(
    found: tuple[pd.DataFrame, str] | None, table_name: str
) -> tuple[pd.DataFrame, str]:
    if found is None:
        raise FileNotFoundError(f"no latest {table_name} silver table found")
    return found


def _read_optional_parquet(lake: LakeStorage, path: str) -> pd.DataFrame:
    return read_parquet(lake.gold, path) if lake.gold.exists(path) else pd.DataFrame()


def _read_optional_json(lake: LakeStorage, path: str) -> dict[str, Any]:
    return cast(dict[str, Any], read_json(lake.gold, path)) if lake.gold.exists(path) else {}


def _manifest_for_latest_run(lake: LakeStorage, latest_run: dict[str, Any]) -> dict[str, Any]:
    run_id = latest_run.get("run_id")
    if not run_id:
        return {}
    path = f"manifests/{run_id}.json"
    return cast(dict[str, Any], read_json(lake.gold, path)) if lake.gold.exists(path) else {}
