# Endpoint Reference

Base path for all analytical endpoints: `/api/v1`. `GET /health` is
outside the versioned path (a liveness probe, not part of the data
contract).

All endpoints are `GET`-only and unauthenticated. See `security.md` for
what is deliberately never returned.

| Endpoint | Returns |
|---|---|
| `GET /health` | `{"status": "ok"}` liveness check. |
| `GET /api/v1/meta` | Active score/component/scenario versions, source run ID, Git SHA, source snapshot IDs, generation time, data schema version. |
| `GET /api/v1/countries` | Lightweight per-country catalogue: ISO3, name, region, income group, active risk score, rank, confidence. Query params: `region`, `min_risk_score`, `limit` (<=100), `offset`. |
| `GET /api/v1/countries/{iso3}` | Full profile: active score, v1/v2 comparison, component decomposition, latest transition/energy snapshot, production scenario summary, provenance. `iso3` is case-insensitive. 404 if unknown. |
| `GET /api/v1/countries/{iso3}/timeseries` | Historical transition indicators (carbon intensity, CO2/capita, etc). Query params: `start_year`, `end_year` (422 if `start_year > end_year`). |
| `GET /api/v1/countries/{iso3}/energy` | Historical electricity-mix indicators. Same year-range params as timeseries. |
| `GET /api/v1/countries/{iso3}/scenario` | **Production scenario only** (`empirical_bootstrap_v1`): P5/P50/P95, horizon, method. Never returns an experimental variant. 404 if no scenario exists for the country. |
| `GET /api/v1/countries/{iso3}/risk-components` | Score decomposition, both `v1` and `v2_energy` rows (each flagged `is_active_score`). |
| `GET /api/v1/countries/{iso3}/score-comparison` | `v1` vs `v2_energy`: scores, ranks, deltas. No new scoring logic -- both values read directly from the bundle. |
| `GET /api/v1/rankings` | Current ranking on the production score. Query params: `sort` (`risk_desc` default, or `risk_asc`), `limit` (<=19, the full covered-country count). |
| `GET /api/v1/backtests` | Rolling-origin model evidence: summary rows (MAE/RMSE/coverage per model variant) and individual country/origin splits. Query params: `model_variant`, `country`, `origin_year`, `limit`, `offset`. Historical undercoverage is not filtered out. |
| `GET /api/v1/diagnostics/regimes/{iso3}` | M7 structural-break/regime diagnostics. **Every entry carries `production_use: false` and `status: "research_diagnostic"`.** 404 if unknown ISO3. |

## Errors

- Unknown ISO3 -> `404 {"detail": "Unknown country ISO3 code: '...'"}`.
- `start_year > end_year` -> `422 {"detail": "start_year must be <= end_year"}`.
- Out-of-range query params (e.g. `limit` above the endpoint's cap) -> `422`
  (FastAPI/Pydantic validation, standard shape).
- Published bundle missing/inconsistent -> the process **fails to start**
  (see `contracts.md`), not a per-request 503 -- there is no scenario
  where the API is "up" but serving from a known-bad bundle.

## Example: full request/response walkthrough

```bash
curl -s http://127.0.0.1:8000/api/v1/countries/idn | jq
```

Returns Indonesia's full profile -- at time of writing, the highest-risk
covered country (`risk_score: 92.4`, `rank: 1`), including its production
scenario (`empirical_bootstrap_v1`, P5/P50/P95 for 2030) and provenance
(`run_id`, `completed_at`).
