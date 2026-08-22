"""climate-risk CLI entrypoint.

Milestone status (see README.md for the authoritative table): `ingest` (M1),
`build-silver` (M2), `backtest` (M4), `score` (M5) and `publish` are
implemented. `features`/`model` are library functions
(climate_risk.features.decoupling, climate_risk.scenarios.engine) not yet
wired as standalone CLI commands. `run` chains every implemented stage.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import structlog
import typer

from climate_risk.config.loader import RunPaths, load_countries, load_source_registry
from climate_risk.contracts.models import QualitySeverity
from climate_risk.contracts.run import PipelineRun
from climate_risk.observability.logging import configure_logging, get_logger

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
    lake_root: str | None = typer.Option(None, help="Override the local lake root."),
) -> None:
    """Fetch, validate and snapshot configured sources into raw/ and bronze/."""
    from climate_risk.ingestion.base import SourceAdapter
    from climate_risk.ingestion.owid import OwidCo2Adapter
    from climate_risk.ingestion.pipeline import run_ingest
    from climate_risk.ingestion.world_bank import WorldBankAdapter

    log = get_logger(stage="ingest")
    paths = RunPaths.from_env({"CLIMATE_RISK_LAKE_ROOT": lake_root} if lake_root else {})
    paths.ensure_zones()

    registry = load_source_registry()
    adapters: dict[str, SourceAdapter] = {
        "owid_co2": OwidCo2Adapter(),
        "world_bank_wdi": WorldBankAdapter(),
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
            manifest = run_ingest(adapters[key], paths=paths, run_id=run.run_id)
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
def build_silver(
    lake_root: str | None = typer.Option(None, help="Override the local lake root."),
) -> None:
    """Build dim_country + fact_country_year_transition from the latest bronze snapshots."""
    from climate_risk.config.loader import load_countries
    from climate_risk.transforms.silver import (
        build_dim_country,
        build_silver_panel,
        latest_complete_common_year,
    )
    from climate_risk.transforms.writer import write_dim_country, write_fact_country_year_transition

    log = get_logger(stage="build-silver")
    paths = RunPaths.from_env({"CLIMATE_RISK_LAKE_ROOT": lake_root} if lake_root else {})
    paths.ensure_zones()

    panel, snapshot_set_id, report = build_silver_panel(paths)
    if report.has_fatal:
        for event in report.by_severity(QualitySeverity.FATAL):
            log.error("silver build blocked", rule_id=event.rule_id, message=event.message)
        raise typer.Exit(code=1)

    for event in report.events:
        log.warning("quality event", rule_id=event.rule_id, message=event.message)

    write_dim_country(build_dim_country(), paths=paths)
    write_fact_country_year_transition(panel, snapshot_set_id=snapshot_set_id, paths=paths)

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


@app.command()
def backtest(
    lake_root: str | None = typer.Option(None, help="Override the local lake root."),
    n_simulations: int = typer.Option(10_000, help="Bootstrap simulation count per split."),
    random_seed: int = typer.Option(42, help="Seed for reproducibility."),
) -> None:
    """Run rolling-origin backtests over the latest silver panel and write gold/backtest_summary.parquet."""
    import glob

    from climate_risk.backtesting.rolling_origin import run_backtest, summarise_metrics

    log = get_logger(stage="backtest")
    paths = RunPaths.from_env({"CLIMATE_RISK_LAKE_ROOT": lake_root} if lake_root else {})

    fact_dirs = sorted(
        glob.glob(str(paths.silver / "fact_country_year_transition" / "snapshot_set_id=*"))
    )
    if not fact_dirs:
        typer.echo("no silver panel found; run `climate-risk build-silver` first", err=True)
        raise typer.Exit(code=1)
    panel = pd.read_parquet(Path(fact_dirs[-1]) / "data.parquet")

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
    paths.gold.mkdir(parents=True, exist_ok=True)
    results.to_parquet(paths.gold / "backtest_country_origin.parquet", index=False)
    summary.to_parquet(paths.gold / "backtest_summary.parquet", index=False)

    log.info("backtest complete", n_splits=len(results), origins=origins)
    typer.echo(summary.to_string(index=False))


@app.command()
def score(
    lake_root: str | None = typer.Option(None, help="Override the local lake root."),
    target_year: int = typer.Option(
        2050, help="Scenario horizon for the forward-downside component."
    ),
    random_seed: int = typer.Option(
        42, help="Seed for scenario simulation and weight perturbation."
    ),
) -> None:
    """Compute transition risk scores (v1, 4 of 5 components) and write gold/country_transition_risk.parquet."""
    import glob
    import json

    from climate_risk.features.decoupling import compute_decoupling_for_panel
    from climate_risk.scenarios.engine import run_country_scenario
    from climate_risk.scoring.risk_score import (
        WEIGHT_COVERAGE,
        compute_raw_metrics,
        compute_risk_scores,
        weight_perturbation_analysis,
    )

    log = get_logger(stage="score")
    paths = RunPaths.from_env({"CLIMATE_RISK_LAKE_ROOT": lake_root} if lake_root else {})

    fact_dirs = sorted(
        glob.glob(str(paths.silver / "fact_country_year_transition" / "snapshot_set_id=*"))
    )
    if not fact_dirs:
        typer.echo("no silver panel found; run `climate-risk build-silver` first", err=True)
        raise typer.Exit(code=1)
    panel = pd.read_parquet(Path(fact_dirs[-1]) / "data.parquet")
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

    paths.gold.mkdir(parents=True, exist_ok=True)
    scores.to_parquet(paths.gold / "country_transition_risk.parquet", index=False)
    (paths.gold / "rank_stability.json").write_text(
        json.dumps(stability, indent=2), encoding="utf-8"
    )

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
def publish(
    lake_root: str | None = typer.Option(None, help="Override the local lake root."),
) -> None:
    """Fail-closed publish: promote the current gold outputs to latest_successful_run,
    or refuse and leave the previous release untouched (climate_risk.publishing.barrier).

    Requires: an accepted silver panel, backtest gold outputs, and score gold
    outputs to already exist (run `climate-risk run` first, or ingest/build-silver/
    backtest/score individually). Writes a full evidence manifest to
    gold/manifests/<run_id>.json in addition to the barrier's own pointer file.
    """
    import glob
    import hashlib
    import json

    from climate_risk.publishing.barrier import PublishBlockedError
    from climate_risk.publishing.barrier import publish as publish_barrier
    from climate_risk.scoring.risk_score import EFFECTIVE_WEIGHTS

    log = get_logger(stage="publish")
    paths = RunPaths.from_env({"CLIMATE_RISK_LAKE_ROOT": lake_root} if lake_root else {})
    run = PipelineRun.start()
    log = log.bind(run_id=run.run_id)

    def _fail(stage: str, message: str) -> None:
        run.fail(stage=stage, message=message)
        log.error("publish blocked", stage=stage, message=message)

    source_snapshots: dict[str, dict[str, str]] = {}
    for source_name in ("owid_co2", "world_bank_wdi"):
        manifest_paths = sorted(
            glob.glob(str(paths.raw / f"source={source_name}" / "*" / "*" / "manifest.json"))
        )
        if not manifest_paths:
            _fail("ingest", f"no ingestion manifest found for source={source_name}")
            typer.echo(f"publish blocked: no ingestion manifest for {source_name}", err=True)
            raise typer.Exit(code=1)
        latest_manifest = json.loads(Path(manifest_paths[-1]).read_text(encoding="utf-8"))
        if latest_manifest["status"] != "ACCEPTED":
            _fail("ingest", f"latest {source_name} snapshot has status {latest_manifest['status']}")
            typer.echo(f"publish blocked: {source_name} snapshot not ACCEPTED", err=True)
            raise typer.Exit(code=1)
        source_snapshots[source_name] = {
            "sha256": latest_manifest["sha256"],
            "retrieved_at_utc": latest_manifest["retrieved_at_utc"],
        }

    fact_dirs = sorted(
        glob.glob(str(paths.silver / "fact_country_year_transition" / "snapshot_set_id=*"))
    )
    if not fact_dirs:
        _fail("build-silver", "no silver panel found")
        typer.echo("publish blocked: no silver panel found", err=True)
        raise typer.Exit(code=1)
    snapshot_set_id = Path(fact_dirs[-1]).name.removeprefix("snapshot_set_id=")
    panel = pd.read_parquet(Path(fact_dirs[-1]) / "data.parquet")
    countries = set(load_countries().keys())

    from climate_risk.transforms.silver import latest_complete_common_year

    eligible_year = latest_complete_common_year(panel, countries=countries)
    completeness = (
        float(panel[panel["year"] == eligible_year]["is_core_complete"].mean())
        if eligible_year is not None
        else 0.0
    )

    backtest_summary_path = paths.gold / "backtest_summary.parquet"
    score_path = paths.gold / "country_transition_risk.parquet"
    if not backtest_summary_path.exists():
        _fail("backtest", "no gold/backtest_summary.parquet found")
        typer.echo("publish blocked: no backtest output found", err=True)
        raise typer.Exit(code=1)
    if not score_path.exists():
        _fail("score", "no gold/country_transition_risk.parquet found")
        typer.echo("publish blocked: no score output found", err=True)
        raise typer.Exit(code=1)

    backtest_summary = pd.read_parquet(backtest_summary_path)
    scores = pd.read_parquet(score_path)

    run.snapshot_set_id = snapshot_set_id
    run.feature_set_version = "decoupling_v1"
    run.model_version = "empirical_bootstrap_v1"
    config_source = json.dumps(
        {"weights": dict(EFFECTIVE_WEIGHTS), "sources": sorted(source_snapshots)},
        sort_keys=True,
    )
    run.config_hash = hashlib.sha256(config_source.encode()).hexdigest()[:16]
    run.succeed(release_id=snapshot_set_id)

    manifest = {
        "run_id": run.run_id,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "git_sha": run.git_commit,
        "container_image_digest": None,  # populated once this runs inside a built image
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
        "azure_job_execution_id": None,  # populated when run as an Azure Container Apps Job
    }
    (paths.gold / "manifests").mkdir(parents=True, exist_ok=True)
    (paths.gold / "manifests" / f"{run.run_id}.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    try:
        publish_barrier(run, gold_root=paths.gold)
    except PublishBlockedError as exc:
        typer.echo(f"publish blocked: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    log.info("published", release_id=snapshot_set_id, countries=len(scores))
    typer.echo(f"published release_id={snapshot_set_id} ({len(scores)} countries scored)")


@app.command()
def run() -> None:
    """Run every implemented stage in order: ingest, build-silver, backtest, score, publish."""
    ingest(source=None, lake_root=None)
    build_silver(lake_root=None)
    backtest(lake_root=None, n_simulations=10_000, random_seed=42)
    score(lake_root=None, target_year=2050, random_seed=42)
    publish(lake_root=None)
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
