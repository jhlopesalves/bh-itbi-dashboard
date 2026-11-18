"""Ribbon boundaries for composition terms that reverse sign."""

import numpy as np
import pandas as pd

from bh_itbi.figures import band_traces, ribbon_grid
from bh_itbi.theme import COMPOSITION_HUES


def test_ribbon_bands_close_at_interpolated_sign_changes() -> None:
    dates = pd.date_range("2020-01-01", periods=3, freq="QS")
    table = pd.DataFrame(
        {"date": dates, "hedonic_index": [100, 105, 100], "neighbourhood": [0.1, -0.1, 0.1]}
    )
    grid, adjusted, contributions = ribbon_grid(table, ["neighbourhood"])
    first_zero = dates[0] + (dates[1] - dates[0]) / 2
    second_zero = dates[1] + (dates[2] - dates[1]) / 2
    assert grid.tolist() == [dates[0], first_zero, dates[1], second_zero, dates[2]]
    values = contributions["neighbourhood"]
    np.testing.assert_array_equal(values, [0.1, 0, -0.1, 0, 0.1])

    negative_fill, negative_edge = band_traces(
        grid, adjusted, adjusted + values.clip(max=0), COMPOSITION_HUES["neighbourhood"]
    )
    assert negative_edge.x == (first_zero, dates[1], second_zero, None)
    assert negative_fill.y[0] == negative_fill.y[-2]

    _, positive_edge = band_traces(
        grid, adjusted, adjusted + values.clip(min=0), COMPOSITION_HUES["neighbourhood"]
    )
    assert positive_edge.x == (dates[0], first_zero, None, second_zero, dates[2], None)
