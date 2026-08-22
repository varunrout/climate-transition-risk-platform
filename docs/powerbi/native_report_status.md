# Native Power BI Report -- Status and Validation Record

## Environment detection (performed, not assumed)

Checked on the Windows development machine before writing any project files:

- `C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe` -- not present
- `C:\Program Files (x86)\Microsoft Power BI Desktop\bin\PBIDesktop.exe` -- not present
- `%LOCALAPPDATA%\Microsoft\WindowsApps\PBIDesktop.exe` (Store install) -- not present
- `Get-AppxPackage -Name "*PowerBI*"` -- no results
- `HKLM:\...\Uninstall\*` registry scan for `Power BI` -- no results
- `pbi-tools`, `pbi-tools.exe`, `TabularEditor`, `TabularEditor.exe`, `TE3.exe` on PATH -- none found

**Conclusion: Power BI Desktop is not installed, and no CLI-based Power BI
project tooling (pbi-tools, Tabular Editor) is available in this
environment.** Per this project's honesty rules, Power BI Desktop was
**not** installed solely to force this task through -- that would be
adding a large interactive GUI dependency for a one-off report build, which
the M9 brief itself explicitly discourages ("Do not install random
third-party software merely to force report generation").

## What was built anyway

A complete, source-controlled PBIP project was hand-authored against the
current, documented PBIP/TMDL/PBIR schema:

```text
powerbi/
    ClimateTransitionRisk.pbip
    ClimateTransitionRisk.Report/          (PBIR -- one folder per page, one folder per visual)
    ClimateTransitionRisk.SemanticModel/   (TMDL -- one file per table + relationships/model/expressions)
```

- **9 tables**: the 8 real `gold/bi/*.parquet` tables plus one calculated
  `dim_year` table (DAX `UNION`/`DISTINCT` over the three year-grained
  fact tables), matching `docs/powerbi/semantic_model.md` exactly -- no
  redesign.
- **9 relationships**: `country_overview` (1) to each of the six fact
  tables' `country_iso3` (*), plus `dim_year` (1) to the three
  year-grained fact tables' year columns, all single-direction, matching
  the semantic model doc's recommended table exactly.
- **28 DAX measures** covering every item in the M9 measure list (Active
  Transition Risk Score, Country Rank, Data Confidence, Weight Coverage,
  Score v1/v2, Score/Rank Delta, Selected Country, Latest Model Year,
  Latest Successful Run [+ Run Id], Carbon Intensity [+ a dedicated
  `Carbon Intensity Trend` for the year-series visuals], Clean/Fossil
  Electricity Share, Transition Momentum, Scenario P5/P50/P95 [+
  deterministic baseline], Backtest MAE, Interval Coverage, Calibration
  Gap, Active Score Version), plus three supporting measures
  (`Component Score`, `Low Carbon Share`, `Slope Delta`) added specifically
  so the report's trend/decomposition visuals have a real measure to bind
  to rather than referencing a raw column as if it were one.
- **7 report pages**, in the exact order and with the exact names from
  `docs/powerbi/page_specs.md`: Executive Overview, Country Profile,
  Energy Transition, Scenario Explorer, Model Evidence, Structural Change
  Diagnostics (with the required diagnostic-only banner), Data Quality &
  Provenance -- 49 visual containers total (cards, tables, bar/line
  charts, a slicer, a filled map, text callouts), built from the "2-4
  primary visuals" density `docs/powerbi/design_system.md` specifies, not
  an exhaustive rendering of every bullet in the page spec.
- A `GoldBiFolderPath` Power Query text parameter (not a hardcoded literal
  in every table) so every table's `Parquet.Document(File.Contents(...))`
  partition reads from one place; local portfolio mode per
  `docs/powerbi/refresh_and_auth.md`.

## Validation actually performed (and what was NOT)

Power BI Desktop was not available, so the report **could not be opened,
could not be confirmed to load, and no visual has been confirmed to
render**. That is a real, stated limitation, not an oversight. What *was*
done, mechanically, against the actual files:

1. **JSON syntax**: all 64 `.json`/`.pbir`/`.pbism`/`.platform`/`.pbip`
   files parse as valid JSON (`json.load` over every file) -- 0 failures.
2. **TMDL structural sanity**: every `.tmdl` file uses consistent
   tab-indentation and contains the expected top-level keyword
   (`table`/`database`/`model`/`relationship`/`expression`/`cultureInfo`).
3. **Field-reference cross-check (the check most likely to catch a real
   authoring mistake, and the one that DID catch mistakes)**: every column
   and measure reference used in all 49 visuals was parsed out of the
   TMDL table definitions and checked against the actual defined
   columns/measures for that table. The first pass found **6 real
   mistakes** -- five visuals referencing a raw column as if it were a
   measure (`risk_components[component_score]`,
   `energy_indicators[low_carbon_share_elec]`,
   `regime_diagnostics[slope_delta]` used directly, and a `country_overview`
   measure name reused against `country_timeseries`, which doesn't have
   that measure). Three new measures (`Component Score`, `Low Carbon
   Share`, `Slope Delta`) and one renamed/relocated measure (`Carbon
   Intensity Trend` on `country_timeseries`) were added specifically to
   fix these, and the six affected visual JSON files were corrected. The
   check was then re-run clean: **all 49 visuals' field references now
   resolve to a real column or measure on the table they claim to query.**
4. **Relationship cross-check**: all 9 relationships' `fromColumn`/
   `toColumn` pairs resolve to real columns on real tables.
5. **Model/table-file cross-check**: `model.tmdl`'s `ref table` list
   matches the actual table files on disk exactly (no missing, no stale
   references).

What none of this proves: whether Power BI Desktop's actual parser accepts
this exact PBIR/TMDL schema-version combination, whether the Parquet
connector reads these files without a type-coercion warning, whether
layout/z-ordering renders sensibly, or whether any visual type
(`filledMap`, `tableEx`, etc.) is spelled/configured exactly as the
installed Desktop version expects. None of that can be verified without
Desktop itself.

## What a user must do before treating this as finished

1. Install Power BI Desktop (Microsoft Store or the MSI from
   `powerbi.microsoft.com/desktop`).
2. Run `uv run climate-risk build-bi --scenario-target-year 2030` if
   `data/lake/gold/bi/*.parquet` isn't already present/current.
3. Open `powerbi/ClimateTransitionRisk.pbip`.
4. If Desktop asks to update the `GoldBiFolderPath` parameter, point it at
   the local `data/lake/gold/bi/` folder (Transform data > Manage
   Parameters).
5. Let Desktop attempt to load; **fix whatever it reports**. Given the
   automated checks above, an error is most likely to be a schema/version
   mismatch in the PBIR/TMDL JSON (e.g. a `$schema` version string this
   Desktop build doesn't recognise) rather than a broken table/measure/
   relationship reference -- but that is an expectation, not a claim.
6. Once it opens cleanly, walk all 7 pages, confirm visuals render, and
   export the screenshots listed in `docs/powerbi/screenshots/README.md`.
7. Optionally save as PBIX for distribution (see
   `docs/powerbi/portfolio_story.md` for why PBIX is not committed to the
   repository).

## Status

**M9 CODE/DATA COMPLETE. NATIVE REPORT PROJECT AUTHORED BUT BLOCKED FROM
DESKTOP VALIDATION -- Power BI Desktop is not installed in this
environment, so the PBIP project above has never actually been opened.**
