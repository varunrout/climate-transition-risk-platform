"""climate-risk CLI entrypoint.

Milestone status (see README.md for the authoritative table): `ingest` is
implemented for OWID and World Bank (M1). `build-silver`, `features`,
`model`, `backtest`, `score`, `publish` are not yet implemented and exit
with a clear NotImplementedError rather than pretending to run. `run`
chains whichever stages exist.
"""

from __future__ import annotations

import sys

import structlog
import typer

from climate_risk.config.loader import RunPaths, load_countries, load_source_registry
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
def build_silver() -> None:
    """Not yet implemented (M2)."""
    _not_implemented("build-silver", milestone="M2")


@app.command()
def features() -> None:
    """Not yet implemented (M3)."""
    _not_implemented("features", milestone="M3")


@app.command()
def model() -> None:
    """Not yet implemented (M3)."""
    _not_implemented("model", milestone="M3")


@app.command()
def backtest() -> None:
    """Not yet implemented (M4)."""
    _not_implemented("backtest", milestone="M4")


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
    """Run every implemented stage in order. Currently: ingest only."""
    ingest(source=None, lake_root=None)
    typer.echo(
        "Stages build-silver/features/model/backtest/score/publish are not yet "
        "implemented; run stopped after ingest. See README.md milestone table.",
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
