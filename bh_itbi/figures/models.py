"""Models tab Plotly figures: hedonic composition ribbon and trajectory clusters."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from bh_itbi.config import INDEX_BASE, YEAR_TICKS
from bh_itbi.formatting import composition_number, number, quarter_label
from bh_itbi.models import COMPOSITION_TERMS, PreparedModels
from bh_itbi.text.models import (
    CLUSTER_CENTRE_HOVER,
    CLUSTER_INDEX_AXIS_TITLE,
    CLUSTER_TRAJECTORY_HOVER,
    HEDONIC_INDEX_TRACE_NAME,
    HEDONIC_RAW_TRACE_NAME,
    cluster_group_heading,
    hedonic_hover,
)
from bh_itbi.text.shared import (
    COMPOSITION_LABELS,
)
from bh_itbi.theme import (
    CLUSTER_COLORS,
    COMPOSITION_HUES,
    INK,
    MUTED,
    REFERENCE,
    SURFACE,
    TEAL,
    composition_tint,
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


def clusters_figure(models: PreparedModels, group: int | None = None) -> go.Figure:
    """Group selection changes visibility, preserving the offline fitted groups."""
    members, centres = models.members, models.centres
    fig = go.Figure()
    groups = [group] if group else list(CLUSTER_COLORS)
    for group_id in groups:
        rows = members.loc[members["group"].eq(group_id)]
        color = CLUSTER_COLORS[group_id]
        for name, trajectory in rows.groupby("neighbourhood", observed=True):
            ordered = trajectory.sort_values("year")
            fig.add_trace(
                go.Scatter(
                    x=ordered["year"],
                    y=ordered["index"],
                    name=str(name).title(),
                    mode="lines",
                    line={"color": color, "width": 1},
                    opacity=0.25,
                    showlegend=False,
                    legendgroup=str(group_id),
                    customdata=ordered[["n"]],
                    hovertemplate=CLUSTER_TRAJECTORY_HOVER,
                )
            )
        centroid = centres.loc[centres["group"].eq(group_id)].sort_values("year")
        n = rows["neighbourhood"].nunique()
        fig.add_trace(
            go.Scatter(
                x=centroid["year"],
                y=centroid["index"],
                mode="lines+markers",
                name=cluster_group_heading(group_id, n),
                legendgroup=str(group_id),
                line={"color": color, "width": 3},
                marker={"size": 5},
                hovertemplate=CLUSTER_CENTRE_HOVER,
            )
        )
    themed(fig, height=410)
    fig.add_hline(y=INDEX_BASE, line=dict(REFERENCE))
    fig.update_xaxes(tickvals=list(YEAR_TICKS))
    fig.update_yaxes(title_text=CLUSTER_INDEX_AXIS_TITLE)
    return fig
