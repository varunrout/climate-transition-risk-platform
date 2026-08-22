from __future__ import annotations

from climate_risk.research.m6_panel import feature_catalog


def test_feature_catalog_has_unique_names() -> None:
    catalog = feature_catalog()
    names = [f.feature_name for f in catalog]
    assert len(names) == len(set(names))


def test_feature_catalog_directions_are_valid() -> None:
    catalog = feature_catalog()
    for entry in catalog:
        assert entry.directionality in {"higher_is_higher_risk", "higher_is_lower_risk"}
        assert entry.source_columns
        assert entry.unit
        assert entry.transformation


def test_feature_catalog_is_a_fresh_copy_each_call() -> None:
    a = feature_catalog()
    b = feature_catalog()
    assert a is not b
    a.pop()
    assert len(feature_catalog()) == len(b)
