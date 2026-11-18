"""Age-band premiums, clustered inference and filtering boundaries."""

import os

import numpy as np
import pandas as pd
import pytest
from statsmodels.regression.linear_model import OLS

from bh_itbi.age import (
    AGE_GROUPS,
    FEW_NEIGHBOURHOODS,
    MISSING_REFERENCE,
    UNIDENTIFIED_ADJUSTMENT,
    age_premiums,
    within_neighbourhood,
)
from bh_itbi.data import load_transactions
from bh_itbi.filters import Filters, filter_transactions
from bh_itbi.urls import default_controls


@pytest.fixture
def apartments() -> pd.DataFrame:
    rng = np.random.default_rng(31)
    neighbourhood = np.repeat(np.arange(24), 48)
    n = len(neighbourhood)
    quarter = rng.integers(0, 4, n)
    newer = rng.random(n) < 0.2 + 0.02 * neighbourhood + 0.04 * quarter
    area = rng.normal(4.5 + 0.4 * newer, 0.3)
    price = (
        8
        + 0.2 * newer
        - 0.3 * area
        + 0.04 * neighbourhood
        + 0.05 * quarter
        + rng.normal(0, 0.1 + 0.01 * neighbourhood)
    )
    return pd.DataFrame(
        {
            "neighbourhood": pd.Categorical(neighbourhood),
            "building_age_band": np.where(newer, "new", "26_plus"),
            "year": 2024,
            "quarter": pd.date_range("2024-01-01", periods=4, freq="QS")[quarter],
            "property_type": "apartment",
            "built_area_m2": np.exp(area),
            "price_per_m2_brl_real": np.exp(price),
        }
    )


def test_within_slopes_and_cluster_errors_match_full_dummy_ols(
    apartments: pd.DataFrame,
) -> None:
    groups = apartments["neighbourhood"].array
    y = np.log(apartments["price_per_m2_brl_real"].to_numpy())
    quarter = pd.get_dummies(apartments["quarter"], drop_first=True)
    x = np.column_stack(
        (
            apartments["building_age_band"].eq("new"),
            np.log(apartments["built_area_m2"]),
            quarter,
        )
    )
    result = within_neighbourhood(y, x, groups)
    assert result is not None
    beta, se, intercepts = result
    dummies = pd.get_dummies(groups, drop_first=True)
    full = OLS(y, np.column_stack((x, np.ones(len(y)), dummies))).fit(
        cov_type="cluster", cov_kwds={"groups": groups.codes}
    )
    np.testing.assert_allclose(beta, full.params[: x.shape[1]], atol=1e-8, rtol=0)
    np.testing.assert_allclose(se, full.bse[: x.shape[1]], atol=1e-8, rtol=0)
    np.testing.assert_allclose(
        x @ beta + intercepts[groups.codes], full.fittedvalues, atol=1e-8
    )


def test_age_composition_is_invariant_to_neighbourhood_reference(
    apartments: pd.DataFrame,
) -> None:
    original = age_premiums(apartments).table
    band = apartments["building_age_band"]
    age = band.eq("new")
    area = np.log(apartments["built_area_m2"])
    quarters = pd.get_dummies(apartments["quarter"], drop_first=True)
    effects = original.loc["new", list(AGE_GROUPS)]
    assert effects.abs().gt(0.01).all()
    indicators = pd.get_dummies(apartments["neighbourhood"])
    for reference in (indicators.columns[0], indicators.columns[-1]):
        neighbourhoods = indicators.drop(columns=reference)
        design = np.column_stack((np.ones(len(band)), age, area, quarters, neighbourhoods))
        beta = OLS(np.log(apartments["price_per_m2_brl_real"]), design).fit().params.to_numpy()
        quarter_end = 3 + quarters.shape[1]
        components = (
            pd.DataFrame(
                {
                    "Bairro": neighbourhoods @ beta[quarter_end:],
                    "Área": area * beta[2],
                    "Trimestre": quarters @ beta[3:quarter_end],
                }
            )
            .groupby(band)
            .mean()
        )
        np.testing.assert_allclose(
            effects, components.loc["new"] - components.loc["26_plus"], atol=1e-8, rtol=0
        )


def test_band_suppression_and_few_neighbourhoods_use_same_observed_sample(
    apartments: pd.DataFrame,
) -> None:
    sample = apartments.loc[apartments["neighbourhood"].isin(range(19))].copy()
    sample.loc[sample.index[:14], "building_age_band"] = "3_10"
    sample.loc[sample.index[14], "price_per_m2_brl_real"] = 1_000_000
    sample.loc[sample.index[15], "built_area_m2"] = 0
    sample.loc[sample.index[16], "neighbourhood"] = np.nan
    premiums = age_premiums(sample)
    assert premiums.unavailable == FEW_NEIGHBOURHOODS
    assert premiums.excluded["3_10"] == 14
    assert premiums.neighbourhoods == 19
    assert "adjusted" not in premiums.table
    retained = sample.iloc[14:].drop(sample.index[15:17])
    means = np.exp(
        np.log(retained["price_per_m2_brl_real"]).groupby(retained["building_age_band"]).mean()
    )
    assert premiums.table["n"].sum() == len(retained)
    assert premiums.table.loc["new", "observed"] == pytest.approx(
        np.log(means["new"] / means["26_plus"])
    )


def test_missing_reference_and_unidentified_adjustment(apartments: pd.DataFrame) -> None:
    without_reference = age_premiums(apartments.loc[apartments["building_age_band"].eq("new")])
    assert without_reference.table.empty
    assert without_reference.unavailable == MISSING_REFERENCE
    assert without_reference.excluded["26_plus"] == 0

    apartments["built_area_m2"] = 100.0
    unidentified = age_premiums(apartments)
    assert unidentified.unavailable == UNIDENTIFIED_ADJUSTMENT
    assert "adjusted" not in unidentified.table


@pytest.mark.skipif(
    os.environ.get("BH_ITBI_REAL_DATA") != "1",
    reason="Run after main.py prepare with BH_ITBI_REAL_DATA=1",
)
def test_default_age_decomposition_identity_on_real_data() -> None:
    property_type, years, neighbourhoods, *_ = default_controls()
    selection = Filters.from_controls(property_type, years, neighbourhoods)
    data = filter_transactions(load_transactions(allow_prepare=False), selection)
    premiums = age_premiums(data)
    assert premiums.unavailable is None
    assert len(premiums.table) == 4
    error = (
        premiums.table["observed"]
        - premiums.table["adjusted"]
        - premiums.table[list(AGE_GROUPS)].sum(axis=1)
    )
    assert error.abs().max() < 1e-8
