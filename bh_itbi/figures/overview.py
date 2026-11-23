"""Overview tab Plotly figures and neighbourhood comparison ridgeline payload."""

from __future__ import annotations

from collections.abc import Sequence
from math import ceil, floor, log10
from typing import TypedDict

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from bh_itbi.config import (
    BAND_MINIMUM_POINTS,
    LONG_TIME_AXIS_SPAN_YEARS,
    MAP_CENTRE,
    MAP_ZOOM,
)
from bh_itbi.filters import Filters
from bh_itbi.formatting import currency, month_label, number, quarter_label
from bh_itbi.overview import (
    MapScales,
    NeighbourhoodDistribution,
    city_quarterly_table,
    temporal_table,
)
from bh_itbi.stats import trim_log_density
from bh_itbi.text.overview import (
    CITY_TRAJECTORY_HOVER,
    COMPARISON_AXIS_TITLE,
    MAP_COLORBAR_TITLE,
    MAP_EMPTY_MESSAGE,
    MAP_HOVER,
    TEMPORAL_EMPTY_MESSAGE,
    TEMPORAL_HOVER,
    TEMPORAL_REFERENCE_HOVER,
    TRAJECTORIES_HOVER,
)
from bh_itbi.text.shared import (
    CITY_NAME,
    REAL_PRICE_AXIS_TITLE,
    TYPE_LABELS,
    UNKNOWN_NEIGHBOURHOOD_LABEL,
)
from bh_itbi.theme import (
    INK,
    MUTED,
    REFERENCE,
    TRANSPARENT,
    TYPE_STYLES,
    composition_tint,
    empty_figure,
    neighbourhood_styles,
    padded_price_range,
    rgba,
    themed,
)


class ComparisonRow(TypedDict):
    """Preformatted quantiles and visible KDE curve points for one neighbourhood."""

    name: str
    colour: str
    outer_fill: str
    iqr_fill: str
    n: int
    quantiles: tuple[float, float, float, float, float]
    prices: list[float]
    density: list[float]


class ComparisonPlot(TypedDict):
    """Browser payload for the neighbourhood comparison SVG chart."""

    rows: list[ComparisonRow]
    city_median: float | None
    axis_title: str


def _band(fig: go.Figure, rows: pd.DataFrame, group: str) -> list[pd.Series]:
    """Draw each contiguous observed band separately; never fill across a gap."""
    valid = rows["p25"].notna() & rows["p75"].notna()
    segments = (~valid).cumsum()
    fill = rgba(TYPE_STYLES[group]["line"]["color"], 0.09)
    bounds: list[pd.Series] = []
    for _, segment in rows.loc[valid].groupby(segments[valid], sort=False):
        if len(segment) < BAND_MINIMUM_POINTS:
            continue
        bounds.extend((segment["p25"], segment["p75"]))
        fig.add_trace(
            go.Scatter(
                x=segment["month"],
                y=segment["p75"],
                mode="lines",
                line={"color": INK, "width": 0},
                showlegend=False,
                hoverinfo="skip",
                legendgroup=group,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=segment["month"],
                y=segment["p25"],
                mode="lines",
                line={"color": INK, "width": 0},
                fill="tonexty",
                fillcolor=fill,
                showlegend=False,
                hoverinfo="skip",
                legendgroup=group,
            )
        )
    return bounds


def _apply_time_axis(fig: go.Figure, filters: Filters, plotted: Sequence[pd.Series]) -> None:
    """Configure the shared date x-axis and real-price y-axis for time series."""
    span = filters.end_year - filters.start_year
    fig.update_xaxes(
        dtick="M24" if span >= LONG_TIME_AXIS_SPAN_YEARS else "M12" if span > 0 else "M3",
        tickformat="%Y" if span > 0 else "%b",
        range=[f"{filters.start_year}-01-01", f"{filters.end_year}-12-31"],
    )
    fig.update_yaxes(title_text=REAL_PRICE_AXIS_TITLE)
    values = pd.concat(plotted).dropna()
    if not values.empty:
        fig.update_yaxes(range=padded_price_range(float(values.min()), float(values.max())))


def _monthly_reference_trace(rows: pd.DataFrame, label: str) -> go.Scatter:
    """Label each type's city median while preserving its legend and tooltip."""
    return go.Scatter(
        x=rows["month"],
        y=rows["median"],
        name=f"BH · {label}",
        mode="lines",
        line=dict(REFERENCE),
        connectgaps=False,
        customdata=[
            [month_label(month), number(n)]
            for month, n in zip(rows["month"], rows["n"], strict=True)
        ],
        hovertemplate=TEMPORAL_REFERENCE_HOVER,
    )


def _monthly_median_trace(rows: pd.DataFrame, kind: str, label: str) -> go.Scatter:
    """Draw a solid median with January markers that also identify its legend entry."""
    style = TYPE_STYLES[kind]
    colour = style["line"]["color"]
    return go.Scatter(
        x=rows["month"],
        y=rows["median"],
        name=label,
        mode="lines+markers",
        marker={
            "color": [colour if month.month == 1 else TRANSPARENT for month in rows["month"]],
            "size": 5.5,
            "symbol": style["symbol"],
        },
        line=dict(style["line"]),
        connectgaps=False,
        legendgroup=kind,
        customdata=[
            [month_label(month), number(n), currency(p25), currency(p75)]
            for month, n, p25, p75 in rows[["month", "n", "p25", "p75"]].itertuples(
                index=False, name=None
            )
        ],
        hovertemplate=TEMPORAL_HOVER,
    )


def temporal_figure(selected: pd.DataFrame, city: pd.DataFrame, filters: Filters) -> go.Figure:
    """Keep transaction dispersion distinct from the city-reference median."""
    monthly = temporal_table(selected, filters)
    reference = (
        temporal_table(city, filters.city_reference()) if filters.neighbourhoods else None
    )
    if not monthly["median"].notna().any() and (
        reference is None or not reference["median"].notna().any()
    ):
        return empty_figure(TEMPORAL_EMPTY_MESSAGE)
    fig = go.Figure()
    plotted = [monthly["median"]]
    if reference is not None:
        plotted.append(reference["median"])
    series = {kind: monthly.loc[monthly["property_type"].eq(kind)] for kind in TYPE_LABELS}
    # Paint both bands before the medians so an overlapping fill cannot wash out a line.
    for property_type, rows in series.items():
        plotted.extend(_band(fig, rows, property_type))
    for property_type, label in TYPE_LABELS.items():
        rows = series[property_type]
        if rows.empty:
            continue
        fig.add_trace(_monthly_median_trace(rows, property_type, label))
        if reference is not None:
            ref = reference.loc[reference["property_type"] == property_type]
            fig.add_trace(_monthly_reference_trace(ref, label))
    themed(fig)
    _apply_time_axis(fig, filters, plotted)
    return fig


def _map_hover_data(points: pd.DataFrame) -> list[list[str]]:
    """Prepare map hovers and preserve the source neighbourhood for clicks."""
    hover_columns = ["neighbourhood", "property_type", "built_area_m2", "transaction_date"]
    return [
        [
            str(name) if pd.notna(name) else "",
            str(name).title() if pd.notna(name) else UNKNOWN_NEIGHBOURHOOD_LABEL,
            TYPE_LABELS[property_type],
            number(area, 1),
            month_label(date),
        ]
        for name, property_type, area, date in points[hover_columns].itertuples(
            index=False, name=None
        )
    ]


def _map_colourbar_ticks(lower: float, upper: float) -> tuple[list[float], list[str]]:
    """Place open-ended labels around round interior colour-bar ticks."""
    if lower == upper:
        return [lower], [number(lower)]
    step = 10 ** floor(log10(upper - lower))
    interior = [i * step for i in range(floor(lower / step) + 1, ceil(upper / step))]
    return (
        [lower, *interior, upper],
        [f"≤ {number(lower)}", *(number(tick) for tick in interior), f"≥ {number(upper)}"],
    )


def map_figure(points: pd.DataFrame, style: str, scales: MapScales) -> go.Figure:
    """Draw area-scaled circles coloured by real price per m² on fixed scales."""
    if points.empty:
        return empty_figure(MAP_EMPTY_MESSAGE, 540)
    points = points.sort_values("built_area_m2", ascending=False, kind="stable")
    tickvals, ticktext = _map_colourbar_ticks(scales["price_lower"], scales["price_upper"])
    fig = go.Figure(
        go.Scattermap(
            lat=points["lat"],
            lon=points["lon"],
            mode="markers",
            marker={
                "size": points["built_area_m2"].clip(upper=scales["area_reference"]),
                "sizemode": "area",
                "sizeref": scales["area_reference"] / 8**2,
                "sizemin": 2.5,
                "opacity": 0.60,
                "color": points["price_per_m2_brl_real"],
                "colorscale": "Viridis",
                "cmin": scales["price_lower"],
                "cmax": scales["price_upper"],
                "showscale": True,
                "colorbar": {
                    "title": {"text": MAP_COLORBAR_TITLE, "font": {"size": 10, "color": INK}},
                    "thickness": 8,
                    "len": 0.82,
                    "outlinewidth": 0,
                    "tickmode": "array",
                    "tickvals": tickvals,
                    "ticktext": ticktext,
                    "tickfont": {"size": 10, "color": MUTED},
                    "xpad": 8,
                },
            },
            customdata=_map_hover_data(points),
            showlegend=False,
            hovertemplate=MAP_HOVER,
        )
    )
    themed(fig, height=540)
    fig.update_layout(
        showlegend=False,
        map={
            "style": style,
            "center": {"lat": MAP_CENTRE[0], "lon": MAP_CENTRE[1]},
            "zoom": MAP_ZOOM,
        },
        margin={"l": 0, "r": 12, "t": 0, "b": 0},
        uirevision="bh-point-map",
        clickmode="event",
        dragmode="pan",
    )
    return fig


def neighbourhood_comparison_data(
    grid: np.ndarray,
    rows: Sequence[NeighbourhoodDistribution],
    city: pd.DataFrame,
    names: Sequence[str],
) -> ComparisonPlot:
    """Send only the visible curves and summaries to the browser."""
    styles = neighbourhood_styles(names)
    visible: list[ComparisonRow] = []
    for row in rows:
        if row.density is None:
            prices: list[float] = []
            density: list[float] = []
        else:
            visible_prices, visible_density = trim_log_density(grid, row.density)
            prices = visible_prices.tolist()
            density = visible_density.tolist()
        colour = styles[row.neighbourhood].colour
        visible.append(
            {
                "name": row.neighbourhood.title(),
                "colour": colour,
                "outer_fill": composition_tint(colour, strength=0.34),
                "iqr_fill": composition_tint(colour, strength=0.68),
                "n": row.n,
                "quantiles": row.quantiles,
                "prices": prices,
                "density": density,
            }
        )
    values = city["price_per_m2_brl_real"]
    city_median = values.loc[values.gt(0) & values.lt(np.inf)].median()
    return {
        "rows": visible,
        "city_median": float(city_median) if pd.notna(city_median) else None,
        "axis_title": COMPARISON_AXIS_TITLE,
    }


def neighbourhood_trajectories_figure(
    rows: pd.DataFrame, city: pd.DataFrame, filters: Filters
) -> go.Figure:
    """Compare source neighbourhoods with a city median pooled from raw records."""
    quarterly = temporal_table(rows, filters, neighbourhood=True)
    fig = go.Figure()
    plotted: list[pd.Series] = []
    for name, style in neighbourhood_styles(filters.neighbourhoods).items():
        subset = quarterly.loc[quarterly["neighbourhood"].eq(name)]
        plotted.append(subset["median"])
        label = name.title()
        fig.add_trace(
            go.Scatter(
                x=subset["quarter"],
                y=subset["median"],
                mode="lines+markers",
                name=label,
                line={"color": style.colour, "dash": style.dash, "width": 2},
                marker={"size": 4},
                connectgaps=False,
                customdata=[
                    [quarter_label(quarter), number(n)]
                    for quarter, n in zip(subset["quarter"], subset["n"], strict=True)
                ],
                hovertemplate=TRAJECTORIES_HOVER,
            )
        )
    # Same type and dates, but no geographical restriction. A pooled city median
    # is recomputed from transactions, never by averaging neighbourhood medians.
    ref = city_quarterly_table(city, filters.city_reference())
    plotted.append(ref["median"])
    fig.add_trace(
        go.Scatter(
            x=ref["quarter"],
            y=ref["median"],
            name=CITY_NAME,
            mode="lines",
            line=dict(REFERENCE),
            connectgaps=False,
            customdata=[
                [quarter_label(t), number(n)]
                for t, n in zip(ref["quarter"], ref["n"], strict=True)
            ],
            hovertemplate=CITY_TRAJECTORY_HOVER,
        )
    )
    themed(fig, height=370)
    _apply_time_axis(fig, filters, plotted)
    # Show up to six rows before scrolling, preserving room for the trajectories.
    fig.update_layout(legend={"maxheight": 124})
    return fig
