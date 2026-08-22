from __future__ import annotations

from climate_risk.contracts.models import QualitySeverity
from climate_risk.quality.rules import load_rule_registry, publish_gate


def test_rule_registry_loads_and_has_expected_severities() -> None:
    rules = load_rule_registry()
    assert rules["DQ-PANEL-010"].severity == QualitySeverity.FATAL
    assert rules["DQ-GDP-020"].severity == QualitySeverity.WARN


def test_publish_gate_blocks_on_fatal() -> None:
    may_publish, reason = publish_gate({QualitySeverity.FATAL: 1})
    assert may_publish is False
    assert reason is not None


def test_publish_gate_allows_warn_only() -> None:
    may_publish, reason = publish_gate({QualitySeverity.WARN: 5})
    assert may_publish is True
    assert reason is None
