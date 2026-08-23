> **SUPERSEDED PRODUCT PROTOTYPE -- NOT CURRENT PRODUCT LAYER.** See
> [`docs/powerbi/README.md`](README.md) and
> [ADR 0016](../adr/0016-m9-react-web-supersedes-power-bi.md). The React
> web dashboard under `web/` is now the canonical M9 product. This record
> is preserved unmodified below as engineering history.

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

## Update: live Desktop validation session (2026-08-22/23)

Power BI Desktop (2.157.879.0, August 2026 release, PBIR/enhanced-report-format
preview flags on) was later confirmed installed and opened against this
project. This section records what was found and fixed during that session,
and the unresolved blocker that ended it.

### Real defects found and fixed (each confirmed against the actual
Microsoft JSON schemas, not guessed)

1. **`country_overview.tmdl` -- invalid multi-line DAX.** The `'Risk Band
   Colour'` measure's `SWITCH(TRUE(), ...)` body started on the same line as
   `=` and continued on following lines, which TMDL's parser rejects.
   Fixed by making it fully single-line. Confirmed resolved (the exact
   parse error disappeared on reload).
2. **`dim_year` calculated table -- TOM relationship load failure**
   (`invalid column ID 254`). Root cause not fully diagnosed; since no
   visual referenced `dim_year`, the table, its three relationships, and
   `model.tmdl`'s references to it were removed rather than debugged
   further. Confirmed resolved.
3. **Power Query type-inference crash** (`'dataType' argument cannot be
   null`) during Desktop's `DetectTablesWithMissingData` step, triggered by
   columns that are entirely null in the current data (e.g.
   `run_metadata.image_ref`). Fixed by adding an explicit
   `Table.TransformColumnTypes` step to every table's M partition. Confirmed
   resolved.
4. **M language syntax error** -- the type-inference fix above used
   `{#"col", type text}`, but `#"identifier"` in M is a *quoted identifier*
   (a variable/step reference), not a string literal, so Desktop tried to
   resolve every column name as an undefined variable ("name wasn't
   recognized"). Fixed by changing every `{#"col", ...}` to `{"col", ...}`
   across all 8 table files. Confirmed resolved -- model loads cleanly, all
   8 tables visible with no warnings.
5. **`pages.json` used a schema URL that does not exist**
   (`.../definition/pages/1.4.0/schema.json` -- confirmed 404). The correct
   schema, confirmed by fetching it directly, is
   `.../definition/pagesMetadata/1.0.0/schema.json`. Fixed.
6. **`report.json` used a schema URL that does not exist**
   (`.../definition/report/1.4.0/schema.json` -- confirmed 404). The correct
   schema is `.../definition/report/1.0.0/schema.json`, under which
   `themeCollection` is a **required** field -- the opposite of an earlier
   failed fix attempt (in this same session) that removed it. Restored with
   a verified real Microsoft base theme (`CY24SU10`, `SharedResources`).
   Fixed.
7. **`definition.pbir` and `definition.pbism` were both missing the
   required `$schema` field entirely** (confirmed against the real
   `definitionProperties` schemas for report and semantic-model
   respectively). Fixed.
8. A nonstandard `definition/version.json` file was removed on the
   (incorrect) belief it wasn't part of the real PBIR spec, based on
   secondary web sources. **Desktop's own loader proved this wrong**
   (`Cannot find file 'version.json'`, thrown from
   `ExplorationSerializer.GetFileData(..., isRequired: true)`) -- it is a
   real, required file. Restored immediately once Desktop's own error
   contradicted the earlier (incorrect) research-based assumption.

### Unresolved blocker (session ended here)

After fixes 1-7 above, the semantic model loads cleanly (all 8 tables,
all measures, no Power Query warnings), but **the report canvas itself
fails to render** with:

```
JS Error Message: Cannot read properties of undefined (reading 'visualContainers')
Component: DesktopExplorationComponent / onExplorationActivated
via ViewSelectionService.onViewSelectionChanged
```

Diagnostic isolation performed (each confirmed by an identical, unchanged
error across reloads):

- Removing the one `filledMap` visual (replacing with `barChart`) -- no
  change.
- Removing the unverified `themeCollection.baseTheme` reference -- no
  change (and was later found to be required anyway, see fix #6).
- Emptying the Executive Overview page's `visuals/` folder entirely (after
  the schema fixes above were in place) -- **identical crash with zero
  visuals present**, ruling out visual content entirely.
- Changing `pages.json`'s `activePageName` from `ExecutiveOverview` to
  `CountryProfile` -- **identical crash**, ruling out that specific page
  (or its identity) as the cause. The crash follows whichever page is set
  active on load, independent of that page's content.

This means the defect is not in any page's or visual's content -- it is
somewhere in the report/model activation path that current diagnostics
have not isolated further. All JSON files that could be checked against a
real, fetched Microsoft schema have been checked and are valid; the
remaining candidates (an undiagnosed Desktop-side PBIR/TMDL
interoperability issue, a schema-version mismatch not yet identified, or a
defect in a file/mechanism not covered by the public schemas) were not
reached before this validation session was paused.

**Working tree status**: all fixes above (1-8) are applied on disk but
**not committed**. `git status` shows these as uncommitted changes against
the `39a7af6` baseline.

## Status

**M9 BLOCKED, NOT COMPLETE. The native PBIP/TMDL/PBIR project has real,
confirmed authoring defects that were found and fixed live against Power BI
Desktop across nine debugging rounds, and the semantic model now loads
cleanly -- but the report canvas itself still fails to render with an
unresolved `visualContainers` activation error, independent of page/visual
content. No page has been confirmed to render, no screenshots exist, and
no interaction/measure/production-semantics validation was possible. Per
the project's stated criterion, M9 is explicitly NOT marked complete.
Live Desktop debugging was paused by the user's direction on 2026-08-23 to
evaluate a different delivery path (a web-based dashboard) instead of
continuing to chase this defect.**
