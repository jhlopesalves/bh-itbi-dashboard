"""Plotly histogram of all positive observations on a shared logarithmic axis."""

from itertools import pairwise

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from bh_itbi.config import DISTRIBUTION_BINS, DISTRIBUTION_MINIMUM, DISTRIBUTION_TICK_LIMIT
from bh_itbi.formatting import compact_number, currency
from bh_itbi.text.overview import (
    DISTRIBUTION_EMPTY_MESSAGE,
    DISTRIBUTION_HOVER,
    LOG_CURRENCY_AXIS_TITLE,
)
from bh_itbi.text.shared import (
    TRANSACTIONS_AXIS_TITLE,
    TYPE_LABELS,
)
from bh_itbi.theme import TYPE_STYLES, empty_figure, themed


def distribution_figure(frame: pd.DataFrame, column: str) -> go.Figure:
    """Shared geometric bins show every positive value without tail trimming."""
    values = frame.loc[frame[column].gt(0), ["property_type", column]]
    if len(values) < DISTRIBUTION_MINIMUM:
        return empty_figure(DISTRIBUTION_EMPTY_MESSAGE, 330)
    low, high = float(values[column].min()), float(values[column].max())
    if low == high:
        low, high = low * 0.9, high * 1.1
    edges = np.geomspace(low, high, DISTRIBUTION_BINS + 1)
    centres = np.sqrt(edges[:-1] * edges[1:])
    widths = np.diff(edges) * 0.92
    bins = [[currency(a), currency(b)] for a, b in pairwise(edges)]
    fig = go.Figure()
    for property_type, label in TYPE_LABELS.items():
        subset = values.loc[values["property_type"].eq(property_type), column]
        if subset.empty:
            continue
        counts, _ = np.histogram(subset, bins=edges)
        colour = TYPE_STYLES[property_type]["line"]["color"]
        fig.add_trace(
            go.Bar(
                x=centres,
                y=counts,
                width=widths,
                marker={"color": colour, "line": {"width": 0}},
                opacity=0.75,
                name=label,
                customdata=bins,
                hovertemplate=DISTRIBUTION_HOVER,
            )
        )
        if len(subset) >= DISTRIBUTION_MINIMUM:
            fig.add_vline(
                x=subset.median(),
                line={"color": colour, "dash": "dot", "width": 1.5},
            )
    themed(fig, height=330)
    fig.update_layout(
        barmode="overlay",
        bargap=0,
        margin={"l": 50, "r": 18, "t": 12},
    )
    ticks = [
        multiplier * 10.0**exponent
        for exponent in range(int(np.floor(np.log10(low))), int(np.ceil(np.log10(high))) + 1)
        for multiplier in (1, 2, 5)
        if low <= multiplier * 10.0**exponent <= high
    ]
    if len(ticks) > DISTRIBUTION_TICK_LIMIT:
        indexes = np.linspace(0, len(ticks) - 1, DISTRIBUTION_TICK_LIMIT, dtype=int)
        ticks = [ticks[i] for i in indexes]
    fig.update_xaxes(
        type="log",
        title_text=LOG_CURRENCY_AXIS_TITLE,
        tickmode="array",
        tickvals=ticks,
        ticktext=[compact_number(tick) for tick in ticks],
    )
    fig.update_yaxes(title_text=TRANSACTIONS_AXIS_TITLE, rangemode="tozero", tickformat=",.0f")
    return fig
