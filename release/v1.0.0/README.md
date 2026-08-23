# v1.0.0 release evidence bundle

Machine-readable evidence for the v1.0.0 release, generated and verified
against real production artifacts (never hand-typed placeholder values):

- `release-manifest.json` — the release's key facts: Git SHA, runtime image
  tags/digests, production run ID, data snapshot IDs, active analytical
  versions, deployment URLs.
- `data-revision-summary.json` — comparison of the production run's source
  snapshots against a fresh live fetch.
- `reproducibility-summary.json` — frozen-input and cross-environment
  reproducibility test results.
- `validation-summary.json` — final Python/frontend/Terraform gate results
  at release time.

Validate this bundle's self-consistency with:

```bash
uv run python scripts/validate_release.py release/v1.0.0/
```

See `docs/scope-v1.md` for the release scope, `docs/reproducibility.md` and
`docs/governance.md` for the full narrative behind these summaries.
