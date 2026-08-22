from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from climate_risk.features.decoupling import add_growth_rates, compute_decoupling


@pytest.fixture
def synthetic_panel() -> pd.DataFrame:
    years = list(range(2000, 2021))
    rng = np.random.default_rng(0)
    gdp = 1000 * (1.03 ** np.arange(len(years))) * (1 + rng.normal(0, 0.01, len(years)))
    co2 = 500 * (1.01 ** np.arange(len(years))) * (1 + rng.normal(0, 0.01, len(years)))
    return pd.DataFrame(
        {
            "country_iso3": ["ZZZ"] * len(years),
            "year": years,
            "real_gdp": gdp,
            "co2_mt": co2,
        }
    )


def test_growth_rates_first_year_is_nan(synthetic_panel: pd.DataFrame) -> None:
    panel = add_growth_rates(synthetic_panel)
    first_row = panel.iloc[0]
    assert pd.isna(first_row["gdp_growth_yoy"])
    assert pd.isna(first_row["co2_growth_yoy"])

    expected = (panel.iloc[1]["real_gdp"] / panel.iloc[0]["real_gdp"]) - 1
    assert panel.iloc[1]["gdp_growth_yoy"] == pytest.approx(expected)


def test_decoupling_elasticity_reflects_slower_co2_growth(synthetic_panel: pd.DataFrame) -> None:
    result = compute_decoupling(synthetic_panel, country_iso3="ZZZ")
    assert result is not None
    assert result.sample_size == 21
    assert result.year_start == 2000
    assert result.year_end == 2020
    # GDP grows ~3%/yr, CO2 ~1%/yr -> relative decoupling, elasticity well below 1
    assert result.elasticity is not None
    assert 0 < result.elasticity < 1


def test_decoupling_none_below_min_observations() -> None:
    tiny = pd.DataFrame(
        {
            "country_iso3": ["ZZZ"] * 3,
            "year": [2018, 2019, 2020],
            "real_gdp": [100.0, 105.0, 110.0],
            "co2_mt": [50.0, 51.0, 52.0],
        }
    )
    assert compute_decoupling(tiny, country_iso3="ZZZ") is None
