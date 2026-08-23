# Data card

Three public, openly-licensed statistical datasets feed this platform.
`config/sources.yaml` is the controlled source registry — a source with a
`licence_review_status` other than `approved` cannot influence a
production `gold` output; this is enforced in code
(`climate_risk.config.models` + the publish-time quality gate), not just
documented here.

## OWID CO2

- **Provider**: Our World in Data
- **Dataset**: `owid-co2-data.csv`
- **URL**: `https://github.com/owid/co2-data/raw/master/owid-co2-data.csv`
- **License**: CC-BY-4.0 (attribution required)
- **Fields used**: CO2 emissions, GDP (from OWID's own merge of national
  accounts sources), population
- **Coverage**: annual, global, filtered to the 19 covered G20 sovereigns
- **Update characteristics**: `refresh_check: weekly` in the source
  registry — OWID refreshes this dataset periodically as upstream national
  accounts and emissions inventories are revised
- **Adapter**: `owid_co2_v1` (`src/climate_risk/ingestion/owid.py`)
- **Raw snapshot policy**: every fetch is content-hashed
  (`source_snapshot_id` = first 16 hex chars of the SHA-256 of the raw
  response bytes) and persisted at
  `raw/source=owid_co2/ingest_date=<date>/run_id=<uuid>/payload.bin` —
  never overwritten. In Azure this blob is tiered to cool storage after 30
  days for cost, never deleted.
- **Known limitations**: OWID's own GDP figures lag the current year by
  design (a `DQ-GDP-020` quality event is raised and logged, not hidden,
  whenever the latest source year has missing GDP for covered countries).

## World Bank WDI

- **Provider**: World Bank
- **Dataset**: World Development Indicators — `NY.GDP.MKTP.KD` (GDP,
  constant 2015 US$) and `SP.POP.TOTL` (total population)
- **URL**: `https://api.worldbank.org/v2/country/{country}/indicator/{indicator}`
- **License**: CC-BY-4.0 (attribution required)
- **Fields used**: GDP, population
- **Coverage**: annual, per-country API calls for the 19 covered sovereigns
- **Update characteristics**: `refresh_check: weekly`
- **Adapter**: `world_bank_v1` (`src/climate_risk/ingestion/world_bank.py`)
- **Raw snapshot policy**: same content-hash-and-persist policy as above;
  the merged multi-indicator response is hashed as one artifact.
- **Known limitations**: World Bank revises historical GDP/population
  figures as national accounts methodologies update; a later run can show
  a different historical value for the same country-year purely from this
  revision, not from any model change (see `docs/reproducibility.md`'s
  data revision analysis for how this is detected).

## OWID Energy

- **Provider**: Our World in Data, re-publishing Ember's Yearly Electricity
  Data and the Energy Institute Statistical Review of World Energy
- **Dataset**: `owid-energy-data.csv`
- **URL**: `https://owid-public.owid.io/data/energy/owid-energy-data.csv`
- **License**: CC-BY-4.0 (attribution required)
- **Fields used**: coal/fossil/renewables/low-carbon share of electricity
  generation
- **Coverage**: annual, filtered to the 19 covered sovereigns
- **Update characteristics**: `refresh_check: weekly`
- **Adapter**: `owid_energy_v1` (`src/climate_risk/ingestion/owid_energy.py`)
- **Raw snapshot policy**: same content-hash-and-persist policy as above.
- **Known limitations**: electricity-mix shares only — this dataset does
  not cover primary energy consumption mix or non-electricity energy uses
  (transport fuel, industrial heat); see `docs/m6_source_feasibility.md`
  for the full licence/access/coverage verification that selected this
  source over the alternatives evaluated.

## Fail-closed data rules

- **No silent GDP imputation.** A country-year with missing GDP is left
  missing and surfaced via a logged quality event
  (`DQ-GDP-020`) and a lower `data_confidence_score` — it is never filled
  with an interpolated, carried-forward, or estimated value.
- **No aggregate leakage.** The EU is a G20 member but an aggregate region;
  `config/countries.yaml` deliberately excludes it — aggregates must never
  appear inside a sovereign-country ranking.
- **Unlicensed sources cannot reach production.** `ember_global_electricity`
  is registered in `config/sources.yaml` with
  `licence_review_status: pending_verification` and `enabled: false`; it
  cannot influence any `gold` output until (if ever) its licence is
  reviewed and approved, and the config/quality-gate enforce this in code.
- **Confidence is reported, not folded into risk.** `data_confidence_score`
  is a separate field on every country record — low confidence never
  silently raises or lowers the reported risk score.

## Deferred / excluded sources

`ember_global_electricity` was evaluated (see `docs/m6_source_feasibility.md`)
as a potential primary-source alternative for electricity-mix data but is
disabled pending licence verification; OWID Energy's re-publication of
Ember + Energy Institute data was used instead since its licence was
already clear (CC-BY-4.0). No other sources were evaluated and deferred for
v1 — the three enabled sources above are the complete v1 data footprint.

## Geography data (web dashboard only)

The React dashboard's Executive Overview map uses `world-atlas`'s public
domain Natural Earth 110m country topology (bundled as an npm dependency,
not fetched from an external API at runtime) purely for country boundary
geometry — it contributes no analytical values, only the shapes the risk
scores are colored onto. See `LICENSE` for the distinction between this
repository's software license and third-party dataset licenses.
