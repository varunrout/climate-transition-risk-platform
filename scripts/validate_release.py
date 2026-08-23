#!/usr/bin/env python3
"""Validate a release evidence bundle's self-consistency.

Usage: uv run python scripts/validate_release.py release/v1.0.0/

Checks the bundle is internally consistent and free of anything that
shouldn't be published -- it does not re-run the pipeline or re-verify
artifact bytes against Azure; it validates the bundle's own claims are
well-formed and match this project's known-good constants.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

EXPECTED_RELEASE_VERSION = "1.0.0"
EXPECTED_SCORE_VERSION = "v2_energy"
EXPECTED_SCENARIO_METHOD = "empirical_bootstrap_v1"
EXPECTED_COUNTRY_COUNT = 19
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SNAPSHOT_ID_RE = re.compile(r"^[0-9a-f]{16}$")
EXPECTED_URL_PREFIXES = (
    "https://varunrout.github.io/climate-transition-risk-platform",
    "https://ca-climate-risk-dev-api.ambitiousbush-97a2aedf.uksouth.azurecontainerapps.io",
)
# Field names that would be a real problem if a plausible-looking secret value
# ever showed up under them -- deliberately anchored to how a *credential*
# field is actually named (password/client_secret/api_key/...), not a bare
# substring match on words like "secret" or "token", which also appear in
# entirely legitimate fields describing this project's own secret-scanning
# process (e.g. "credential_leak_scan_git_history"). This is a name-based
# tripwire, not a substitute for the repository-wide secret scan already run
# as part of the release security review -- see docs/governance.md.
SECRET_LIKE_KEYS = re.compile(
    r"^(password|client[_-]?secret|api[_-]?key|connection[_-]?string|sas[_-]?token|account[_-]?key)$"
    r"|(_password|_client_secret|_api_key|_connection_string|_sas_token|_account_key)$",
    re.IGNORECASE,
)


class ValidationError(Exception):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def check_no_secret_like_fields(obj: object, path: str = "$") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if SECRET_LIKE_KEYS.search(key):
                raise ValidationError(f"secret-like field name at {path}.{key}")
            check_no_secret_like_fields(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            check_no_secret_like_fields(item, f"{path}[{i}]")


def validate_release_manifest(data: dict[str, Any]) -> list[str]:
    errors = []
    try:
        check(
            data.get("release_version") == EXPECTED_RELEASE_VERSION, "release_version must be 1.0.0"
        )
        sha = data.get("release_git_sha", "")
        check(
            bool(GIT_SHA_RE.match(sha)), f"release_git_sha is not a valid 40-hex Git SHA: {sha!r}"
        )
        for field in ("runtime_pipeline_source_sha", "runtime_api_source_sha"):
            val = data.get(field, "")
            check(bool(GIT_SHA_RE.match(val)), f"{field} is not a valid 40-hex Git SHA: {val!r}")
        for field in ("pipeline_image_digest", "api_image_digest"):
            val = data.get(field, "")
            check(
                bool(SHA256_RE.match(val)),
                f"{field} is not a valid sha256:<64-hex> digest: {val!r}",
            )
        check(
            data.get("active_score_version") == EXPECTED_SCORE_VERSION,
            "active_score_version must be v2_energy",
        )
        check(
            data.get("active_scenario_method") == EXPECTED_SCENARIO_METHOD,
            "active_scenario_method must be empirical_bootstrap_v1",
        )
        check(data.get("country_count") == EXPECTED_COUNTRY_COUNT, "country_count must be 19")
        for source, snap_id in data.get("source_snapshot_ids", {}).items():
            check(
                bool(SNAPSHOT_ID_RE.match(snap_id)),
                f"snapshot id for {source} is malformed: {snap_id!r}",
            )
        for name, url in data.get("deployment_urls", {}).items():
            check(
                any(url.startswith(p) for p in EXPECTED_URL_PREFIXES),
                f"deployment url {name}={url!r} does not match an expected prefix",
            )
    except ValidationError as exc:
        errors.append(str(exc))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_release.py <release-dir>", file=sys.stderr)
        return 2
    release_dir = Path(sys.argv[1])
    manifest_path = release_dir / "release-manifest.json"
    check(manifest_path.exists(), f"missing {manifest_path}")

    all_errors: list[str] = []
    for json_path in sorted(release_dir.glob("*.json")):
        data = json.loads(json_path.read_text())
        try:
            check_no_secret_like_fields(data)
        except ValidationError as exc:
            all_errors.append(f"{json_path.name}: {exc}")

    manifest = json.loads(manifest_path.read_text())
    all_errors.extend(f"release-manifest.json: {e}" for e in validate_release_manifest(manifest))

    if all_errors:
        print(f"FAILED: {len(all_errors)} issue(s)", file=sys.stderr)
        for e in all_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"OK: {manifest_path.parent} is self-consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
