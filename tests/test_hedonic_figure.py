"""Ribbon boundaries for composition terms that reverse sign."""

import numpy as np
import pandas as pd

from bh_itbi.figures import band_traces, hedonic_figure, ribbon_grid
from bh_itbi.models import COMPOSITION_TERMS
from bh_itbi.text.models import HEDONIC_INDEX_TRACE_NAME, HEDONIC_RAW_TRACE_NAME
from bh_itbi.text.shared import COMPOSITION_LABELS
from bh_itbi.theme import COMPOSITION_HUES, SURFACE, composition_tint


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


def test_hedonic_figure_groups_index_bounds_and_composition_components() -> None:
    dates = pd.date_range("2020-01-01", periods=3, freq="QS")
    table = pd.DataFrame(
        {
            "date": dates,
            "hedonic_index": [100.0, 104.0, 110.0],
            "lower": [100.0, 101.0, 106.0],
            "upper": [100.0, 107.0, 114.0],
            "raw_geometric_mean": [100.0, 102.0, 105.0],
            "neighbourhood": [0.0, 0.04, -0.05],
            "area": [0.0, -0.02, 0.02],
            "age_band": [0.0, -0.05, -0.08],
            "property_type": [0.0, 0.01, 0.005],
        }
    )
    fig = hedonic_figure(table)

    assert fig.layout.showlegend is True
    assert (
        fig.layout.legend.groupclick,
        fig.layout.legend.itemclick,
        fig.layout.legend.itemdoubleclick,
    ) == ("togglegroup", "toggle", "toggleothers")
    assert not fig.layout.annotations
    assert fig.layout.margin.r == 22

    visible_legend = sorted(
        (trace for trace in fig.data if trace.showlegend is not False),
        key=lambda trace: trace.legendrank,
    )
    expected_groups = ["age_band", "neighbourhood", "area", "property_type"]
    assert [trace.name for trace in visible_legend] == [
        HEDONIC_INDEX_TRACE_NAME,
        HEDONIC_RAW_TRACE_NAME,
        *(COMPOSITION_LABELS[group] for group in expected_groups),
    ]
    assert [trace.legendgroup for trace in visible_legend] == [
        "hedonic_index",
        None,
        *expected_groups,
    ]

    hedonic_group = [trace for trace in fig.data if trace.legendgroup == "hedonic_index"]
    assert len(hedonic_group) == 3
    assert sum(trace.showlegend is not False for trace in hedonic_group) == 1

    for group in COMPOSITION_TERMS:
        grouped = [trace for trace in fig.data if trace.legendgroup == group]
        swatches = [trace for trace in grouped if trace.showlegend is not False]
        polygons = [trace for trace in grouped if trace.fill == "toself"]
        separators = [trace for trace in grouped if trace.line.color == SURFACE]
        assert len(swatches) == 1
        assert swatches[0].marker.symbol == "square"
        assert swatches[0].marker.color == COMPOSITION_HUES[group]
        assert polygons and all(
            trace.fillcolor == composition_tint(COMPOSITION_HUES[group])
            and trace.showlegend is False
            for trace in polygons
        )
        assert len(separators) == len(polygons)
        assert all(trace.showlegend is False for trace in separators)
