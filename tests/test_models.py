"""Composition accounting on synthetic fits with different dummy codings."""

import numpy as np
import pandas as pd

from bh_itbi.models import COMPOSITION_TERMS, fit_hedonic


def test_composition_is_invariant_to_neighbourhood_reference() -> None:
    rng = np.random.default_rng(42)
    quarter = np.repeat(np.arange(3), 160)
    n = len(quarter)
    savassi = rng.random(n) < 0.25 + 0.25 * quarter
    older = rng.random(n) < 0.30 + 0.15 * quarter
    house = rng.random(n) < 0.65 - 0.15 * quarter
    log_area = 4 + 0.2 * quarter + rng.normal(0, 0.3, n)
    log_price = (
        8
        + 0.04 * quarter
        + 0.3 * savassi
        - 0.2 * older
        - 0.1 * house
        - 0.3 * log_area
        + rng.normal(0, 0.1, n)
    )
    frame = pd.DataFrame(
        {
            "year": 2016,
            "transaction_date": pd.date_range("2016-01-01", periods=3, freq="QS")[quarter],
            "neighbourhood": pd.Categorical(np.where(savassi, "SAVASSI", "LOURDES")),
            "building_age_band": np.where(older, "old", "new"),
            "property_type": np.where(house, "house", "apartment"),
            "built_area_m2": np.exp(log_area),
            "price_per_m2_brl_real": np.exp(log_price),
        }
    )
    original, _ = fit_hedonic(frame)
    frame["neighbourhood"] = frame["neighbourhood"].cat.reorder_categories(
        ["SAVASSI", "LOURDES"]
    )
    recoded, _ = fit_hedonic(frame)

    groups = list(COMPOSITION_TERMS)
    assert original.loc[2, groups].abs().gt(0.01).all()
    np.testing.assert_allclose(original[groups], recoded[groups], atol=1e-10, rtol=0)
    assert original.loc[0, groups].eq(0).all()
    assert original.loc[0, ["indice_hedonico", "media_geometrica_bruta"]].eq(100).all()
