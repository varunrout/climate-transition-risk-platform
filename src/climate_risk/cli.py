"""climate-risk CLI entrypoint.

Milestone status (see README.md for the authoritative table): `ingest` (M1),
`build-silver` (M2), `backtest` (M4), `score` (M5) and `publish` are
implemented. `features`/`model` are library functions
(climate_risk.features.decoupling, climate_risk.scenarios.engine) not yet
wired as standalone CLI commands. `run` chains every implemented stage.

Storage is backend-neutral (climate_risk.storage.LakeStorage) so the same
commands run unchanged against a local `data/lake/` checkout or four
`abfss://` ADLS Gen2 filesystems -- see ADR 0003 for the bug this replaced
and ADR 0004 for the storage design.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

import pandas as pd
import structlog
import typer

from climate_risk.config.loader import load_countries, load_source_registry
from climate_risk.contracts.models import QualitySeverity
from climate_risk.contracts.run import PipelineRun
from climate_risk.observability.logging import configure_logging, get_logger
from climate_risk.storage import (
    LakeStorage,
    read_json,
    read_parquet,
    write_json,
    write_parquet,
)
from climate_risk.storage.runtime import (
    StorageRuntimeError,
    is_azure_container_apps_job,
    prepare_lake_from_env,
    verify_durable_success,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def main(
    ctx: typer.Context,
    json_logs: bool = typer.Option(True, help="Emit structured JSON logs instead of console."),
) -> None:
    configure_logging(json_output=json_logs)
    ctx.obj = get_logger()


@app.command()
def validate_config() -> None:
    """Load and validate config/sources.yaml and config/countries.yaml."""
    log: structlog.stdlib.BoundLogger = get_logger(stage="validate-config")
    sources = load_source_registry()
    countries = load_countries()
    log.info(
        "config validated",
        source_count=len(sources),
        enabled_sources=sorted(k for k, v in sources.items() if v.enabled),
        country_count=len(countries),
    )
    typer.echo(f"{len(sources)} sources, {len(countries)} countries — OK")


@app.command()
def ingest(
    source: list[str] | None = typer.Option(  # noqa: B008 - typer requires call-in-default
        None, help="Source key(s) to ingest (default: all enabled core sources)."
    ),
) -> None:
    """Fetch, validate and snapshot configured sources into raw/ and bronze/."""
    from climate_risk.ingestion.base import SourceAdapter
    from climate_risk.ingestion.owid import OwidCo2Adapter
    from climate_risk.ingestion.owid_energy import OwidEnergyAdapter
    from climate_risk.ingestion.pipeline import run_ingest
    from climate_risk.ingestion.world_bank import WorldBankAdapter

    log = get_logger(stage="ingest")
    lake = prepare_lake_from_env(log, ensure_zones=True)

    registry = load_source_registry()
    adapters: dict[str, SourceAdapter] = {
        "owid_co2": OwidCo2Adapter(),
        "world_bank_wdi": WorldBankAdapter(),
        "owid_energy": OwidEnergyAdapter(),
    }
    selected = source or [k for k, v in registry.items() if v.enabled and k in adapters]

    run = PipelineRun.start()
    log = log.bind(run_id=run.run_id)
    exit_code = 0
    for key in selected:
        if key not in adapters:
            log.warning("no local adapter implemented for source, skipping", source=key)
            continue
        source_cfg = registry[key]
        if source_cfg.licence_review_status.value != "approved":
            log.warning(
                "source not approved for production use, skipping",
                source=key,
                licence_review_status=source_cfg.licence_review_status.value,
            )
            continue
        try:
            manifest = run_ingest(adapters[key], lake=lake, run_id=run.run_id)
            log.info(
                "ingest complete",
                source=key,
                status=manifest.status.value,
                row_count=manifest.row_count,
            )
        except Exception as exc:  # noqa: BLE001 - top-level CLI boundary
            log.error("ingest failed", source=key, error=str(exc))
            exit_code = 1

    if exit_code:
        raise typer.Exit(code=exit_code)


@app.command()
def build_silver() -> None:
    """Build dim_country + fact_country_year_transition from the latest bronze snapshots."""
    from climate_risk.transforms.silver import (
        build_dim_country,
        build_fact_country_year_energy,
        build_silver_panel,
        latest_complete_common_year,
    )
    from climate_risk.transforms.writer import (
        write_dim_country,
        write_fact_country_year_energy,
        write_fact_country_year_transition,
    )

    log = get_logger(stage="build-silver")
    lake = prepare_lake_from_env(log, ensure_zones=True)

    panel, snapshot_set_id, report = build_silver_panel(lake)
    if report.has_fatal:
        for event in report.by_severity(QualitySeverity.FATAL):
            log.error("silver build blocked", rule_id=event.rule_id, message=event.message)
        raise typer.Exit(code=1)

    for event in report.events:
        log.warning("quality event", rule_id=event.rule_id, message=event.message)

    write_dim_country(build_dim_country(), lake=lake)
    write_fact_country_year_transition(panel, snapshot_set_id=snapshot_set_id, lake=lake)

    # Raw energy-mix table (M6) is independent of the core transition panel --
    # its absence must never block the panel that M0-M5 already depend on.
    try:
        energy_frame, energy_snapshot_id, energy_report = build_fact_country_year_energy(lake)
        if energy_report.has_fatal:
            for event in energy_report.by_severity(QualitySeverity.FATAL):
                log.error(
                    "energy silver table blocked, skipping",
                    rule_id=event.rule_id,
                    message=event.message,
                )
        else:
            for event in energy_report.events:
                log.warning("energy quality event", rule_id=event.rule_id, message=event.message)
            write_fact_country_year_energy(
                energy_frame, snapshot_set_id=energy_snapshot_id, lake=lake
            )
            log.info(
                "energy silver table built",
                row_count=len(energy_frame),
                snapshot_set_id=energy_snapshot_id,
            )
    except FileNotFoundError:
        log.warning("no owid_energy bronze snapshot found, skipping energy silver table")

    countries = set(load_countries().keys())
    eligible_year = latest_complete_common_year(panel, countries=countries)
    log.info(
        "silver panel built",
        row_count=len(panel),
        snapshot_set_id=snapshot_set_id,
        latest_model_eligible_year=eligible_year,
    )
    typer.echo(
        f"{len(panel)} rows, snapshot_set_id={snapshot_set_id}, "
        f"latest model-eligible year={eligible_year}"
    )


@app.command()
def features() -> None:
    """Not yet implemented (M3)."""
    _not_implemented("features", milestone="M3")


@app.command()
def model() -> None:
    """Not yet implemented (M3)."""
    _not_implemented("model", milestone="M3")


def _latest_silver_panel(lake: LakeStorage) -> tuple[pd.DataFrame, str] | None:
    from climate_risk.transforms.silver import latest_silver_panel

    return latest_silver_panel(lake)


def _latest_silver_energy_panel(lake: LakeStorage) -> tuple[pd.DataFrame, str] | None:
    from climate_risk.transforms.silver import latest_silver_energy_panel

    return latest_silver_energy_panel(lake)


@app.command()
def energy_features(
    trailing_window_years: int = typer.Option(
        5, help="Trailing window (years) for trend/momentum/build-out-rate features."
    ),
) -> None:
    """Compute diagnostic energy-transition features (M6) and write
    gold/energy_transition_features.parquet.

    Reads the raw fact_country_year_energy silver table only -- this
    artifact is explicitly NOT consumed by `score` yet (see
    docs/m6_source_feasibility.md's risk-score gating section).
    """
    from climate_risk.features.energy_transition import compute_energy_features_for_panel

    log = get_logger(stage="energy-features")
    lake = prepare_lake_from_env(log)

    found = _latest_silver_energy_panel(lake)
    if found is None:
        typer.echo(
            "no fact_country_year_energy silver table found; run `climate-risk ingest` "
            "and `climate-risk build-silver` first",
            err=True,
        )
        raise typer.Exit(code=1)
    energy_panel, _ = found

    features = compute_energy_features_for_panel(
        energy_panel, trailing_window_years=trailing_window_years
    )
    if features.empty:
        typer.echo("no country had enough energy history for features", err=True)
        raise typer.Exit(code=1)

    write_parquet(lake.gold, "energy_transition_features.parquet", features)
    log.info(
        "energy features computed",
        countries=len(features),
        trailing_window_years=trailing_window_years,
    )
    typer.echo(features.to_string(index=False))


@app.command()
def m6_evaluate(
    n_permutations: int = typer.Option(
        200, help="Permutations for the incremental-information null-distribution test."
    ),
    random_seed: int = typer.Option(42, help="Seed for permutation test and weight perturbation."),
) -> None:
    """M6 phase 2: energy-feature evaluation and score-integration gating.

    Research-only -- reads the existing v1 score + silver tables, writes
    every evidence artifact under gold/research/m6/, and makes one
    evidence-based ACCEPT / DIAGNOSTICS_ONLY / REVISE decision
    (gold/research/m6/decision.json). Never overwrites
    gold/country_transition_risk.parquet (v1) or gold/manifests/ (publish
    evidence); score v2 is written to a separate path.
    """
    from scipy import stats

    from climate_risk.features.decoupling import compute_decoupling_for_panel
    from climate_risk.research import m6_coverage, m6_incremental, m6_redundancy, m6_stability
    from climate_risk.research.m6_panel import build_evaluation_panel, feature_catalog
    from climate_risk.scenarios.engine import run_country_scenario
    from climate_risk.scoring.energy_component import compute_energy_component
    from climate_risk.scoring.risk_score import compute_raw_metrics, compute_risk_scores
    from climate_risk.scoring.risk_score_v2_energy import (
        compute_risk_scores_v2,
        weight_perturbation_analysis_v2,
    )

    log = get_logger(stage="m6-evaluate")
    lake = prepare_lake_from_env(log)

    transition_found = _latest_silver_panel(lake)
    energy_found = _latest_silver_energy_panel(lake)
    if transition_found is None or energy_found is None:
        typer.echo(
            "requires both fact_country_year_transition and fact_country_year_energy; "
            "run `climate-risk ingest` and `climate-risk build-silver` first",
            err=True,
        )
        raise typer.Exit(code=1)
    transition_panel, _ = transition_found
    energy_panel, _ = energy_found
    countries = sorted(load_countries().keys())

    # ---------------------------------------------------------------
    # 1. Freeze the current v1 baseline (never overwritten by anything below)
    # ---------------------------------------------------------------
    if not lake.gold.exists("country_transition_risk.parquet"):
        typer.echo(
            "no gold/country_transition_risk.parquet found; run `climate-risk score` first",
            err=True,
        )
        raise typer.Exit(code=1)
    v1_scores = read_parquet(lake.gold, "country_transition_risk.parquet")
    v1_rank_stability = (
        read_json(lake.gold, "rank_stability.json")
        if lake.gold.exists("rank_stability.json")
        else None
    )
    manifest_paths = lake.gold.glob("manifests/*.json")
    latest_manifest = (
        read_json(lake.gold, max(manifest_paths, key=lake.gold.modified_at))
        if manifest_paths
        else None
    )
    from climate_risk.scoring.risk_score import EFFECTIVE_WEIGHTS, NOMINAL_WEIGHTS, WEIGHT_COVERAGE

    baseline_frozen = {
        "score_version": "v1",
        "nominal_weights": NOMINAL_WEIGHTS,
        "effective_weights": EFFECTIVE_WEIGHTS,
        "weight_coverage": WEIGHT_COVERAGE,
        "country_scores": v1_scores.to_dict(orient="records"),
        "rank_stability": v1_rank_stability,
        "latest_publish_manifest": latest_manifest,
    }
    write_json(lake.gold, "research/m6/baseline_v1_frozen.json", baseline_frozen)
    log.info("v1 baseline frozen", countries=len(v1_scores))

    # ---------------------------------------------------------------
    # 2. Evaluation panel + feature catalog
    # ---------------------------------------------------------------
    evaluation_panel = build_evaluation_panel(lake)
    write_parquet(lake.gold, "research/m6/evaluation_panel.parquet", evaluation_panel)
    catalog_frame = pd.DataFrame([f.model_dump() for f in feature_catalog()])
    write_parquet(lake.gold, "research/m6/feature_catalog.parquet", catalog_frame)

    # ---------------------------------------------------------------
    # 3. Coverage
    # ---------------------------------------------------------------
    coverage_report = m6_coverage.run_coverage_analysis(evaluation_panel, energy_panel)
    write_parquet(lake.gold, "research/m6/coverage_report.parquet", coverage_report)
    compact_component_columns = [
        "low_carbon_share_elec",
        "clean_power_momentum_pp_per_year",
        "fossil_persistence_mean_pct",
    ]
    compact_coverage = coverage_report[
        coverage_report["feature_name"].isin(compact_component_columns)
    ]
    coverage_gate_passed = len(compact_coverage) == len(compact_component_columns) and bool(
        compact_coverage["meets_minimum_thresholds"].all()
    )
    log.info("coverage analysis complete", coverage_gate_passed=coverage_gate_passed)

    # ---------------------------------------------------------------
    # 4. Stability
    # ---------------------------------------------------------------
    yoy = m6_stability.yoy_volatility(energy_panel, column="low_carbon_share_elec")
    lookback = m6_stability.lookback_window_sensitivity(energy_panel)
    lookback_pairwise = lookback["pairwise_comparisons"]
    assert isinstance(lookback_pairwise, pd.DataFrame)
    revision = m6_stability.one_year_revision_sensitivity(energy_panel)
    stability_summary = m6_stability.summarise_stability(lookback, revision)
    write_parquet(lake.gold, "research/m6/stability_yoy_volatility.parquet", yoy)
    write_parquet(
        lake.gold,
        "research/m6/stability_lookback_sensitivity.parquet",
        lookback_pairwise,
    )
    write_parquet(lake.gold, "research/m6/stability_revision_sensitivity.parquet", revision)
    write_json(lake.gold, "research/m6/stability_analysis.json", stability_summary)
    log.info("stability analysis complete", **stability_summary)

    # ---------------------------------------------------------------
    # 5. Redundancy / collinearity
    # ---------------------------------------------------------------
    correlations = m6_redundancy.correlation_matrices(evaluation_panel)
    write_parquet(
        lake.gold,
        "research/m6/correlation_matrix_pearson.parquet",
        correlations["pearson"].reset_index(),
    )
    write_parquet(
        lake.gold,
        "research/m6/correlation_matrix_spearman.parquet",
        correlations["spearman"].reset_index(),
    )
    vif = m6_redundancy.variance_inflation_factors(evaluation_panel)
    write_parquet(lake.gold, "research/m6/variance_inflation_factors.parquet", vif)
    groups = m6_redundancy.redundancy_groups(evaluation_panel)
    write_parquet(lake.gold, "research/m6/redundancy_groups.parquet", groups)
    log.info("redundancy analysis complete", n_groups=int(groups["redundancy_group"].nunique()))

    # ---------------------------------------------------------------
    # 6+7. Incremental information + temporal backtest (same rolling-origin
    # evaluation answers both -- see m6_incremental module docstring)
    # ---------------------------------------------------------------
    incremental_dataset = m6_incremental.build_incremental_dataset(
        transition_panel, energy_panel, countries=countries
    )
    write_parquet(lake.gold, "research/m6/temporal_backtest.parquet", incremental_dataset)
    incremental_result = m6_incremental.leave_one_country_out_comparison(incremental_dataset)
    permutation_result = m6_incremental.permutation_test(
        incremental_dataset, n_permutations=n_permutations, random_seed=random_seed
    )
    ablation = m6_incremental.ablation_comparison(incremental_dataset)
    write_parquet(lake.gold, "research/m6/incremental_ablation.parquet", ablation)
    write_json(
        lake.gold,
        "research/m6/incremental_information.json",
        {"leave_one_country_out": incremental_result, "permutation_test": permutation_result},
    )
    log.info(
        "incremental information test complete",
        **{k: v for k, v in incremental_result.items() if k != "feature_columns"},
    )

    # ---------------------------------------------------------------
    # 8+9. Energy component + score v2 experiment
    # ---------------------------------------------------------------
    energy_component = compute_energy_component(evaluation_panel)
    write_parquet(lake.gold, "research/m6/energy_component.parquet", energy_component)

    decoupling = {
        r.country_iso3: r
        for r in compute_decoupling_for_panel(transition_panel, min_observations=5)
    }
    scenarios = {}
    for country_iso3 in countries:
        result = run_country_scenario(
            transition_panel, country_iso3=country_iso3, target_year=2050, random_seed=random_seed
        )
        if result is not None:
            scenarios[country_iso3] = result
    raw_metrics = compute_raw_metrics(
        transition_panel, decoupling=decoupling, scenarios=scenarios, countries=countries
    )

    v1_rescored = compute_risk_scores(
        raw_metrics
    )  # identical to gold/country_transition_risk.parquet, for a same-run comparison
    v2_scores = compute_risk_scores_v2(raw_metrics, energy_component=energy_component)
    write_parquet(lake.gold, "research/m6/score_v2_energy_experimental.parquet", v2_scores)

    comparison = (
        v1_rescored.set_index("country_iso3")[["score_total", "rank"]]
        .rename(columns={"score_total": "score_total_v1", "rank": "rank_v1"})
        .join(
            v2_scores.set_index("country_iso3")[
                ["score_total", "rank", "score_energy", "energy_confidence", "weight_coverage"]
            ].rename(columns={"score_total": "score_total_v2", "rank": "rank_v2"}),
            how="outer",
        )
    )
    comparison["score_delta"] = comparison["score_total_v2"] - comparison["score_total_v1"]
    comparison["rank_delta"] = comparison["rank_v1"] - comparison["rank_v2"]
    comparison = comparison.reset_index().sort_values("score_delta", key=abs, ascending=False)
    write_parquet(lake.gold, "research/m6/score_v1_vs_v2.parquet", comparison)
    common_countries = comparison.dropna(subset=["rank_v1", "rank_v2"])
    v1_vs_v2_spearman = (
        float(stats.spearmanr(common_countries["rank_v1"], common_countries["rank_v2"]).correlation)
        if len(common_countries) >= 3
        else None
    )
    log.info("score v1 vs v2 comparison complete", v1_vs_v2_spearman=v1_vs_v2_spearman)

    # ---------------------------------------------------------------
    # 10. Weight robustness (v2)
    # ---------------------------------------------------------------
    weight_sensitivity = {
        f"perturbation_{int(frac * 100)}pct": weight_perturbation_analysis_v2(
            raw_metrics,
            energy_component=energy_component,
            perturbation_fraction=frac,
            random_seed=random_seed,
        )
        for frac in (0.1, 0.2, 0.3)
    }
    write_json(lake.gold, "research/m6/weight_sensitivity.json", weight_sensitivity)
    log.info(
        "weight robustness (v2) complete",
        **{k: v["mean_spearman_correlation"] for k, v in weight_sensitivity.items()},
    )

    # ---------------------------------------------------------------
    # 14. Decision gate -- mechanical, evidence-based, fixed criteria
    # ---------------------------------------------------------------
    reasons: list[str] = []
    if not coverage_gate_passed:
        decision = "REVISE"
        reasons.append(
            "compact energy component's source features fail the pre-declared coverage thresholds"
        )
    elif "error" in incremental_result:
        decision = "DIAGNOSTICS_ONLY"
        reasons.append(f"incremental-information test could not run: {incremental_result['error']}")
    else:
        p_value_raw = permutation_result.get("permutation_p_value")
        p_value: float | None = float(p_value_raw) if isinstance(p_value_raw, int | float) else None
        mae_improvement = incremental_result.get("mae_improvement", 0.0)
        assert isinstance(mae_improvement, float)
        robust_30pct = float(weight_sensitivity["perturbation_30pct"]["min_spearman_correlation"])
        if p_value is not None and p_value <= 0.10 and mae_improvement > 0 and robust_30pct >= 0.85:
            decision = "ACCEPT"
            reasons.append(
                f"leave-one-country-out MAE improved by {mae_improvement:.4f} "
                f"(permutation p={p_value:.3f}), weight-robust at +/-30% (min Spearman rho={robust_30pct:.3f})"
            )
        else:
            decision = "DIAGNOSTICS_ONLY"
            reasons.append(
                f"incremental-information evidence insufficient: mae_improvement={mae_improvement:.4f}, "
                f"permutation_p_value={p_value}, weight-robustness min Spearman rho at +/-30%={robust_30pct}"
            )

    decision_record = {
        "decision": decision,
        "reasons": reasons,
        "coverage_gate_passed": coverage_gate_passed,
        "incremental_information": incremental_result,
        "permutation_test": permutation_result,
        "weight_robustness_30pct": weight_sensitivity["perturbation_30pct"],
        "v1_vs_v2_spearman_rank_correlation": v1_vs_v2_spearman,
        "score_v2_promoted_to_production": False,
    }
    write_json(lake.gold, "research/m6/decision.json", decision_record)
    log.info("M6 decision", decision=decision, reasons=reasons)
    typer.echo(f"M6 decision: {decision}")
    for reason in reasons:
        typer.echo(f"  - {reason}")


@app.command()
def m6_harden(
    n_permutations: int = typer.Option(
        2000, help="Strengthened permutation count (M6 phase 3, section 1)."
    ),
    random_seed: int = typer.Option(42, help="Deterministic seed for every stochastic step."),
) -> None:
    """M6 phase 3, sections 1-4: strengthen the M6 phase-2 evidence before
    freezing a production energy-component specification.

    Research-only, like `m6-evaluate` -- writes every artifact under
    gold/research/m6/phase3/, never touches gold/country_transition_risk.parquet
    (v1) or cli.score()/cli.publish(). See ADR 0009 for the resulting
    freeze decision.
    """
    from climate_risk.features.decoupling import compute_decoupling_for_panel
    from climate_risk.research.m6_panel import build_evaluation_panel
    from climate_risk.research.m6_phase3_harden import run_hardening
    from climate_risk.scenarios.engine import run_country_scenario
    from climate_risk.scoring.risk_score import compute_raw_metrics

    log = get_logger(stage="m6-harden")
    lake = prepare_lake_from_env(log)

    transition_found = _latest_silver_panel(lake)
    energy_found = _latest_silver_energy_panel(lake)
    if transition_found is None or energy_found is None:
        typer.echo(
            "requires both fact_country_year_transition and fact_country_year_energy; "
            "run `climate-risk ingest` and `climate-risk build-silver` first",
            err=True,
        )
        raise typer.Exit(code=1)
    transition_panel, _ = transition_found
    energy_panel, _ = energy_found
    countries = sorted(load_countries().keys())

    evaluation_panel = build_evaluation_panel(lake)
    decoupling = {
        r.country_iso3: r
        for r in compute_decoupling_for_panel(transition_panel, min_observations=5)
    }
    scenarios = {}
    for country_iso3 in countries:
        result = run_country_scenario(
            transition_panel, country_iso3=country_iso3, target_year=2050, random_seed=random_seed
        )
        if result is not None:
            scenarios[country_iso3] = result
    raw_metrics = compute_raw_metrics(
        transition_panel, decoupling=decoupling, scenarios=scenarios, countries=countries
    )

    log.info("hardening started", n_permutations=n_permutations, random_seed=random_seed)
    hardening_result = run_hardening(
        transition_panel,
        energy_panel,
        evaluation_panel,
        raw_metrics,
        countries=countries,
        n_permutations=n_permutations,
        random_seed=random_seed,
    )

    prefix = "research/m6/phase3"
    write_parquet(
        lake.gold, f"{prefix}/incremental_dataset.parquet", hardening_result["incremental_dataset"]
    )
    write_json(
        lake.gold,
        f"{prefix}/permutation_result_incumbent.json",
        hardening_result["permutation_result_incumbent"],
    )
    write_parquet(
        lake.gold,
        f"{prefix}/formulation_incremental.parquet",
        hardening_result["formulation_incremental"],
    )
    write_json(
        lake.gold,
        f"{prefix}/formulation_permutations.json",
        hardening_result["formulation_permutations"],
    )
    for name, frame in hardening_result["formulation_lookback"].items():
        write_parquet(lake.gold, f"{prefix}/formulation_lookback_{name}.parquet", frame)
    write_json(
        lake.gold,
        f"{prefix}/formulation_weight_sensitivity.json",
        hardening_result["formulation_weight_sensitivity"],
    )
    write_json(
        lake.gold,
        f"{prefix}/formulation_missing_data.json",
        hardening_result["formulation_missing_data"],
    )
    for name, frame in hardening_result["formulation_collinearity"].items():
        write_parquet(lake.gold, f"{prefix}/formulation_collinearity_{name}.parquet", frame)
    write_parquet(
        lake.gold,
        f"{prefix}/full_lookback_pairwise.parquet",
        hardening_result["full_lookback_pairwise"],
    )
    write_parquet(
        lake.gold,
        f"{prefix}/lookback_instability_by_feature.parquet",
        hardening_result["lookback_instability_by_feature"],
    )
    write_parquet(
        lake.gold,
        f"{prefix}/lookback_country_deltas.parquet",
        hardening_result["lookback_country_deltas"],
    )
    write_json(
        lake.gold, f"{prefix}/theil_sen_comparison.json", hardening_result["theil_sen_comparison"]
    )
    for name, frame in hardening_result["formulation_by_origin"].items():
        write_parquet(lake.gold, f"{prefix}/formulation_by_origin_{name}.parquet", frame)
    write_json(
        lake.gold,
        f"{prefix}/formulation_leave_one_origin_out.json",
        hardening_result["formulation_leave_one_origin_out"],
    )

    permutation = hardening_result["permutation_result_incumbent"]
    log.info(
        "hardening complete",
        permutation_p_value=permutation.get("permutation_p_value"),
        n_permutations_run=permutation.get("n_permutations_run"),
        observed_improvement_percentile_within_null=permutation.get(
            "observed_improvement_percentile_within_null"
        ),
    )
    typer.echo(
        f"strengthened permutation test ({permutation.get('n_permutations_run')} perms): "
        f"p={permutation.get('permutation_p_value')}, "
        f"percentile_within_null={permutation.get('observed_improvement_percentile_within_null')}"
    )
    typer.echo(hardening_result["formulation_incremental"].to_string(index=False))


@app.command()
def m7_phase1(
    bootstrap_iterations: int = typer.Option(
        100, help="Residual-bootstrap iterations for breakpoint stability diagnostics."
    ),
    random_seed: int = typer.Option(42, help="Deterministic seed for stochastic diagnostics."),
    max_bootstrap_profiles: int = typer.Option(
        12, help="Maximum country-series profiles included in Phase 1 bootstrap stability."
    ),
) -> None:
    """M7 phase 1: leakage-safe structural-break / regime diagnostics.

    Research-only -- writes evidence under gold/research/m7/ and does not
    alter score artifacts, publish manifests, Azure infrastructure, or the
    scheduled production pipeline.
    """
    from climate_risk.research.m7_regimes import run_phase1_diagnostics

    log = get_logger(stage="m7-phase1")
    lake = prepare_lake_from_env(log)

    transition_found = _latest_silver_panel(lake)
    energy_found = _latest_silver_energy_panel(lake)
    if transition_found is None or energy_found is None:
        typer.echo(
            "requires both fact_country_year_transition and fact_country_year_energy; "
            "run `climate-risk ingest` and `climate-risk build-silver` first",
            err=True,
        )
        raise typer.Exit(code=1)
    transition_panel, transition_path = transition_found
    energy_panel, energy_path = energy_found

    artifacts = run_phase1_diagnostics(
        transition_panel,
        energy_panel,
        random_seed=random_seed,
        bootstrap_iterations=bootstrap_iterations,
        max_bootstrap_profiles=max_bootstrap_profiles,
    )
    candidate_series = artifacts["candidate_series"]
    feature_catalog = artifacts["feature_catalog"]
    country_breaks = artifacts["country_breaks"]
    method_comparison = artifacts["method_comparison"]
    method_agreement = artifacts["method_agreement"]
    regime_profiles = artifacts["regime_profiles"]
    break_stability = artifacts["break_stability"]
    case_studies = artifacts["country_case_studies"]
    decision_raw = artifacts["decision"]
    assert isinstance(candidate_series, pd.DataFrame)
    assert isinstance(feature_catalog, pd.DataFrame)
    assert isinstance(country_breaks, pd.DataFrame)
    assert isinstance(method_comparison, pd.DataFrame)
    assert isinstance(method_agreement, pd.DataFrame)
    assert isinstance(regime_profiles, pd.DataFrame)
    assert isinstance(break_stability, pd.DataFrame)
    assert isinstance(case_studies, dict)
    assert isinstance(decision_raw, dict)

    prefix = "research/m7"
    write_parquet(lake.gold, f"{prefix}/candidate_series.parquet", candidate_series)
    write_parquet(lake.gold, f"{prefix}/feature_catalog.parquet", feature_catalog)
    write_parquet(lake.gold, f"{prefix}/country_breaks.parquet", country_breaks)
    write_parquet(lake.gold, f"{prefix}/method_comparison.parquet", method_comparison)
    write_parquet(lake.gold, f"{prefix}/method_agreement.parquet", method_agreement)
    write_parquet(lake.gold, f"{prefix}/regime_profiles.parquet", regime_profiles)
    write_parquet(lake.gold, f"{prefix}/break_stability.parquet", break_stability)
    write_json(lake.gold, f"{prefix}/country_case_studies.json", case_studies)

    decision = dict(decision_raw)
    decision["inputs"] = {
        "transition_silver_path": transition_path,
        "energy_silver_path": energy_path,
        "transition_rows": len(transition_panel),
        "energy_rows": len(energy_panel),
    }
    write_json(lake.gold, f"{prefix}/decision.json", decision)

    log.info(
        "M7 phase 1 diagnostics complete",
        candidate_series=int(country_breaks["series_name"].nunique()) if len(country_breaks) else 0,
        break_rows=len(country_breaks),
        bootstrap_iterations=bootstrap_iterations,
        random_seed=random_seed,
        max_bootstrap_profiles=max_bootstrap_profiles,
    )
    typer.echo("M7 phase 1 artifacts written under gold/research/m7/")


@app.command()
def m7_phase2() -> None:
    """M7 phase 2: historical-origin regime recomputation and stability.

    Research-only -- writes evidence under gold/research/m7/phase2/ and does
    not alter score artifacts, publish manifests, Azure infrastructure, or the
    scheduled production pipeline.
    """
    from climate_risk.research.m7_regimes import run_phase2_diagnostics

    log = get_logger(stage="m7-phase2")
    lake = prepare_lake_from_env(log)

    transition_found = _latest_silver_panel(lake)
    energy_found = _latest_silver_energy_panel(lake)
    if transition_found is None or energy_found is None:
        typer.echo(
            "requires both fact_country_year_transition and fact_country_year_energy; "
            "run `climate-risk ingest` and `climate-risk build-silver` first",
            err=True,
        )
        raise typer.Exit(code=1)
    transition_panel, transition_path = transition_found
    energy_panel, energy_path = energy_found

    artifacts = run_phase2_diagnostics(transition_panel, energy_panel)
    origin_results = artifacts["origin_regime_results"]
    origin_agreement = artifacts["origin_method_agreement"]
    temporal_stability = artifacts["temporal_stability"]
    decision_raw = artifacts["decision"]
    assert isinstance(origin_results, pd.DataFrame)
    assert isinstance(origin_agreement, pd.DataFrame)
    assert isinstance(temporal_stability, pd.DataFrame)
    assert isinstance(decision_raw, dict)

    prefix = "research/m7/phase2"
    write_parquet(lake.gold, f"{prefix}/origin_regime_results.parquet", origin_results)
    write_parquet(lake.gold, f"{prefix}/origin_method_agreement.parquet", origin_agreement)
    write_parquet(lake.gold, f"{prefix}/temporal_stability.parquet", temporal_stability)
    decision = dict(decision_raw)
    decision["inputs"] = {
        "transition_silver_path": transition_path,
        "energy_silver_path": energy_path,
        "transition_rows": len(transition_panel),
        "energy_rows": len(energy_panel),
    }
    write_json(lake.gold, f"{prefix}/decision.json", decision)

    log.info(
        "M7 phase 2 diagnostics complete",
        origin_rows=len(origin_results),
        stability_rows=len(temporal_stability),
    )
    typer.echo("M7 phase 2 artifacts written under gold/research/m7/phase2/")


@app.command()
def m7_phase3(
    n_simulations: int = typer.Option(
        5_000, help="Simulation count for each experimental bootstrap scenario."
    ),
    random_seed: int = typer.Option(42, help="Deterministic seed for stochastic scenarios."),
) -> None:
    """M7 phase 3: regime-aware scenario experiments and decision gate.

    Research-only -- writes evidence under gold/research/m7/phase3/ and does
    not alter production scenarios, scores, publish manifests, Azure resources,
    or the scheduled pipeline.
    """
    from climate_risk.research.m7_scenarios import run_phase3_experiment

    log = get_logger(stage="m7-phase3")
    lake = prepare_lake_from_env(log)

    found = _latest_silver_panel(lake)
    if found is None:
        typer.echo("no silver panel found; run `climate-risk build-silver` first", err=True)
        raise typer.Exit(code=1)
    panel, transition_path = found
    countries = sorted(load_countries().keys())

    artifacts = run_phase3_experiment(
        panel,
        countries=countries,
        n_simulations=n_simulations,
        random_seed=random_seed,
    )
    scenario_results = artifacts["scenario_method_results"]
    origin_metrics = artifacts["origin_metrics"]
    country_metrics = artifacts["country_metrics"]
    calibration_metrics = artifacts["calibration_metrics"]
    break_sensitivity = artifacts["break_sensitivity"]
    recency_vs_regime = artifacts["recency_vs_regime"]
    conditional_policy = artifacts["conditional_policy"]
    performance_uncertainty = artifacts["performance_uncertainty"]
    case_studies = artifacts["case_studies"]
    decision_raw = artifacts["decision"]
    assert isinstance(scenario_results, pd.DataFrame)
    assert isinstance(origin_metrics, pd.DataFrame)
    assert isinstance(country_metrics, pd.DataFrame)
    assert isinstance(calibration_metrics, pd.DataFrame)
    assert isinstance(break_sensitivity, pd.DataFrame)
    assert isinstance(recency_vs_regime, pd.DataFrame)
    assert isinstance(conditional_policy, pd.DataFrame)
    assert isinstance(performance_uncertainty, pd.DataFrame)
    assert isinstance(case_studies, dict)
    assert isinstance(decision_raw, dict)

    prefix = "research/m7/phase3"
    write_parquet(lake.gold, f"{prefix}/scenario_method_results.parquet", scenario_results)
    write_parquet(lake.gold, f"{prefix}/origin_metrics.parquet", origin_metrics)
    write_parquet(lake.gold, f"{prefix}/country_metrics.parquet", country_metrics)
    write_parquet(lake.gold, f"{prefix}/calibration_metrics.parquet", calibration_metrics)
    write_parquet(lake.gold, f"{prefix}/break_sensitivity.parquet", break_sensitivity)
    write_parquet(lake.gold, f"{prefix}/recency_vs_regime.parquet", recency_vs_regime)
    write_parquet(lake.gold, f"{prefix}/conditional_policy.parquet", conditional_policy)
    write_parquet(lake.gold, f"{prefix}/performance_uncertainty.parquet", performance_uncertainty)
    write_json(lake.gold, f"{prefix}/case_studies.json", case_studies)
    decision = dict(decision_raw)
    decision["inputs"] = {
        "transition_silver_path": transition_path,
        "transition_rows": len(panel),
        "n_simulations": n_simulations,
        "random_seed": random_seed,
    }
    write_json(lake.gold, f"{prefix}/decision.json", decision)

    log.info(
        "M7 phase 3 scenario experiment complete",
        scenario_rows=len(scenario_results),
        decision=decision.get("decision"),
    )
    typer.echo(f"M7 phase 3 decision: {decision.get('decision')}")


@app.command()
def m7_phase4(
    n_simulations: int = typer.Option(
        5_000, help="Simulation count for each hardened recency-bootstrap candidate."
    ),
    random_seed: int = typer.Option(42, help="Deterministic seed for stochastic scenarios."),
) -> None:
    """M7 phase 4: recency scenario hardening and final M7 decision.

    Research-only unless the decision artifact later justifies an explicit
    production promotion. This command writes under gold/research/m7/phase4/
    and does not alter scores, production scenarios, Azure resources, or the
    scheduled pipeline.
    """
    from climate_risk.research.m7_phase4 import run_phase4_hardening

    log = get_logger(stage="m7-phase4")
    lake = prepare_lake_from_env(log)

    found = _latest_silver_panel(lake)
    if found is None:
        typer.echo("no silver panel found; run climate-risk build-silver first", err=True)
        raise typer.Exit(code=1)
    panel, transition_path = found
    countries = sorted(load_countries().keys())

    artifacts = run_phase4_hardening(
        panel,
        countries=countries,
        n_simulations=n_simulations,
        random_seed=random_seed,
    )
    candidate_comparison = artifacts["candidate_comparison"]
    country_results = artifacts["country_results"]
    origin_results = artifacts["origin_results"]
    calibration_analysis = artifacts["calibration_analysis"]
    recency_robustness = artifacts["recency_robustness"]
    nested_weight_selection = artifacts["nested_weight_selection"]
    performance_uncertainty = artifacts["performance_uncertainty"]
    decision_raw = artifacts["decision"]
    assert isinstance(candidate_comparison, pd.DataFrame)
    assert isinstance(country_results, pd.DataFrame)
    assert isinstance(origin_results, pd.DataFrame)
    assert isinstance(calibration_analysis, pd.DataFrame)
    assert isinstance(recency_robustness, pd.DataFrame)
    assert isinstance(nested_weight_selection, pd.DataFrame)
    assert isinstance(performance_uncertainty, pd.DataFrame)
    assert isinstance(decision_raw, dict)

    prefix = "research/m7/phase4"
    write_parquet(lake.gold, f"{prefix}/candidate_comparison.parquet", candidate_comparison)
    write_parquet(lake.gold, f"{prefix}/country_results.parquet", country_results)
    write_parquet(lake.gold, f"{prefix}/origin_results.parquet", origin_results)
    write_parquet(lake.gold, f"{prefix}/calibration_analysis.parquet", calibration_analysis)
    write_parquet(lake.gold, f"{prefix}/recency_robustness.parquet", recency_robustness)
    write_parquet(lake.gold, f"{prefix}/nested_weight_selection.parquet", nested_weight_selection)
    write_parquet(lake.gold, f"{prefix}/performance_uncertainty.parquet", performance_uncertainty)
    decision = dict(decision_raw)
    decision["inputs"] = {
        "transition_silver_path": transition_path,
        "transition_rows": len(panel),
        "n_simulations": n_simulations,
        "random_seed": random_seed,
    }
    write_json(lake.gold, f"{prefix}/decision.json", decision)

    log.info(
        "M7 phase 4 recency hardening complete",
        decision=decision.get("production_decision"),
        m7_status=decision.get("m7_status"),
    )
    typer.echo(f"M7 phase 4 decision: {decision.get('production_decision')}")


@app.command()
def build_bi(
    scenario_target_year: int = typer.Option(
        2030, help="Target year for the production scenario explorer table."
    ),
) -> None:
    """Build Power BI-ready semantic tables under gold/bi/.

    This is a downstream publication layer. It reshapes validated silver/gold
    analytics for BI consumption and does not recompute risk scoring or alter
    the production publish pointer.
    """
    from climate_risk.bi.publish import build_bi_artifacts, write_bi_artifacts

    log = get_logger(stage="build-bi")
    lake = prepare_lake_from_env(log)
    artifacts = build_bi_artifacts(lake, scenario_target_year=scenario_target_year)
    write_bi_artifacts(lake, artifacts)
    log.info(
        "Power BI semantic tables written",
        table_count=len(artifacts.as_dict()),
        scenario_target_year=scenario_target_year,
    )
    typer.echo("Power BI semantic tables written under gold/bi/")


@app.command()
def build_web() -> None:
    """Build the browser-safe web publication bundle under gold/web/.

    Downstream of `build-bi`: selects, serializes, and validates the
    already-published gold/bi/*.parquet tables into JSON. Does not
    recompute risk scoring, scenario generation, or diagnostics. A failure
    here does not invalidate an already-published core analytical run --
    see ADR 0016.
    """
    from climate_risk.bi.web_publish import build_manifest, build_web_bundle, write_web_bundle

    log = get_logger(stage="build-web")
    lake = prepare_lake_from_env(log)
    bundle = build_web_bundle(lake)
    manifest = build_manifest(bundle)
    write_web_bundle(lake, bundle, manifest)
    log.info(
        "web publication bundle written",
        file_count=len(bundle) + 1,
        country_count=manifest["country_count"],
        web_bundle_hash=manifest["web_bundle_hash"],
    )
    typer.echo("Web publication bundle written under gold/web/")


@app.command()
def publish_product(
    scenario_target_year: int = typer.Option(
        2030, help="Target year for the production scenario explorer table."
    ),
) -> None:
    """Build and verify the downstream product publication (gold/bi + gold/web).

    Requires an existing core analytical publication (`climate-risk publish`,
    or `climate-risk run`, must have already succeeded). Reshapes that
    already-published release for BI/web consumption; never recomputes
    scoring, scenarios, or diagnostics. A failure here never rolls back or
    corrupts the core analytical release -- see ADR 0016/0019 -- but it
    exits non-zero so operational monitoring sees the product layer is
    stale, and it re-reads every written file back from storage to verify
    completeness and integrity before declaring success.
    """
    from climate_risk.publishing.product import ProductPublicationError
    from climate_risk.publishing.product import publish_product as _publish

    log = get_logger(stage="publish-product")
    lake = prepare_lake_from_env(log)
    try:
        result = _publish(lake, log, scenario_target_year=scenario_target_year)
    except ProductPublicationError as exc:
        log.error("product publication failed", error=str(exc))
        typer.echo(f"product publication failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    log.info(
        "product publication complete",
        run_id=result.run_id,
        bi_table_count=result.bi_table_count,
        web_file_count=result.web_file_count,
        web_bundle_hash=result.web_bundle_hash,
    )
    typer.echo(
        f"product publication complete for run_id={result.run_id} "
        f"({result.bi_table_count} BI tables, {result.web_file_count} web files)"
    )


@app.command()
def export_bi_preview(
    output_path: str = typer.Option(
        "docs/powerbi/portfolio_preview.html",
        help="HTML output path for the static BI portfolio preview.",
    ),
) -> None:
    """Export a static portfolio preview from gold/bi tables.

    This is not a PBIX. It is a lightweight, reproducible report artifact for
    environments where Power BI Desktop is unavailable.
    """
    from pathlib import Path

    from climate_risk.bi.static_report import render_portfolio_preview

    log = get_logger(stage="export-bi-preview")
    lake = prepare_lake_from_env(log)
    written = render_portfolio_preview(lake, Path(output_path))
    log.info("Power BI portfolio preview written", output_path=str(written))
    typer.echo(f"Power BI portfolio preview written to {written}")


@app.command()
def backtest(
    n_simulations: int = typer.Option(10_000, help="Bootstrap simulation count per split."),
    random_seed: int = typer.Option(42, help="Seed for reproducibility."),
) -> None:
    """Run rolling-origin backtests over the latest silver panel and write gold/backtest_summary.parquet."""
    from climate_risk.backtesting.rolling_origin import run_backtest, summarise_metrics

    log = get_logger(stage="backtest")
    lake = prepare_lake_from_env(log)

    found = _latest_silver_panel(lake)
    if found is None:
        typer.echo("no silver panel found; run `climate-risk build-silver` first", err=True)
        raise typer.Exit(code=1)
    panel, _ = found

    origins = [(2010, 2015), (2012, 2017), (2014, 2019), (2015, 2020), (2016, 2021), (2017, 2022)]
    results = run_backtest(
        panel, origins=origins, n_simulations=n_simulations, random_seed=random_seed
    )
    if results.empty:
        typer.echo(
            "no eligible backtest splits (insufficient history or missing targets)", err=True
        )
        raise typer.Exit(code=1)

    summary = summarise_metrics(results)
    write_parquet(lake.gold, "backtest_country_origin.parquet", results)
    write_parquet(lake.gold, "backtest_summary.parquet", summary)

    log.info("backtest complete", n_splits=len(results), origins=origins)
    typer.echo(summary.to_string(index=False))


@app.command()
def score(
    target_year: int = typer.Option(
        2050, help="Scenario horizon for the forward-downside component."
    ),
    random_seed: int = typer.Option(
        42, help="Seed for scenario simulation and weight perturbation."
    ),
) -> None:
    """Compute transition risk scores: v1 (4 of 5 components, permanent
    comparison baseline, gold/country_transition_risk.parquet) and v2
    (energy-augmented, the default production score since ADR 0009,
    gold/country_transition_risk_v2.parquet). v1's own computation and
    output are completely unaffected by v2's presence or absence.
    """
    from climate_risk.features.decoupling import compute_decoupling_for_panel
    from climate_risk.features.energy_transition import compute_energy_features_for_panel
    from climate_risk.scenarios.engine import run_country_scenario
    from climate_risk.scoring.energy_component import compute_energy_component
    from climate_risk.scoring.risk_score import (
        WEIGHT_COVERAGE,
        compute_raw_metrics,
        compute_risk_scores,
        weight_perturbation_analysis,
    )
    from climate_risk.scoring.risk_score_v2_energy import (
        SCORE_VERSION as V2_SCORE_VERSION,
    )
    from climate_risk.scoring.risk_score_v2_energy import (
        compute_risk_scores_v2,
        weight_perturbation_analysis_v2,
    )

    log = get_logger(stage="score")
    lake = prepare_lake_from_env(log)

    found = _latest_silver_panel(lake)
    if found is None:
        typer.echo("no silver panel found; run `climate-risk build-silver` first", err=True)
        raise typer.Exit(code=1)
    panel, _ = found
    countries = sorted(panel["country_iso3"].unique())

    decoupling = {
        r.country_iso3: r for r in compute_decoupling_for_panel(panel, min_observations=5)
    }
    scenarios = {}
    for country_iso3 in countries:
        result = run_country_scenario(
            panel, country_iso3=country_iso3, target_year=target_year, random_seed=random_seed
        )
        if result is not None:
            scenarios[country_iso3] = result

    raw_metrics = compute_raw_metrics(
        panel, decoupling=decoupling, scenarios=scenarios, countries=countries
    )
    scores_v1 = compute_risk_scores(raw_metrics)
    if scores_v1.empty:
        typer.echo("no country scored (insufficient data for every candidate)", err=True)
        raise typer.Exit(code=1)

    stability_v1 = weight_perturbation_analysis(
        raw_metrics, n_perturbations=200, random_seed=random_seed
    )
    write_parquet(lake.gold, "country_transition_risk.parquet", scores_v1)
    write_json(lake.gold, "rank_stability.json", stability_v1)
    log.info(
        "v1 score complete",
        countries_scored=len(scores_v1),
        countries_in_panel=len(countries),
        weight_coverage=WEIGHT_COVERAGE,
        **stability_v1,
    )

    # v2 (ADR 0009): best-effort on top of v1, which is already written and
    # unaffected either way. Requires the energy silver table + enough
    # history to compute the frozen 2-signal component; `publish` is what
    # actually enforces fail-closed production requirements (section 15),
    # not this command.
    energy_found = _latest_silver_energy_panel(lake)
    scores_v2 = None
    if energy_found is None:
        log.warning("no fact_country_year_energy silver table found; v2 score not computed")
    else:
        energy_panel, _ = energy_found
        energy_features = compute_energy_features_for_panel(energy_panel, trailing_window_years=5)
        if energy_features.empty:
            log.warning("no country had enough energy history; v2 score not computed")
        else:
            energy_component = compute_energy_component(energy_features)
            scores_v2 = compute_risk_scores_v2(raw_metrics, energy_component=energy_component)
            if scores_v2.empty:
                log.warning("v2 scoring produced no rows; v2 score not written")
                scores_v2 = None
            else:
                stability_v2 = weight_perturbation_analysis_v2(
                    raw_metrics,
                    energy_component=energy_component,
                    perturbation_fraction=0.3,
                    n_perturbations=200,
                    random_seed=random_seed,
                )
                write_parquet(lake.gold, "country_transition_risk_v2.parquet", scores_v2)
                write_json(lake.gold, "rank_stability_v2.json", stability_v2)
                log.info(
                    "v2 score complete",
                    score_version=V2_SCORE_VERSION,
                    countries_scored=len(scores_v2),
                    **stability_v2,
                )

    if scores_v2 is not None:
        typer.echo(f"=== v2 ({V2_SCORE_VERSION}, PRODUCTION) ===")
        typer.echo(scores_v2.to_string(index=False))
        typer.echo("\n=== v1 (comparison baseline) ===")
        typer.echo(scores_v1.to_string(index=False))
    else:
        typer.echo(scores_v1.to_string(index=False))
        typer.echo(f"\nweight_coverage={WEIGHT_COVERAGE:.2f} (v1 only -- v2 not computed, see log)")


@app.command()
def publish() -> str:
    """Fail-closed publish: promote the current gold outputs to latest_successful_run,
    or refuse and leave the previous release untouched (climate_risk.publishing.barrier).

    Requires: an accepted silver panel, backtest gold outputs, and BOTH v1
    and v2 score gold outputs to already exist (run `climate-risk run`
    first, or ingest/build-silver/backtest/score individually). v2 is
    required, not optional -- since ADR 0009, a run where the energy
    pipeline or v2 scoring failed must not publish at all (section 15's
    fail-closed requirement), not silently fall back to publishing v1 alone.
    Writes a full evidence manifest to gold/manifests/<run_id>.json in
    addition to the barrier's own pointer file.
    """
    from climate_risk.publishing.barrier import PublishBlockedError
    from climate_risk.publishing.barrier import publish as publish_barrier
    from climate_risk.scoring.risk_score import EFFECTIVE_WEIGHTS
    from climate_risk.scoring.risk_score_v2_energy import (
        COMPONENT_VERSION,
        EFFECTIVE_WEIGHTS_V2,
        WEIGHTS_VERSION,
    )
    from climate_risk.scoring.risk_score_v2_energy import SCORE_VERSION as V2_SCORE_VERSION
    from climate_risk.transforms.silver import latest_complete_common_year

    log = get_logger(stage="publish")
    lake = prepare_lake_from_env(log)
    run = PipelineRun.start()
    log = log.bind(run_id=run.run_id)

    def _fail(stage: str, message: str) -> None:
        run.fail(stage=stage, message=message)
        log.error("publish blocked", stage=stage, message=message)

    source_snapshots: dict[str, dict[str, str]] = {}
    # owid_energy is required here too (not just owid_co2/world_bank_wdi):
    # since ADR 0009, v2 is the required production score, so a failed or
    # missing energy ingestion must fail-close the whole publish, not just
    # silently degrade to a v1-only release.
    for source_name in ("owid_co2", "world_bank_wdi", "owid_energy"):
        manifest_paths = lake.raw.glob(f"source={source_name}/ingest_date=*/run_id=*/manifest.json")
        if not manifest_paths:
            _fail("ingest", f"no ingestion manifest found for source={source_name}")
            typer.echo(f"publish blocked: no ingestion manifest for {source_name}", err=True)
            raise typer.Exit(code=1)
        latest_manifest_path = max(manifest_paths, key=lake.raw.modified_at)
        latest_manifest = read_json(lake.raw, latest_manifest_path)
        assert isinstance(latest_manifest, dict)
        if latest_manifest["status"] != "ACCEPTED":
            _fail("ingest", f"latest {source_name} snapshot has status {latest_manifest['status']}")
            typer.echo(f"publish blocked: {source_name} snapshot not ACCEPTED", err=True)
            raise typer.Exit(code=1)
        source_snapshots[source_name] = {
            "sha256": latest_manifest["sha256"],
            "retrieved_at_utc": latest_manifest["retrieved_at_utc"],
        }

    found = _latest_silver_panel(lake)
    if found is None:
        _fail("build-silver", "no silver panel found")
        typer.echo("publish blocked: no silver panel found", err=True)
        raise typer.Exit(code=1)
    panel, latest_fact_path = found
    snapshot_set_id = latest_fact_path.split("/")[1].removeprefix("snapshot_set_id=")
    countries = set(load_countries().keys())

    eligible_year = latest_complete_common_year(panel, countries=countries)
    completeness = (
        float(panel[panel["year"] == eligible_year]["is_core_complete"].mean())
        if eligible_year is not None
        else 0.0
    )

    if not lake.gold.exists("backtest_summary.parquet"):
        _fail("backtest", "no gold/backtest_summary.parquet found")
        typer.echo("publish blocked: no backtest output found", err=True)
        raise typer.Exit(code=1)
    if not lake.gold.exists("country_transition_risk.parquet"):
        _fail("score", "no gold/country_transition_risk.parquet (v1) found")
        typer.echo("publish blocked: no v1 score output found", err=True)
        raise typer.Exit(code=1)
    if not lake.gold.exists("country_transition_risk_v2.parquet"):
        _fail(
            "score",
            "no gold/country_transition_risk_v2.parquet (v2, ADR 0009 production score) found",
        )
        typer.echo(
            "publish blocked: no v2 score output found -- energy ingestion, energy "
            "feature construction, or v2 scoring must have failed upstream; the "
            "previous successful release is left untouched",
            err=True,
        )
        raise typer.Exit(code=1)

    backtest_summary = read_parquet(lake.gold, "backtest_summary.parquet")
    scores_v1 = read_parquet(lake.gold, "country_transition_risk.parquet")
    scores_v2 = read_parquet(lake.gold, "country_transition_risk_v2.parquet")

    run.snapshot_set_id = snapshot_set_id
    run.feature_set_version = "decoupling_v1"
    run.model_version = "empirical_bootstrap_v1"
    config_source = json.dumps(
        {
            "weights_v1": dict(EFFECTIVE_WEIGHTS),
            "weights_v2": dict(EFFECTIVE_WEIGHTS_V2),
            "component_version": COMPONENT_VERSION,
            "sources": sorted(source_snapshots),
        },
        sort_keys=True,
    )
    run.config_hash = hashlib.sha256(config_source.encode()).hexdigest()[:16]
    run.succeed(release_id=snapshot_set_id)

    # Azure Container Apps Jobs injects CONTAINER_APP_JOB_EXECUTION_NAME into
    # every job execution's environment (the execution name, e.g.
    # "<job-name>-xxxxxxx"). None outside a deployed Container Apps Job --
    # documented here rather than fabricated if it's ever absent.
    azure_job_execution_id = os.environ.get("CONTAINER_APP_JOB_EXECUTION_NAME")

    manifest = {
        "run_id": run.run_id,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "git_sha": run.git_commit,
        # Image provenance: set by the Container Apps Job template
        # (CLIMATE_RISK_IMAGE_REF/CLIMATE_RISK_IMAGE_DIGEST env vars, see
        # infra/modules/container_apps). None outside a deployed container.
        "container_image_ref": os.environ.get("CLIMATE_RISK_IMAGE_REF"),
        "container_image_digest": os.environ.get("CLIMATE_RISK_IMAGE_DIGEST") or None,
        "source_snapshot_ids": {k: v["sha256"][:16] for k, v in source_snapshots.items()},
        "source_checksums": {k: v["sha256"] for k, v in source_snapshots.items()},
        "config_hash": run.config_hash,
        "random_seed": 42,
        "country_scope": sorted(countries),
        "quality_status": "ACCEPTED",
        "model_variant": run.model_version,
        "backtest_metrics": backtest_summary.to_dict(orient="records"),
        # Active production score since ADR 0009 -- v2, not v1. v1 is
        # preserved as a permanent, always-computed comparison artifact
        # (gold/country_transition_risk.parquet), never deleted or silently
        # superseded; this field is what a downstream consumer must read to
        # know which one is authoritative.
        "score_version": V2_SCORE_VERSION,
        "component_version": COMPONENT_VERSION,
        "weights_version": WEIGHTS_VERSION,
        "comparison_score_version": "v1",
        "v1_artifact": "country_transition_risk.parquet",
        "v2_artifact": "country_transition_risk_v2.parquet",
        "v1_countries_scored": len(scores_v1),
        "v2_countries_scored": len(scores_v2),
        "publish_status": "PUBLISHED",
        "latest_model_eligible_year": eligible_year,
        "latest_model_eligible_year_completeness": completeness,
        "azure_job_execution_id": azure_job_execution_id,
        "generated_at": run.completed_at.isoformat() if run.completed_at else None,
    }
    manifest_path = f"manifests/{run.run_id}.json"
    write_json(lake.gold, manifest_path, manifest)

    try:
        publish_barrier(
            run,
            gold=lake.gold,
            required_artifacts=[
                "backtest_summary.parquet",
                "country_transition_risk.parquet",
                "country_transition_risk_v2.parquet",
                manifest_path,
            ],
        )
    except PublishBlockedError as exc:
        typer.echo(f"publish blocked: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    log.info(
        "published",
        release_id=snapshot_set_id,
        active_score_version=V2_SCORE_VERSION,
        v1_countries=len(scores_v1),
        v2_countries=len(scores_v2),
        azure_job_execution_id=azure_job_execution_id,
    )
    typer.echo(
        f"published release_id={snapshot_set_id}, active_score_version={V2_SCORE_VERSION} "
        f"({len(scores_v2)} countries scored v2, {len(scores_v1)} v1 comparison)"
    )
    return run.run_id


@app.command()
def run() -> None:
    """Run every implemented stage in order: ingest, build-silver, backtest, score, publish."""
    log = get_logger(stage="run")
    try:
        ingest(source=None)
        build_silver()
        try:
            energy_features(trailing_window_years=5)
        except typer.Exit:
            # Diagnostic/exploratory artifact (M6) -- not required for publish, which
            # never reads gold/energy_transition_features.parquet or gates on it.
            log.warning("energy-features skipped (no energy silver table or insufficient history)")
        backtest(n_simulations=10_000, random_seed=42)
        score(target_year=2050, random_seed=42)
        published_run_id = publish()
        if is_azure_container_apps_job():
            verification = verify_durable_success(
                LakeStorage.from_env(), require_energy=True, expected_run_id=published_run_id
            )
            log.info("durable success verified", **verification)
    except StorageRuntimeError as exc:
        log.error("storage runtime invariant failed", error=str(exc))
        typer.echo(f"storage runtime invariant failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    # Downstream product publication (gold/bi + gold/web) runs after the core
    # release is durably confirmed. A failure here is reported clearly and
    # exits non-zero -- so scheduled-run monitoring sees the product layer
    # went stale -- but it never touches or re-runs the core stages above,
    # and the already-published core release is left exactly as it is.
    from climate_risk.publishing.product import ProductPublicationError
    from climate_risk.publishing.product import publish_product as _publish_product

    try:
        product_result = _publish_product(LakeStorage.from_env(), log)
        log.info(
            "product publication complete",
            run_id=product_result.run_id,
            web_bundle_hash=product_result.web_bundle_hash,
        )
    except ProductPublicationError as exc:
        log.error("product publication failed; core release remains valid", error=str(exc))
        typer.echo(f"product publication failed (core release unaffected): {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        "All implemented stages complete.",
        err=True,
    )


@app.command()
def api(
    host: str = typer.Option("127.0.0.1", help="Bind host."),
    port: int = typer.Option(8000, help="Bind port."),
    reload: bool = typer.Option(False, help="Auto-reload on source changes (development only)."),
) -> None:
    """Run the M10 read-only API (requires the `api` extra: `uv sync --extra api`).

    Serves already-published gold/web output; never recomputes analytics.
    Fails to start if the published bundle is missing or inconsistent.
    Docs at /docs, /redoc, /openapi.json once running.
    """
    try:
        import uvicorn
    except ImportError as exc:
        typer.echo(
            "The API requires the 'api' extra: run `uv sync --extra api`.",
            err=True,
        )
        raise typer.Exit(code=1) from exc

    uvicorn.run("climate_risk.api.app:app", host=host, port=port, reload=reload)


def _not_implemented(command: str, *, milestone: str) -> None:
    typer.echo(
        f"'{command}' is not implemented yet (tracked under {milestone}). "
        "Refusing to fabricate output.",
        err=True,
    )
    raise typer.Exit(code=2)


if __name__ == "__main__":
    sys.exit(app())
