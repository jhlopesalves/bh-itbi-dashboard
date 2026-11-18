"""Distribution figure behaviour for type-specific medians and the legend."""

from bh_itbi.data import prepare_transactions
from bh_itbi.figures import distribution_figure


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


def test_histogram_legend_is_anchored_below_the_axes(source_factory):
    source = source_factory()
    source.loc[:9, "property_type"] = "house"
    fig = distribution_figure(prepare_transactions(source), "price_per_m2_brl_real")

    assert len(fig.data) == 2
    assert fig.layout.xaxis.automargin
    assert fig.layout.margin.autoexpand is not False
    legend = fig.layout.legend
    assert (legend.yref, legend.yanchor, legend.y) == ("container", "bottom", 0)
