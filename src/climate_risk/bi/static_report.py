"""Static portfolio preview for the M9 BI layer."""

from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd

from climate_risk.storage import LakeStorage, read_parquet


def render_portfolio_preview(lake: LakeStorage, output_path: Path) -> Path:
    overview = read_parquet(lake.gold, "bi/country_overview.parquet")
    scenarios = read_parquet(lake.gold, "bi/scenario_quantiles.parquet")
    backtest = read_parquet(lake.gold, "bi/backtest_metrics.parquet")
    regimes = read_parquet(lake.gold, "bi/regime_diagnostics.parquet")
    metadata = read_parquet(lake.gold, "bi/run_metadata.parquet")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = _page(overview, scenarios, backtest, regimes, metadata)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def _page(
    overview: pd.DataFrame,
    scenarios: pd.DataFrame,
    backtest: pd.DataFrame,
    regimes: pd.DataFrame,
    metadata: pd.DataFrame,
) -> str:
    active = metadata.iloc[0].to_dict() if len(metadata) else {}
    top = overview.sort_values("rank").head(10)
    components = [
        "score_pace",
        "score_coupling",
        "score_volatility",
        "score_forward_downside",
        "score_energy",
    ]
    model_summary = backtest[backtest["metric_grain"] == "summary"].copy()
    diagnostic_count = int(len(regimes))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Climate Transition Risk Intelligence Preview</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 32px; color: #17202a; }}
    header {{ border-bottom: 2px solid #1f4e5f; padding-bottom: 16px; margin-bottom: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; }}
    h2 {{ margin-top: 32px; color: #1f4e5f; }}
    .note {{ color: #52616b; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
    .card {{ border: 1px solid #d8dee4; border-radius: 6px; padding: 12px; }}
    .value {{ font-size: 24px; font-weight: 650; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: 7px 8px; text-align: left; }}
    th {{ background: #f3f6f8; }}
    .bar {{ background: #d8e8ee; height: 10px; border-radius: 4px; overflow: hidden; }}
    .bar span {{ display: block; height: 10px; background: #b84a4a; }}
    .warn {{ background: #fff7e6; border-left: 4px solid #c77d00; padding: 10px; }}
  </style>
</head>
<body>
<header>
  <h1>Climate Transition Risk Intelligence</h1>
  <div class="note">Static portfolio preview generated from <code>gold/bi</code> tables. Power BI Desktop visual assembly remains separate.</div>
</header>
<section class="grid">
  <div class="card"><div>Active score</div><div class="value">{escape(str(active.get("active_score_version", "")))}</div></div>
  <div class="card"><div>Countries</div><div class="value">{len(overview)}</div></div>
  <div class="card"><div>Production scenario</div><div class="value">{escape(str(active.get("production_scenario_method", "")))}</div></div>
  <div class="card"><div>Latest run</div><div class="value">{escape(str(active.get("run_id", "")))[:8]}</div></div>
</section>
<h2>Executive Overview</h2>
{_risk_table(top)}
<h2>Scenario Explorer</h2>
{_scenario_table(scenarios.sort_values("country_iso3").head(10))}
<h2>Model Evidence</h2>
<div class="warn">Historical P5-P95 intervals under-cover the nominal 90% target; calibration limitations are intentionally visible.</div>
{_simple_table(model_summary[["model_variant", "n_splits", "mae", "coverage_90", "calibration_gap_90", "mean_interval_width_90"]])}
<h2>Structural Change Diagnostics</h2>
<p>{diagnostic_count} diagnostic rows are available. These are not used to select production forecasts or scores.</p>
{_simple_table(regimes[["country_iso3", "series_name", "strongest_break_year", "regime_confidence", "diagnostic_status"]].head(10))}
<h2>Largest Component Drivers</h2>
{_component_driver_table(overview, components)}
</body>
</html>
"""


def _risk_table(frame: pd.DataFrame) -> str:
    rows = []
    for row in frame.to_dict(orient="records"):
        score = float(row["score_total"])
        rows.append(
            "<tr>"
            f"<td>{escape(str(row['rank']))}</td>"
            f"<td>{escape(str(row['country_name']))}</td>"
            f"<td>{score:.1f}<div class='bar'><span style='width:{score:.0f}%'></span></div></td>"
            f"<td>{escape(str(row['rank_band']))}</td>"
            f"<td>{float(row['data_confidence_score']):.1f}</td>"
            "</tr>"
        )
    return (
        "<table><tr><th>Rank</th><th>Country</th><th>Risk score</th><th>Band</th><th>Data confidence</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def _scenario_table(frame: pd.DataFrame) -> str:
    return _simple_table(
        frame[
            [
                "country_iso3",
                "origin_year",
                "target_year",
                "forecast_p05",
                "forecast_p50",
                "forecast_p95",
                "deterministic_baseline",
            ]
        ]
    )


def _component_driver_table(overview: pd.DataFrame, components: list[str]) -> str:
    rows = []
    for row in overview.sort_values("rank").head(10).to_dict(orient="records"):
        driver = max(components, key=lambda column: float(row.get(column, 0.0)))
        rows.append(
            {
                "country": row["country_name"],
                "top_driver": driver.removeprefix("score_"),
                "driver_score": round(float(row[driver]), 1),
            }
        )
    return _simple_table(pd.DataFrame(rows))


def _simple_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "<p>No rows available.</p>"
    header = "".join(f"<th>{escape(str(column))}</th>" for column in frame.columns)
    rows = []
    for row in frame.to_dict(orient="records"):
        cells = "".join(f"<td>{_format_cell(value)}</td>" for value in row.values())
        rows.append(f"<tr>{cells}</tr>")
    return f"<table><tr>{header}</tr>{''.join(rows)}</table>"


def _format_cell(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return escape(str(value))
