# Screenshots

No screenshots are committed here. Power BI Desktop is not installed in this
development environment (`docs/powerbi/native_report_status.md` documents the
detection check), so no automated or manual capture could be performed --
faking screenshots is explicitly out of scope for this project's honesty
rules.

## What to export once the project is opened

After validating `powerbi/ClimateTransitionRisk.pbip` in Power BI Desktop
(see `docs/powerbi/native_report_status.md` for the exact opening/repair
steps), export one PNG or PDF page per report page and save it here using
these exact filenames so future documentation/links resolve:

```text
docs/powerbi/screenshots/executive_overview.png
docs/powerbi/screenshots/country_profile.png
docs/powerbi/screenshots/energy_transition.png
docs/powerbi/screenshots/scenario_explorer.png
docs/powerbi/screenshots/model_evidence.png
docs/powerbi/screenshots/structural_diagnostics.png
docs/powerbi/screenshots/provenance.png
```

Use File > Export > Export to PDF (all 7 pages, one PDF) or capture each
page individually with File > Export > Export current view. `*.png` files
in this folder are gitignored by design (`.gitignore`): treat them as local
portfolio artifacts, not repository content, consistent with how the PBIX
itself is distributed (see `docs/powerbi/portfolio_story.md`).
