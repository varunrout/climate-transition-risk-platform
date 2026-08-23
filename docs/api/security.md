# Security

## Read-only guarantee

Every route is `GET`. There are no `POST`/`PUT`/`PATCH`/`DELETE` business
endpoints anywhere in `climate_risk.api` -- no score recalculation, no
model execution, no data upload, no admin mutation, no job triggers.
`tests/integration/test_api.py::test_no_mutation_routes` asserts this.

## What is never returned

The API can only ever expose fields that survive
`climate_risk.bi.web_publish.RUN_METADATA_SAFE_FIELDS` -- the same
safelist the public web dashboard's data bundle is built through (ADR
0017). Startup validation (`contracts.md`) actively rejects a bundle
whose `run-metadata.json` contains any field outside that list, so this
isn't just a convention -- an accidental leak fails the API's own startup,
not just a code-review miss.

Never returned: storage account keys, SAS tokens, connection strings,
access tokens, Azure tenant/subscription IDs, managed identity client
IDs, or local filesystem paths (`transition_silver_path` /
`energy_silver_path` are lake-relative paths, not secrets, but are still
excluded from the safelist as unnecessary for the product).

Safe provenance fields that *are* returned (`GET /api/v1/meta`,
`.../provenance`): Git SHA, container image digest, run ID, active
score/component/scenario versions, source data-snapshot IDs.

`tests/integration/test_api.py::test_no_secret_like_fields_anywhere_in_meta`
greps the `/api/v1/meta` response for a list of secret-like substrings as
a blunt but effective regression guard.

## CORS

`allow_origins=["*"]`, `allow_credentials=False`, `allow_methods=["GET"]`.

This is a deliberate, documented choice, not an oversight: the API is a
public, unauthenticated, read-only service serving already-public
analytical output (no PII, no per-user data, no session state). A
wildcard origin with credentials disabled cannot be used to exfiltrate
authenticated data from another origin, because there is no
authenticated data here to exfiltrate -- every response is identical
regardless of who asks. `allow_credentials=False` also means this
configuration could not be silently escalated into a credentialed
wildcard (a genuinely dangerous CORS misconfiguration) without an
explicit code change.

## Azure access: managed identity only

Production Azure access uses a **dedicated, least-privilege user-assigned
managed identity** (`id-climate-risk-api`), separate from the pipeline
job's identity:

| Identity | Role | Scope |
|---|---|---|
| `id-climate-risk-job` (existing, pipeline) | Storage Blob Data **Contributor** | storage account |
| `id-climate-risk-api` (new, this milestone) | Storage Blob Data **Reader** | storage account |

The API identity cannot write to the lake even if the API code had a bug
that tried to -- it is genuinely read-only at the Azure RBAC layer, not
just by application convention. No API keys, SAS tokens, or connection
strings are used or stored anywhere; `climate_risk.storage.azure`
resolves `ManagedIdentityCredential(client_id=...)` from the
`AZURE_CLIENT_ID` environment variable (a non-secret identifier, safe as
a plain env var -- the same pattern the pipeline job already uses). No
token is ever logged.

## Abuse posture

No paid API gateway, no rate-limiting infrastructure. Scoped-down instead:
bounded response sizes (`limit`/`offset` with hard per-endpoint caps --
19 for rankings, since that's the entire covered-country count; 100 for
the country catalogue; 500 for backtests), no arbitrary filter
expressions (every query parameter is typed and validated by Pydantic,
never string-interpolated into anything), no user-provided code
execution, no path traversal (ISO3 codes are matched against an in-memory
dict key, never used to construct a filesystem path).
Production-grade commercial abuse protection (WAF, geo-blocking, request
throttling) is explicitly out of scope for a small public portfolio API
-- documented here rather than silently absent.
