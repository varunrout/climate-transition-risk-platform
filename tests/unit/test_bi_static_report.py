from __future__ import annotations

from pathlib import Path

import pandas as pd

from climate_risk.bi.static_report import render_portfolio_preview
from climate_risk.storage import LakeStorage, LocalStorageBackend, write_parquet


def test_static_preview_is_generated_from_bi_tables(tmp_path: Path) -> None:
    lake = LakeStorage(
        raw=LocalStorageBackend(tmp_path / "raw"),
        bronze=LocalStorageBackend(tmp_path / "bronze"),
        silver=LocalStorageBackend(tmp_path / "silver"),
        gold=LocalStorageBackend(tmp_path / "gold"),
    )
    write_parquet(
        lake.gold,
        "bi/country_overview.parquet",
        pd.DataFrame(
            {
                "rank": [1],
                "country_name": ["Alpha"],
                "country_iso3": ["AAA"],
                "score_total": [75.0],
                "rank_band": ["elevated"],
                "data_confidence_score": [92.0],
                "score_pace": [80.0],
                "score_coupling": [70.0],
                "score_volatility": [65.0],
                "score_forward_downside": [60.0],
                "score_energy": [90.0],
            }
        ),
    )
    write_parquet(
        lake.gold,
        "bi/scenario_quantiles.parquet",
        pd.DataFrame(
            {
                "country_iso3": ["AAA"],
                "origin_year": [2024],
                "target_year": [2030],
                "forecast_p05": [0.4],
                "forecast_p50": [0.5],
                "forecast_p95": [0.7],
                "deterministic_baseline": [0.55],
            }
        ),
    )
    write_parquet(
        lake.gold,
        "bi/backtest_metrics.parquet",
        pd.DataFrame(
            {
                "metric_grain": ["summary"],
                "model_variant": ["empirical_bootstrap"],
                "n_splits": [114],
                "mae": [0.036],
                "coverage_90": [0.763],
                "calibration_gap_90": [0.137],
                "mean_interval_width_90": [0.140],
            }
        ),
    )
    write_parquet(
        lake.gold,
        "bi/regime_diagnostics.parquet",
        pd.DataFrame(
            {
                "country_iso3": ["AAA"],
                "series_name": ["carbon_intensity_gdp"],
                "strongest_break_year": [2020],
                "regime_confidence": [0.8],
                "diagnostic_status": ["diagnostic_only_not_production_forecast_selector"],
            }
        ),
    )
    write_parquet(
        lake.gold,
        "bi/run_metadata.parquet",
        pd.DataFrame(
            {
                "run_id": ["run-1"],
                "active_score_version": ["v2_energy"],
                "production_scenario_method": ["empirical_bootstrap_v1"],
            }
        ),
    )

    output = render_portfolio_preview(lake, tmp_path / "preview.html")

    html = output.read_text(encoding="utf-8")
    assert "Climate Transition Risk Intelligence" in html
    assert "empirical_bootstrap_v1" in html
    assert "not used to select production forecasts or scores" in html
    assert "Power BI Desktop visual assembly remains separate" in html
