# Power BI Measure Catalogue

Keep DAX thin. Measures format and slice already-computed Python outputs; they
do not reimplement scoring, energy components, backtesting, regimes, or
scenario generation.

## Core Measures

```DAX
Active Risk Score =
MAX ( country_overview[score_total] )
```

```DAX
Data Confidence =
MAX ( country_overview[data_confidence_score] )
```

```DAX
Current Rank =
MIN ( country_overview[rank] )
```

```DAX
Score Delta v2 vs v1 =
MAX ( country_overview[score_delta_v2_minus_v1] )
```

```DAX
Rank Delta v2 vs v1 =
MAX ( country_overview[rank_delta_v2_minus_v1] )
```

```DAX
Latest Model Year =
MAX ( run_metadata[latest_model_eligible_year] )
```

```DAX
Latest Run Completed At =
MAX ( run_metadata[completed_at] )
```

## Scenario Measures

```DAX
Scenario P50 =
MAX ( scenario_quantiles[forecast_p50] )
```

```DAX
Scenario Interval Width =
MAX ( scenario_quantiles[forecast_p95] )
    - MAX ( scenario_quantiles[forecast_p05] )
```

```DAX
Scenario Horizon Years =
MAX ( scenario_quantiles[scenario_horizon_years] )
```

## Model Evidence Measures

```DAX
Backtest MAE =
AVERAGE ( backtest_metrics[mae] )
```

```DAX
Backtest Coverage 90 =
AVERAGE ( backtest_metrics[coverage_90] )
```

```DAX
Calibration Gap 90 =
AVERAGE ( backtest_metrics[calibration_gap_90] )
```

```DAX
Mean Interval Width 90 =
AVERAGE ( backtest_metrics[mean_interval_width_90] )
```

## Dynamic Labels

```DAX
Selected Country Title =
SELECTEDVALUE ( country_overview[country_name], "G20 sovereigns" )
```

```DAX
Production Scenario Label =
"Production forecast: "
    & MAX ( run_metadata[production_scenario_method] )
```

```DAX
Diagnostic Warning =
"Structural-change diagnostics are not used to select the production forecast."
```

## Conditional Formatting

Risk score:

- low risk: lighter/desaturated green-blue
- medium risk: amber
- high risk: red

Data confidence:

- separate blue scale
- never reuse the risk scale

Regime diagnostics:

- neutral analytical palette
- use text labels for diagnostic-only status
