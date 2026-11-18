"""Period styles and axis bounds for filtered distance medians."""

import numpy as np
import pandas as pd
import pytest

from bh_itbi.figures import distance_figure


def test_distance_styles_follow_periods_when_the_first_period_is_absent() -> None:
    table = pd.DataFrame(
        [
            ("2022–2025", 0.5, 4700.0, 60),
            ("2019–2021", 0.5, 3520.0, 100),
            ("2019–2021", 1.5, np.nan, 20),
        ],
        columns=["period", "band_km", "median", "n"],
    )
    figure = distance_figure(table)
    rose, plum = figure.data
    assert (rose.name, rose.line.color, rose.line.width, rose.marker.size) == (
        "2019–2021",
        "#c94f7c",
        2.0,
        7.0,
    )
    assert (plum.name, plum.line.color, plum.line.width, plum.marker.size) == (
        "2022–2025",
        "#5e2a6e",
        2.8,
        8.0,
    )
    assert np.isnan(rose.y[1])
    assert figure.layout.yaxis.range == (3000, 5000)
    assert figure.layout.yaxis.dtick == 500


def test_distance_figure_has_a_nonzero_span_and_legend_with_one_point() -> None:
    table = pd.DataFrame(
        [("2016–2018", 1.5, 4500.0, 50)], columns=["period", "band_km", "median", "n"]
    )
    figure = distance_figure(table)
    assert figure.layout.yaxis.range == (4000, 5000)
    assert figure.layout.showlegend is True
    table["period"] = "unrecognised"
    with pytest.raises(ValueError, match="unrecognised"):
        distance_figure(table)
