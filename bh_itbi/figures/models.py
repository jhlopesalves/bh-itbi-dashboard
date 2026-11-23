"""Draw the hedonic composition ribbon and adjusted neighbourhood patterns."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from bh_itbi.config import INDEX_BASE, PATTERN_ORDER, PATTERN_PERIODS
from bh_itbi.formatting import composition_number, number, quarter_label
from bh_itbi.models import COMPOSITION_TERMS, PreparedModels
from bh_itbi.text.models import (
    HEDONIC_INDEX_TRACE_NAME,
    HEDONIC_RAW_TRACE_NAME,
    PATTERN_CENTRE_HOVER,
    PATTERN_MEMBER_HOVER,
    hedonic_hover,
)
from bh_itbi.text.shared import (
    COMPOSITION_LABELS,
)
from bh_itbi.theme import (
    AXIS,
    COMPOSITION_HUES,
    GRID,
    INK,
    MUTED,
    PATTERN_BORDERLINE,
    PATTERN_COLOURS,
    PATTERN_FIGURE_HEIGHT,
    REFERENCE,
    SURFACE,
    TEAL,
    composition_tint,
    padded_price_range,
    themed,
)


def ribbon_grid(
    table: pd.DataFrame, groups: Sequence[str]
) -> tuple[pd.DatetimeIndex, np.ndarray, dict[str, np.ndarray]]:
    """Interpolate in log space on a shared grid that includes each zero crossing."""
    quarters = np.arange(len(table))
    crossings: dict[str, np.ndarray] = {}
    for group in groups:
        values = table[group].to_numpy()
        flips = np.flatnonzero(values[:-1] * values[1:] < 0)
        crossings[group] = flips + values[flips] / (values[flips] - values[flips + 1])
    points = np.unique(np.concatenate([quarters, *crossings.values()]))
    millis = table["date"].to_numpy(dtype="datetime64[ms]").astype("int64")
    dates = pd.to_datetime(np.interp(points, quarters, millis), unit="ms")
    hedonic = np.interp(points, quarters, np.log(table["hedonic_index"]))
    contributions: dict[str, np.ndarray] = {}
    for group in groups:
        values = np.interp(points, quarters, table[group])
        values[np.searchsorted(points, crossings[group])] = 0
        contributions[group] = values
    return dates, hedonic, contributions


def band_traces(
    dates: pd.DatetimeIndex,
    inner: np.ndarray,
    outer: np.ndarray,
    hue: str,
    *,
    legendgroup: str | None = None,
) -> tuple[go.Scatter, go.Scatter] | None:
    """Close each active run at zero width and leave gaps in the separators."""
    active = inner != outer
    intervals = active[:-1] | active[1:]
    edges = np.flatnonzero(np.diff(np.r_[False, intervals, False]))
    if not len(edges):
        return None
    polygon_x: list[pd.Timestamp | None] = []
    polygon_y: list[float | None] = []
    edge_x: list[pd.Timestamp | None] = []
    edge_y: list[float | None] = []
    inside, outside = np.exp(inner), np.exp(outer)
    for start, stop in zip(edges[::2], edges[1::2], strict=True):
        section = slice(start, stop + 1)
        x = dates[section].tolist()
        polygon_x.extend([*x, *reversed(x), None])
        polygon_y.extend([*outside[section], *inside[section][::-1], None])
        edge_x.extend([*x, None])
        edge_y.extend([*outside[section], None])
    return (
        go.Scatter(
            x=polygon_x,
            y=polygon_y,
            mode="lines",
            line={"width": 0},
            fill="toself",
            fillcolor=composition_tint(hue),
            legendgroup=legendgroup,
            hoverinfo="skip",
            showlegend=False,
        ),
        go.Scatter(
            x=edge_x,
            y=edge_y,
            mode="lines",
            line={"color": SURFACE, "width": 1.6},
            legendgroup=legendgroup,
            hoverinfo="skip",
            showlegend=False,
        ),
    )


def _composition_bands(
    fig: go.Figure, table: pd.DataFrame, groups: Sequence[str]
) -> list[np.ndarray]:
    """Stack signed contributions around the adjusted index and group each component."""
    dates, adjusted, contributions = ribbon_grid(table, groups)
    stacks = [adjusted.copy(), adjusted.copy()]
    separators: list[go.Scatter] = []
    for rank, group in enumerate(groups, start=2):
        hue = COMPOSITION_HUES[group]
        for stack, signed in zip(
            stacks,
            (contributions[group].clip(max=0), contributions[group].clip(min=0)),
            strict=True,
        ):
            outer = stack + signed
            if traces := band_traces(dates, stack, outer, hue, legendgroup=group):
                band, edge = traces
                fig.add_trace(band)
                separators.append(edge)
            stack[:] = outer
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                name=COMPOSITION_LABELS[group],
                legendgroup=group,
                legendrank=rank,
                marker={"symbol": "square", "size": 8, "color": hue},
                hoverinfo="skip",
            )
        )
    fig.add_traces(separators)
    return stacks


def _hedonic_index_traces(fig: go.Figure, table: pd.DataFrame, groups: Sequence[str]) -> None:
    """Draw the base, confidence bounds, raw mean and adjusted index in paint order."""
    # Trace order keeps the reference above the fills and the estimate on top.
    fig.add_trace(
        go.Scatter(
            x=table["date"].iloc[[0, -1]],
            y=[INDEX_BASE, INDEX_BASE],
            mode="lines",
            line=dict(REFERENCE),
            hoverinfo="skip",
            showlegend=False,
        )
    )
    for bound in ("lower", "upper"):
        fig.add_trace(
            go.Scatter(
                x=table["date"],
                y=table[bound],
                mode="lines",
                line={"color": TEAL, "width": 0.7},
                opacity=0.7,
                legendgroup="hedonic_index",
                hoverinfo="skip",
                showlegend=False,
            )
        )
    fig.add_trace(
        go.Scatter(
            x=table["date"],
            y=table["raw_geometric_mean"],
            mode="lines",
            name=HEDONIC_RAW_TRACE_NAME,
            legendrank=1,
            line={"color": INK, "width": 1.2, "dash": "dot"},
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=table["date"],
            y=table["hedonic_index"],
            mode="lines",
            name=HEDONIC_INDEX_TRACE_NAME,
            legendgroup="hedonic_index",
            legendrank=0,
            line={"color": TEAL, "width": 2.4},
            customdata=[
                [
                    quarter_label(row["date"]),
                    number(row["hedonic_index"], 1),
                    number(row["lower"], 1),
                    number(row["upper"], 1),
                    number(row["raw_geometric_mean"], 1),
                    *(composition_number(row[group]) for group in groups),
                ]
                for row in table.to_dict("records")
            ],
            hovertemplate=hedonic_hover(groups),
        )
    )


def _hedonic_layout(fig: go.Figure, table: pd.DataFrame, stacks: Sequence[np.ndarray]) -> None:
    """Set the log-axis extent and ticks for the hedonic index and composition bands."""
    low = min(
        float(stacks[0].min()), float(np.log(table["lower"].min())), float(np.log(INDEX_BASE))
    )
    high = max(
        float(stacks[1].max()), float(np.log(table["upper"].max())), float(np.log(INDEX_BASE))
    )
    padding = max(0.025, 0.08 * (high - low))
    axis_min, axis_max = low - padding, high + padding
    floor, ceiling = np.exp([axis_min, axis_max])
    tick_step = 10 * max(1, int(np.ceil((ceiling - floor) / 70)))
    ticks = np.arange(np.ceil(floor / tick_step) * tick_step, ceiling, tick_step)
    themed(fig, height=420)
    fig.update_layout(
        margin={"l": 35},
        hovermode="x",
        hoverdistance=-1,
    )
    fig.update_xaxes(
        tickformat="%Y",
        dtick="M24",
        showspikes=True,
        spikemode="across",
        spikesnap="data",
        spikethickness=1,
        spikecolor=MUTED,
        spikedash="dot",
    )
    fig.update_yaxes(
        type="log",
        range=[axis_min / np.log(10), axis_max / np.log(10)],
        tickvals=ticks,
        tickformat=",.0f",
        showline=False,
    )


def hedonic_figure(table: pd.DataFrame) -> go.Figure:
    """Display the adjusted index and the signed composition of the raw gap."""
    fig = go.Figure()
    final = table.iloc[-1]
    groups = sorted(COMPOSITION_TERMS, key=lambda group: abs(final[group]), reverse=True)
    stacks = _composition_bands(fig, table, groups)
    _hedonic_index_traces(fig, table, groups)
    _hedonic_layout(fig, table, stacks)
    return fig


def _pattern_member_trace(name: str, rows: pd.DataFrame, colour: str) -> go.Scatter:
    """Encode a firm's membership in colour and a borderline member in grey dashes."""
    ordered = rows.sort_values("period")
    firm = bool(ordered["firm"].iat[0])
    return go.Scatter(
        x=ordered["period"],
        y=ordered["index"],
        mode="lines",
        name=name.title(),
        opacity=0.35 if firm else 1,
        line={
            "color": colour if firm else PATTERN_BORDERLINE,
            "dash": "solid" if firm else "dash",
            "width": 0.9,
        },
        customdata=ordered["membership_share"],
        hovertemplate=PATTERN_MEMBER_HOVER,
    )


def _pattern_panel_figure(
    models: PreparedModels, pattern: str, bounds: tuple[float, float]
) -> go.Figure:
    """Draw one pattern on the common index scale with its centre in the foreground."""
    colour = PATTERN_COLOURS[pattern]
    rows = models.pattern_members
    members = rows.loc[rows["pattern"].eq(pattern)].sort_values(["firm", "neighbourhood"])
    centre = models.pattern_centres
    centre = centre.loc[centre["pattern"].eq(pattern)].sort_values("period")
    fig = go.Figure()
    for name, group in members.groupby("neighbourhood", observed=True, sort=False):
        fig.add_trace(_pattern_member_trace(str(name), group, colour))
    fig.add_trace(
        go.Scatter(
            x=centre["period"],
            y=centre["index"],
            mode="lines+markers",
            line={"color": colour, "width": 3},
            marker={"color": colour, "size": 6},
            customdata=centre[["p10", "p90"]].to_numpy(),
            hovertemplate=PATTERN_CENTRE_HOVER,
        )
    )
    themed(fig, height=PATTERN_FIGURE_HEIGHT)
    fig.update_layout(showlegend=False, margin={"l": 40, "r": 16, "t": 8, "b": 37})
    fig.update_xaxes(
        categoryorder="array",
        categoryarray=PATTERN_PERIODS,
        tickvals=PATTERN_PERIODS,
        tickfont={"size": 10},
        showgrid=False,
        showline=True,
        linecolor=AXIS,
        automargin=True,
    )
    fig.update_yaxes(
        range=bounds,
        dtick=10,
        gridcolor=GRID,
        showline=True,
        linecolor=AXIS,
        zeroline=False,
        tickfont={"size": 11},
    )
    fig.add_hline(y=INDEX_BASE, line=dict(REFERENCE), layer="below")
    return fig


def pattern_figures(models: PreparedModels) -> dict[str, go.Figure]:
    """Build the three figures using one range across all members and centres."""
    values = pd.concat([models.pattern_members["index"], models.pattern_centres["index"]])
    bounds = padded_price_range(float(values.min()), float(values.max()), step=5)
    return {name: _pattern_panel_figure(models, name, bounds) for name in PATTERN_ORDER}
