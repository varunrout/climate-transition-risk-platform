"""climate-risk CLI entrypoint.

Milestone status (see README.md for the authoritative table): `ingest` (M1),
`build-silver` (M2) and `backtest` (M4) are implemented. `features`/`model`
are library functions (climate_risk.features.decoupling,
climate_risk.scenarios.engine) not yet wired as standalone CLI commands.
`score`, `publish` are not yet implemented and exit with a clear
NotImplementedError rather than pretending to run. `run` chains whichever
stages exist.
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
def score() -> None:
    """Not yet implemented (M5)."""
    _not_implemented("score", milestone="M5")


@app.command()
def publish() -> None:
    """Not yet implemented end-to-end (the publish barrier itself exists and is tested)."""
    _not_implemented("publish", milestone="M5")


@app.command()
def run() -> None:
    """Run every implemented stage in order. Currently: ingest, build-silver, backtest."""
    ingest(source=None, lake_root=None)
    build_silver(lake_root=None)
    backtest(lake_root=None, n_simulations=10_000, random_seed=42)
    typer.echo(
        "Stages score/publish are not yet implemented; run stopped after backtest. "
        "See README.md milestone table.",
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
