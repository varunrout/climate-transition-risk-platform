"""Quality rule registry loader (08_data_quality_and_validation.md section 4)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from climate_risk.config.loader import CONFIG_DIR
from climate_risk.contracts.models import QualitySeverity


class QualityRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str
    description: str
    severity: QualitySeverity


def load_rule_registry(path: Path | None = None) -> dict[str, QualityRule]:
    path = path or (CONFIG_DIR / "quality_rules.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {
        rule_id: QualityRule(rule_id=rule_id, **entry) for rule_id, entry in raw["rules"].items()
    }


def publish_gate(events_by_severity: dict[QualitySeverity, int]) -> tuple[bool, str | None]:
    """Fail-closed publish decision per 08_data_quality_and_validation.md section 11.

    Returns (may_publish, blocking_reason).
    """
    fatal = events_by_severity.get(QualitySeverity.FATAL, 0)
    if fatal > 0:
        return False, f"{fatal} FATAL quality event(s) present"
    return True, None
