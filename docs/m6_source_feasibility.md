# M6 source feasibility report

- Status: Research complete, implementation gated on this review
- Date: 2026-08-22

## Purpose

Before ingesting any energy-system data for M6, verify per source: (1) licensing,
(2) programmatic access, (3) actual country/year coverage for this project's 19-country
G20 panel, (4) update cadence, (5) units/methodology. This report is the record of that
verification. Only sources marked **PASS** below are implemented.

## Sources investigated

### 1. Our World in Data — `energy-data` — PASS (recommended primary source)

- **Licence**: CC-BY-4.0 ("All visualizations, data, and code produced by Our World in
  Data are completely open access under the Creative Commons BY license"). Same licence
  family already `approved` for `owid_co2` in `config/sources.yaml` — no new licence
  type to review.
- **Programmatic access**: verified live — `curl -sI
  https://owid-public.owid.io/data/energy/owid-energy-data.csv` returns `200 OK`,
  stable direct URL, same access pattern as the existing `owid_co2_v1` adapter
  (single CSV, no auth, no rate limit encountered).
- **Coverage measured directly** (downloaded the real CSV and checked all 19 configured
  G20 countries): every country has data from **1985 through 2024 or 2025** with no
  gaps for the electricity-mix columns. This exceeds what's needed — full row set 1985.
- **Columns verified present** (fetched and grepped the actual CSV header, not assumed
  from memory): `fossil_share_elec`, `coal_share_elec`, `gas_share_elec`,
  `oil_share_elec`, `renewables_share_elec`, `solar_share_elec`, `wind_share_elec`,
  `hydro_share_elec`, `biofuel_share_elec`, `other_renewables_share_elec`,
  `other_renewables_share_elec_exc_biofuel`, `nuclear_share_elec`,
  `low_carbon_share_elec` (renewables + nuclear). All expressed as % of total
  electricity generation.
- **Update cadence**: annual; per the OWID `energy-data` GitHub repo, last updated
  April 2026 for the current data year.
- **Provenance note**: OWID's electricity-mix columns are themselves compiled from
  Ember's Yearly Electricity Data plus the Energy Institute's Statistical Review of
  World Energy. Using OWID directly gives the same underlying data as a direct Ember
  ingest, with a cleaner, already-verified access path (see #2 below) and an identical
  licence to a source already approved in this project.

### 2. Ember — `Yearly Electricity Data` (direct) — DEFERRED, not implemented in M6 v1

- **Licence**: verified CC-BY-4.0 via Ember's own site.
- **Programmatic access**: **not verified**. `ember-energy.org` returned `403
  Forbidden` to a direct fetch (typical of a JS-rendered/CDN-protected download page,
  not a stable public CSV endpoint); no direct bulk-CSV URL could be confirmed as
  reproducible from this environment.
- **Coverage** (from search, not independently measured): 2000 onward globally, 1990
  onward for Europe — narrower than OWID's verified 1985-onward panel for this
  project's countries.
- **Decision**: since OWID's `energy-data` already re-publishes Ember's electricity
  data with a verified access path, equal licence, and *wider* measured coverage for
  this project's exact country panel, a direct Ember adapter would be redundant. Left
  `disabled` / `pending_verification` in `config/sources.yaml` (unchanged from current
  state) rather than marked `approved` on unverified access.

### 3. World Bank WDI — `EG.ELC.COAL.ZS`, `EG.ELC.RNEW.ZS`, `EG.ELC.RNWX.ZS`/`.KH` — DEFERRED, not implemented in M6 v1

- **Licence**: CC-BY-4.0 — already `approved` in this project for `world_bank_wdi`.
- **Programmatic access**: verified live — `EG.ELC.COAL.ZS` for `USA` returns real
  values via the same API pattern already used by `world_bank_v1`.
- **Methodology note**: WDI's own documentation states these specific indicators are
  themselves sourced from IEA, not compiled independently by the World Bank — i.e.
  ingesting them would add a second, less-current, less-granular copy of largely the
  same coal/renewable-share signal OWID already provides directly from Ember/EI.
  Latest year is frequently null (e.g. `USA` 2025 = `null`, 2024 populated) — consistent
  with the reporting lag this project already handles explicitly for GDP.
  **Decision**: redundant with OWID `energy-data` for M6 v1. Not ingested now; kept as
  a documented option for a future independent cross-validation check, not as a
  primary feature source.

### 4. IEA — free datasets — EXCLUDED

- **Licence**: verified **CC BY-NC-SA 4.0** (non-commercial share-alike) for IEA's free
  datasets (e.g. World Energy Outlook Free Dataset) — explicitly: "free to copy,
  redistribute and adapt... provided the use is for non-commercial purposes"; commercial
  use requires contacting IEA directly. IEA's full electricity-statistics products
  (beyond the limited free dataset) require a paid subscription.
  **Decision**: excluded from M6 per the user's explicit instruction ("IEA only where
  redistribution/licensing permits"). The NC clause is a real, disqualifying constraint
  for a platform that should stay freely redistributable, and the free dataset's
  granularity is materially worse than what OWID/Ember already provide under a cleaner
  licence for the same underlying countries.

### 5. IRENA — renewable capacity/generation statistics — DEFERRED (optional future source)

- **Licence**: verified permissive — free reuse for both non-commercial and commercial
  purposes, redistribution allowed with attribution to IRENA.
- **Programmatic access**: not verified from this environment (IRENA's query-tool
  endpoint returned `403 Forbidden` to a direct fetch; would need a dedicated
  access-path investigation, e.g. IRENASTAT bulk downloads).
- **Coverage**: capacity statistics 2015–2024, generation 2015–2023 — narrower window
  than OWID's verified 1985-onward panel, and capacity-based rather than
  generation-mix-based.
- **Decision**: not needed for the M6 v1 feature set (which is generation-mix-driven).
  Noted as a candidate for a possible future "renewable build-out rate" feature refined
  by capacity-addition data, not required now.

## Feature contract (raw indicators only — see gating note below)

All features below are computed **only** from the PASS source (OWID `energy-data`) and
land in a new silver fact table, kept structurally separate from
`fact_country_year_transition` and from any risk-score component per the explicit
instruction to keep raw indicators separate from modelled/risk-score components.

**New silver table**: `fact_country_year_energy`
(`country_iso3`, `year`, `snapshot_set_id`, plus the raw share columns below,
1:1 with the source, no derived math at this layer):

| Column | Source column | Definition |
|---|---|---|
| `coal_share_elec` | `coal_share_elec` | % of electricity generation from coal |
| `gas_share_elec` | `gas_share_elec` | % from gas |
| `oil_share_elec` | `oil_share_elec` | % from oil |
| `fossil_share_elec` | `fossil_share_elec` | % from coal+gas+oil combined |
| `renewables_share_elec` | `renewables_share_elec` | % from all renewables |
| `low_carbon_share_elec` | `low_carbon_share_elec` | % from renewables + nuclear |
| `nuclear_share_elec` | `nuclear_share_elec` | % from nuclear |
| `solar_share_elec`, `wind_share_elec`, `hydro_share_elec`, `biofuel_share_elec` | same | sub-technology shares, for transparency/drill-down, not required by the v1 modelled features below |

**Derived feature families** (candidate list from the user's brief, mapped to concrete
formulas — computed in a *separate* module/artifact, e.g.
`gold/energy_transition_features.parquet`, never written into
`country_transition_risk.parquet` until the gating steps below pass):

| Feature family | Formula (using the raw table above) |
|---|---|
| Coal share of electricity | `coal_share_elec` (latest year) |
| Fossil share | `fossil_share_elec` (latest year) |
| Renewable share | `renewables_share_elec` (latest year) |
| Clean electricity share | `low_carbon_share_elec` (latest year) |
| Electricity carbon intensity proxy | not directly available from this source (no gCO2/kWh column in `energy-data`; would require Ember's separate emissions-intensity metric, not verified here) — **omitted from v1**, flagged as a gap |
| Coal generation trend | slope of `coal_share_elec` over trailing N years (reuse the existing deterministic-trend estimator from `climate_risk.scenarios.engine`) |
| Renewable build-out rate | year-over-year delta of `renewables_share_elec`, trailing-N-year average |
| Clean-power momentum | trailing-N-year slope of `low_carbon_share_elec` |
| Fossil lock-in / persistence | trailing-N-year mean of `fossil_share_elec` minus its own trend slope (low slope + high level = high lock-in) |
| Electricity-demand growth | **not available** — `energy-data` has generation-mix shares, not absolute demand/generation levels in this project's currently-ingested column subset; would require adding `electricity_demand`-family absolute columns, deferred |
| Emissions vs power-sector decarbonisation divergence | requires pairing with the existing OWID CO2 emissions series already ingested (`owid_co2`) — cross-source feature, computed once both silver tables exist |
| Transition velocity | rate of change of `low_carbon_share_elec`, normalised by distance-to-100% (percentage-points-per-year against remaining headroom) |
| Distance from recent trend / stalled transition | residual of latest actual `low_carbon_share_elec` vs the trend-projected value |
| Cross-country percentile positioning | percentile rank of each country's latest `low_carbon_share_elec` / `coal_share_elec` within the 19-country panel for that year |

**Explicitly out of scope for M6 v1**: electricity carbon intensity (gCO2/kWh) and
absolute electricity-demand growth — the currently-verified OWID `energy-data` columns
don't carry these directly, and either fabricating them or reaching for a second,
unverified source (Ember direct) to fill the gap would violate the project's "do not
silently fill missing energy data" / "no fabricated benchmarks" rules. Recorded as a
known gap, not implemented, not claimed.

## Risk-score gating (per explicit instruction — not yet done, in-scope for a later step)

Before any energy feature enters `country_transition_risk.parquet` or changes the
`weight_coverage`:

1. Quantify coverage of the new features across the 19-country panel and the backtest
   window.
2. Inspect collinearity between the new features and the existing carbon-intensity
   trend already driving part of the v1 score.
3. Test whether the new features add information beyond the existing carbon-intensity
   trend component (not just correlated noise).
4. Backtest any resulting score/model change using the existing rolling-origin harness.
5. Preserve the current score as `v1`; any change ships as `v2`, both retrievable, not
   overwritten.

None of this has been done yet. M6 v1, as scoped for this immediate implementation
pass, stops at raw ingestion + a separate derived-features artifact — it does **not**
touch `scoring/`.

## Summary decision

| Source | Verdict | Action |
|---|---|---|
| OWID `energy-data` | **PASS** | Implement: new adapter, new `fact_country_year_energy` silver table, new derived-features artifact |
| Ember (direct) | Licence OK, access unverified | Leave `disabled`/`pending_verification`, unchanged |
| World Bank WDI energy indicators | Verified but redundant | Not ingested; documented as a future cross-check option |
| IEA | Licence fails (NC clause) | Excluded |
| IRENA | Licence OK, access unverified, narrower/different data shape | Deferred, not implemented |

No change to `config/sources.yaml`'s `ember_global_electricity` entry's approval
status. No Azure infrastructure change required — same storage zones, same managed
identity, same Container Apps Job.
