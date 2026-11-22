"""Distribution figure behaviour for type-specific medians and the legend."""

import numpy as np

from bh_itbi.config import DISTRIBUTION_BINS
from bh_itbi.data import prepare_transactions
from bh_itbi.figures import distribution_figure
from bh_itbi.text.shared import TYPE_LABELS
from bh_itbi.theme import TEAL, TYPE_STYLES


def test_sparse_type_keeps_counts_but_does_not_gain_a_median_line(source_factory):
    source = source_factory(6)
    source.loc[0, "property_type"] = "house"
    frame = prepare_transactions(source)
    fig = distribution_figure(frame, "price_per_m2_brl_real")
    assert sum(sum(trace.y) for trace in fig.data) == 6
    assert len(fig.layout.shapes) == 1
    assert (
        fig.layout.shapes[0].x0
        == frame.loc[frame["property_type"].eq("apartment"), "price_per_m2_brl_real"].median()
    )
    assert fig.layout.shapes[0].line.color == TEAL
    assert fig.layout.shapes[0].line.dash == "dot"
    assert fig.layout.shapes[0].legendgroup == "apartment"
    assert [trace.legendgroup for trace in fig.data] == ["apartment", "house"]


def test_histogram_legend_is_anchored_below_the_axes(source_factory):
    source = source_factory()
    source.loc[:9, "property_type"] = "house"
    fig = distribution_figure(prepare_transactions(source), "price_per_m2_brl_real")

    assert len(fig.data) == 2
    assert fig.layout.showlegend is True
    assert fig.layout.xaxis.automargin
    assert fig.layout.margin.autoexpand is not False
    legend = fig.layout.legend
    assert (legend.xref, legend.xanchor, legend.x) == ("container", "left", 0)
    assert (legend.yref, legend.yanchor, legend.y) == ("container", "bottom", 0)
    assert (legend.groupclick, legend.itemclick, legend.itemdoubleclick) == (
        "togglegroup",
        "toggle",
        "toggleothers",
    )
    assert [shape.legendgroup for shape in fig.layout.shapes] == ["apartment", "house"]


def test_overlapping_bars_keep_geometric_bins_and_counts_for_each_type(source_factory):
    source = source_factory()
    source.loc[:9, "property_type"] = "house"
    frame = prepare_transactions(source)
    column = "price_per_m2_brl_real"
    frame.loc[0, column] = 463865.91
    edges = np.geomspace(frame[column].min(), frame[column].max(), DISTRIBUTION_BINS + 1)
    fig = distribution_figure(frame, column)
    assert (fig.layout.barmode, fig.layout.xaxis.type) == ("overlay", "log")
    for trace, (kind, label) in zip(fig.data, TYPE_LABELS.items(), strict=True):
        counts, _ = np.histogram(frame.loc[frame["property_type"].eq(kind), column], bins=edges)
        assert (trace.type, trace.name, trace.opacity) == ("bar", label, 0.75)
        assert trace.marker.color == TYPE_STYLES[kind]["line"]["color"]
        np.testing.assert_array_equal(trace.x, np.sqrt(edges[:-1] * edges[1:]))
        np.testing.assert_array_equal(trace.width, np.diff(edges) * 0.92)
        np.testing.assert_array_equal(trace.y, counts)
