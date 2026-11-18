"""Exact price quantiles and eligibility for the neighbourhood comparison."""

import numpy as np
import pandas as pd
import pytest

from bh_itbi.analysis import neighbourhood_price_distributions, silverman_bandwidth
from bh_itbi.figures import trim_log_density


def test_silverman_bandwidth_matches_sample_iqr() -> None:
    # For 0…4 the sample SD is sqrt(2.5); IQR / 1.34 is the smaller spread.
    expected = 0.9 * (2 / 1.34) * 5 ** (-1 / 5)
    assert silverman_bandwidth(np.arange(5, dtype=float)) == pytest.approx(expected)


def test_shared_grid_and_exact_quantiles_at_eligibility_boundaries() -> None:
    samples = {
        "EXCLUDED": np.linspace(3000, 6000, 14),
        "SUMMARY": np.linspace(2000, 8000, 49),
        "RIDGE": np.linspace(4000, 12_000, 50),
        "CHEAPER": np.linspace(1500, 5000, 85),
    }
    column = "price_per_m2_brl_real"
    frame = pd.DataFrame(
        [
            {"neighbourhood": name, column: price}
            for name, prices in samples.items()
            for price in prices
        ]
    )
    grid, rows = neighbourhood_price_distributions(frame)
    assert [row.neighbourhood for row in rows] == ["RIDGE", "SUMMARY", "CHEAPER"]
    assert grid.size == 512
    for row in rows:
        prices = samples[row.neighbourhood]
        assert row.n == len(prices)
        assert row.quantiles == pytest.approx(
            pd.Series(prices).quantile([0.10, 0.25, 0.50, 0.75, 0.90])
        )
        if row.n == 49:
            assert row.density is None
        else:
            assert row.density is not None
            assert row.bandwidth is not None
            assert grid[0] <= np.log(prices.min()) - 3 * row.bandwidth
            assert grid[-1] >= np.log(prices.max()) + 3 * row.bandwidth
            assert np.trapezoid(row.density, grid) == pytest.approx(1, abs=1e-3)


def test_equal_prices_preserve_an_interval_when_bandwidth_is_zero() -> None:
    frame = pd.DataFrame({"neighbourhood": ["BAIRRO"] * 50, "price_per_m2_brl_real": 8000.0})
    grid, rows = neighbourhood_price_distributions(frame)
    assert not grid.size
    assert rows[0].quantiles == (8000, 8000, 8000, 8000, 8000)
    assert rows[0].bandwidth == 0
    assert rows[0].density is None


def test_trim_retains_the_trough_between_price_modes() -> None:
    grid = np.arange(4, 11, dtype=float)
    density = np.array([0, 0.5, 1, 0.01, 0.8, 0.5, 0])
    prices, heights = trim_log_density(grid, density)
    np.testing.assert_allclose(np.log(prices), [4.03, 5, 6, 7, 8, 9, 9.97])
    np.testing.assert_allclose(heights, [0.015, 0.5, 1, 0.01, 0.8, 0.5, 0.015])


def test_nine_eligible_neighbourhoods_use_only_exact_quantiles() -> None:
    frame = pd.DataFrame(
        {
            "neighbourhood": np.repeat([f"BAIRRO {i}" for i in range(9)], 50),
            "price_per_m2_brl_real": np.tile(np.linspace(4000, 8000, 50), 9),
        }
    )
    grid, rows = neighbourhood_price_distributions(frame)
    assert len(rows) == 9
    assert not grid.size
    assert all(row.bandwidth is None and row.density is None for row in rows)
    assert all(row.quantiles[2] == 6000 for row in rows)
