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
    lake = LakeStorage.from_env()
    lake.ensure_zones()

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
    lake = LakeStorage.from_env()
    lake.ensure_zones()

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
    fact_dirs = lake.silver.glob("fact_country_year_transition/snapshot_set_id=*/data.parquet")
    if not fact_dirs:
        return None
    latest_path = max(fact_dirs, key=lake.silver.modified_at)
    panel = read_parquet(lake.silver, latest_path)
    return panel, latest_path


def _latest_silver_energy_panel(lake: LakeStorage) -> tuple[pd.DataFrame, str] | None:
    fact_dirs = lake.silver.glob("fact_country_year_energy/snapshot_set_id=*/data.parquet")
    if not fact_dirs:
        return None
    latest_path = max(fact_dirs, key=lake.silver.modified_at)
    panel = read_parquet(lake.silver, latest_path)
    return panel, latest_path


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
    lake = LakeStorage.from_env()

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
def backtest(
    n_simulations: int = typer.Option(10_000, help="Bootstrap simulation count per split."),
    random_seed: int = typer.Option(42, help="Seed for reproducibility."),
) -> None:
    """Run rolling-origin backtests over the latest silver panel and write gold/backtest_summary.parquet."""
    from climate_risk.backtesting.rolling_origin import run_backtest, summarise_metrics

    log = get_logger(stage="backtest")
    lake = LakeStorage.from_env()

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
    """Compute transition risk scores (v1, 4 of 5 components) and write gold/country_transition_risk.parquet."""
    from climate_risk.features.decoupling import compute_decoupling_for_panel
    from climate_risk.scenarios.engine import run_country_scenario
    from climate_risk.scoring.risk_score import (
        WEIGHT_COVERAGE,
        compute_raw_metrics,
        compute_risk_scores,
        weight_perturbation_analysis,
    )

    log = get_logger(stage="score")
    lake = LakeStorage.from_env()

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
    scores = compute_risk_scores(raw_metrics)
    if scores.empty:
        typer.echo("no country scored (insufficient data for every candidate)", err=True)
        raise typer.Exit(code=1)

    stability = weight_perturbation_analysis(
        raw_metrics, n_perturbations=200, random_seed=random_seed
    )

    write_parquet(lake.gold, "country_transition_risk.parquet", scores)
    write_json(lake.gold, "rank_stability.json", stability)

    log.info(
        "score complete",
        countries_scored=len(scores),
        countries_in_panel=len(countries),
        weight_coverage=WEIGHT_COVERAGE,
        **stability,
    )
    typer.echo(scores.to_string(index=False))
    typer.echo(f"\nweight_coverage={WEIGHT_COVERAGE:.2f} (energy component not computed; see ADR)")
    typer.echo(f"rank stability: {stability}")


@app.command()
def publish() -> None:
    """Fail-closed publish: promote the current gold outputs to latest_successful_run,
    or refuse and leave the previous release untouched (climate_risk.publishing.barrier).

    Requires: an accepted silver panel, backtest gold outputs, and score gold
    outputs to already exist (run `climate-risk run` first, or ingest/build-silver/
    backtest/score individually). Writes a full evidence manifest to
    gold/manifests/<run_id>.json in addition to the barrier's own pointer file.
    """
    from climate_risk.publishing.barrier import PublishBlockedError
    from climate_risk.publishing.barrier import publish as publish_barrier
    from climate_risk.scoring.risk_score import EFFECTIVE_WEIGHTS
    from climate_risk.transforms.silver import latest_complete_common_year

    log = get_logger(stage="publish")
    lake = LakeStorage.from_env()
    run = PipelineRun.start()
    log = log.bind(run_id=run.run_id)

    def _fail(stage: str, message: str) -> None:
        run.fail(stage=stage, message=message)
        log.error("publish blocked", stage=stage, message=message)

    source_snapshots: dict[str, dict[str, str]] = {}
    for source_name in ("owid_co2", "world_bank_wdi"):
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
        _fail("score", "no gold/country_transition_risk.parquet found")
        typer.echo("publish blocked: no score output found", err=True)
        raise typer.Exit(code=1)

    backtest_summary = read_parquet(lake.gold, "backtest_summary.parquet")
    scores = read_parquet(lake.gold, "country_transition_risk.parquet")

    run.snapshot_set_id = snapshot_set_id
    run.feature_set_version = "decoupling_v1"
    run.model_version = "empirical_bootstrap_v1"
    config_source = json.dumps(
        {"weights": dict(EFFECTIVE_WEIGHTS), "sources": sorted(source_snapshots)},
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
        "score_version": "v1",
        "publish_status": "PUBLISHED",
        "latest_model_eligible_year": eligible_year,
        "latest_model_eligible_year_completeness": completeness,
        "azure_job_execution_id": azure_job_execution_id,
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
                manifest_path,
            ],
        )
    except PublishBlockedError as exc:
        typer.echo(f"publish blocked: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    log.info(
        "published",
        release_id=snapshot_set_id,
        countries=len(scores),
        azure_job_execution_id=azure_job_execution_id,
    )
    typer.echo(f"published release_id={snapshot_set_id} ({len(scores)} countries scored)")


@app.command()
def run() -> None:
    """Run every implemented stage in order: ingest, build-silver, backtest, score, publish."""
    ingest(source=None)
    build_silver()
    try:
        energy_features(trailing_window_years=5)
    except typer.Exit:
        # Diagnostic/exploratory artifact (M6) -- not required for publish, which
        # never reads gold/energy_transition_features.parquet or gates on it.
        get_logger(stage="run").warning(
            "energy-features skipped (no energy silver table or insufficient history)"
        )
    backtest(n_simulations=10_000, random_seed=42)
    score(target_year=2050, random_seed=42)
    publish()
    typer.echo(
        "All implemented stages complete.",
        err=True,
    )


def _not_implemented(command: str, *, milestone: str) -> None:
    typer.echo(
        f"'{command}' is not implemented yet (tracked under {milestone}). "
        "Refusing to fabricate output.",
        err=True,
    )
    raise typer.Exit(code=2)


if __name__ == "__main__":
    sys.exit(app())
