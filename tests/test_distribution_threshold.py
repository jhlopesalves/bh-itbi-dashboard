"""A pooled sufficient sample must not validate an unstable type-specific median."""

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
