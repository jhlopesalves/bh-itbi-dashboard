"""Plotly figures with shared units, colour meanings and honest missing periods."""

from __future__ import annotations

from typing import TypedDict

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from bh_itbi.config import (
    COMPOSITION_LABEL_THRESHOLD,
    DEFAULT_NEIGHBOURHOODS,
    DISTANCE_BAND_WIDTH_KM,
    DISTANCE_MAX_KM,
    DISTANCE_PAD_FRACTION,
    DISTANCE_PERIODS,
    DISTANCE_PRICE_STEP,
    DISTRIBUTION_BINS,
    DISTRIBUTION_MINIMUM,
    HEAPING_BAR_WIDTH,
    HEAPING_MINIMUM,
    MAP_CENTRE,
    MAP_ZOOM,
    YEAR_TICKS,
)
from bh_itbi.filters import Filters
from bh_itbi.formatting import (
    composition_number,
    currency,
    month_label,
    number,
    quarter_label,
)
from bh_itbi.models import COMPOSITION_TERMS
from bh_itbi.overview import (
    NeighbourhoodDistribution,
    city_quarterly_table,
    temporal_table,
)
from bh_itbi.stats import trim_log_density
from bh_itbi.text import (
    CITY_NAME,
    CITY_REFERENCE_EXTRA,
    CLUSTER_INDEX_AXIS_TITLE,
    COMPARISON_AXIS_TITLE,
    DISTANCE_AXIS_TITLE,
    DISTANCE_EMPTY_MESSAGE,
    DISTRIBUTION_EMPTY_MESSAGE,
    DISTRIBUTION_LABELS,
    HEAPING_EMPTY_MESSAGE,
    HEAPING_OTHER_BINS_LABEL,
    HEAPING_ROUND_BINS_LABEL,
    HEDONIC_INDEX_TRACE_NAME,
    HEDONIC_RAW_TRACE_NAME,
    LOG_CURRENCY_AXIS_TITLE,
    MAP_COLORBAR_TITLE,
    MAP_EMPTY_MESSAGE,
    NOMINAL_DECLARED_AXIS_TITLE,
    REAL_PRICE_AXIS_TITLE,
    TAX_BASE_EMPTY_MESSAGE,
    TAX_SHARE_AXIS_TITLE,
    TEMPORAL_EMPTY_MESSAGE,
    TRANSACTIONS_AXIS_TITLE,
    TYPE_LABELS,
    UNKNOWN_NEIGHBOURHOOD_LABEL,
    cluster_group_heading,
)
from bh_itbi.theme import (
    CLUSTER_COLORS,
    COMPOSITION_HUES,
    DISTANCE_PERIOD_STYLES,
    INK,
    MUTED,
    NEIGHBOURHOOD_COLORS,
    NEUTRAL_BAR,
    PALETTE,
    PRICE_SCALE,
    SURFACE,
    TEAL,
    TYPE_COLORS,
    composition_tint,
    empty_figure,
    hex_to_rgb,
    themed,
)

__all__ = [
    "DISTRIBUTION_LABELS",
    "ComparisonPlot",
    "ComparisonRow",
    "band_traces",
    "clusters_figure",
    "distance_figure",
    "distribution_figure",
    "heaping_figure",
    "hedonic_figure",
    "label_ribbon",
    "map_figure",
    "neighbourhood_comparison_data",
    "neighbourhood_trajectories_figure",
    "ribbon_grid",
    "tax_base_figure",
    "temporal_figure",
]


def _band(fig: go.Figure, rows: pd.DataFrame, x: str, color: str, group: str) -> None:
    """Draw each contiguous observed band separately; never fill across a gap."""
    valid = rows["p25"].notna() & rows["p75"].notna()
    segments = (~valid).cumsum()
    red, green, blue = hex_to_rgb(color)
    for _, segment in rows.loc[valid].groupby(segments[valid], sort=False):
        if len(segment) < 2:
            continue
        fig.add_trace(
            go.Scatter(
                x=segment[x],
                y=segment["p75"],
                mode="lines",
                line={"width": 0},
                showlegend=False,
                hoverinfo="skip",
                legendgroup=group,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=segment[x],
                y=segment["p25"],
                mode="lines",
                line={"width": 0},
                fill="tonexty",
                fillcolor=f"rgba({red},{green},{blue},0.12)",
                showlegend=False,
                hoverinfo="skip",
                legendgroup=group,
            )
        )


def temporal_figure(selected: pd.DataFrame, city: pd.DataFrame, filters: Filters) -> go.Figure:
    """Keep transaction dispersion distinct from the city-reference median."""
    monthly = temporal_table(selected, filters)
    reference = (
        temporal_table(city, filters.city_reference()) if filters.neighbourhoods else None
    )
    fig = go.Figure()
    geographical = bool(filters.neighbourhoods)
    for property_type, label in TYPE_LABELS.items():
        rows = monthly.loc[monthly["property_type"] == property_type]
        if rows.empty:
            continue
        color = TYPE_COLORS[property_type]
        _band(fig, rows, "month", color, property_type)
        fig.add_trace(
            go.Scatter(
                x=rows["month"],
                y=rows["median"],
                name=label,
                mode="lines+markers",
                marker={"size": 3},
                line={"color": color, "width": 2.6},
                connectgaps=False,
                legendgroup=property_type,
                customdata=[
                    [
                        month_label(row.month),
                        number(row.n),
                        currency(row.p25),
                        currency(row.p75),
                    ]
                    for row in rows.itertuples()
                ],
                hovertemplate="<b>%{customdata[0]}</b><br>Mediana: R$ %{y:,.0f}/m²"
                "<br>P25–P75: %{customdata[2]} a %{customdata[3]}"
                "<br>Transações: %{customdata[1]}<extra>%{fullData.name}</extra>",
            )
        )
        if geographical:
            ref = reference.loc[reference["property_type"] == property_type]
            fig.add_trace(
                go.Scatter(
                    x=ref["month"],
                    y=ref["median"],
                    name=f"BH · {label}",
                    mode="lines",
                    line={"color": color, "width": 1.5, "dash": "dot"},
                    opacity=0.75,
                    connectgaps=False,
                    customdata=[[month_label(r.month), number(r.n)] for r in ref.itertuples()],
                    hovertemplate="%{customdata[0]}<br>BH: R$ %{y:,.0f}/m²"
                    "<br>Transações: %{customdata[1]}<extra>%{fullData.name}</extra>",
                )
            )
    if not any(pd.Series(trace.y).notna().any() for trace in fig.data):
        return empty_figure(TEMPORAL_EMPTY_MESSAGE)
    themed(fig)
    fig.update_xaxes(
        dtick="M24"
        if filters.end_year - filters.start_year >= 5
        else "M12"
        if filters.end_year > filters.start_year
        else "M3",
        tickformat="%Y" if filters.end_year > filters.start_year else "%b",
        range=[f"{filters.start_year}-01-01", f"{filters.end_year}-12-31"],
    )
    fig.update_yaxes(title_text=REAL_PRICE_AXIS_TITLE, rangemode="tozero")
    return fig


def map_figure(points: pd.DataFrame, style: str) -> go.Figure:
    """Translucent, area-scaled circles following the notebook's price map."""
    if points.empty:
        return empty_figure(MAP_EMPTY_MESSAGE, 540)
    custom = [
        [
            str(row.neighbourhood) if pd.notna(row.neighbourhood) else "",
            str(row.neighbourhood).title()
            if pd.notna(row.neighbourhood)
            else UNKNOWN_NEIGHBOURHOOD_LABEL,
            TYPE_LABELS[row.property_type],
            number(row.built_area_m2, 1),
            month_label(row.transaction_date),
        ]
        for row in points.itertuples()
    ]
    fig = go.Figure(
        go.Scattermap(
            lat=points["lat"],
            lon=points["lon"],
            mode="markers",
            marker={
                "size": points["built_area_m2"],
                "sizemode": "area",
                "sizeref": points["built_area_m2"].max() / 16**2,
                "sizemin": 2.5,
                "opacity": 0.70,
                "color": points["price_per_m2_brl"],
                "colorscale": PRICE_SCALE,
                "showscale": True,
                "colorbar": {
                    "title": {"text": MAP_COLORBAR_TITLE, "font": {"size": 10, "color": INK}},
                    "thickness": 8,
                    "len": 0.82,
                    "outlinewidth": 0,
                    "tickformat": ",.0f",
                    "tickfont": {"size": 10, "color": MUTED},
                    "xpad": 8,
                },
            },
            customdata=custom,
            showlegend=False,
            hovertemplate=(
                "<b>%{customdata[1]}</b><br>%{customdata[2]}"
                "<br>Valor declarado: R$ %{marker.color:,.0f}/m²"
                "<br>Área construída: %{customdata[3]} m²"
                "<br>%{customdata[4]}<extra></extra>"
            ),
        )
    )
    themed(fig, height=540)
    fig.update_layout(
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


def distribution_figure(frame: pd.DataFrame, column: str) -> go.Figure:
    """Shared geometric bins show every positive value without tail trimming."""
    values = frame.loc[frame[column].gt(0), ["property_type", column]]
    if len(values) < DISTRIBUTION_MINIMUM:
        return empty_figure(DISTRIBUTION_EMPTY_MESSAGE, 330)
    low, high = values[column].min(), values[column].max()
    if low == high:
        low, high = low * 0.9, high * 1.1
    edges = np.geomspace(low, high, DISTRIBUTION_BINS + 1)
    centres = np.sqrt(edges[:-1] * edges[1:])
    fig = go.Figure()
    for property_type, label in TYPE_LABELS.items():
        subset = values.loc[values["property_type"].eq(property_type), column]
        if subset.empty:
            continue
        counts, _ = np.histogram(subset, bins=edges)
        fig.add_trace(
            go.Bar(
                x=centres,
                y=counts,
                width=np.diff(edges) * 0.92,
                marker={"color": TYPE_COLORS[property_type], "line": {"width": 0}},
                opacity=0.75,
                name=label,
                customdata=[
                    [currency(a), currency(b)]
                    for a, b in zip(edges[:-1], edges[1:], strict=True)
                ],
                hovertemplate="%{customdata[0]} a %{customdata[1]}<br>Transações: %{y:,.0f}"
                "<extra>%{fullData.name}</extra>",
            )
        )
        if len(subset) >= DISTRIBUTION_MINIMUM:
            fig.add_vline(
                x=subset.median(),
                line={"color": TYPE_COLORS[property_type], "dash": "dot", "width": 1.5},
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
    if len(ticks) > 4:
        ticks = [ticks[i] for i in np.linspace(0, len(ticks) - 1, 4, dtype=int)]
    labels = [
        f"{number(tick / 1_000_000)} mi"
        if tick >= 1_000_000
        else f"{number(tick / 1000)} mil"
        if tick >= 1000
        else number(tick)
        for tick in ticks
    ]
    fig.update_xaxes(
        type="log",
        title_text=LOG_CURRENCY_AXIS_TITLE,
        tickmode="array",
        tickvals=ticks,
        ticktext=labels,
    )
    fig.update_yaxes(title_text=TRANSACTIONS_AXIS_TITLE, rangemode="tozero", tickformat=",.0f")
    return fig


class ComparisonRow(TypedDict):
    name: str
    n: int
    quantiles: tuple[float, float, float, float, float]
    prices: list[float]
    density: list[float]


class ComparisonPlot(TypedDict):
    rows: list[ComparisonRow]
    city_median: float | None
    axis_title: str


def neighbourhood_comparison_data(
    grid: np.ndarray, rows: list[NeighbourhoodDistribution], city: pd.DataFrame
) -> ComparisonPlot:
    """Send only the visible curves and summaries to the browser."""
    visible: list[ComparisonRow] = []
    for row in rows:
        if row.density is None:
            prices, density = [], []
        else:
            visible_prices, visible_density = trim_log_density(grid, row.density)
            prices = visible_prices.tolist()
            density = visible_density.tolist()
        visible.append(
            {
                "name": row.neighbourhood.title(),
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
    names = list(filters.neighbourhoods or DEFAULT_NEIGHBOURHOODS)
    for i, name in enumerate(names):
        subset = quarterly.loc[quarterly["neighbourhood"].eq(name)]
        fig.add_trace(
            go.Scatter(
                x=subset["quarter"],
                y=subset["median"],
                mode="lines+markers",
                name=name.title(),
                line={
                    "color": NEIGHBOURHOOD_COLORS.get(name, PALETTE[i % len(PALETTE)]),
                    "width": 2,
                },
                marker={"size": 4},
                connectgaps=False,
                customdata=[
                    [quarter_label(r.quarter), number(r.n)] for r in subset.itertuples()
                ],
                hovertemplate="%{customdata[0]}<br>Mediana: R$ %{y:,.0f}/m²"
                "<br>Transações: %{customdata[1]}<extra>%{fullData.name}</extra>",
            )
        )
    # Same type and dates, but no geographical restriction. A pooled city median
    # is recomputed from transactions, never by averaging neighbourhood medians.
    ref = city_quarterly_table(city, filters.city_reference())
    fig.add_trace(
        go.Scatter(
            x=ref["quarter"],
            y=ref["median"],
            name=CITY_NAME,
            mode="lines",
            line={"color": MUTED, "width": 2, "dash": "dash"},
            connectgaps=False,
            customdata=[
                [quarter_label(t), number(n)]
                for t, n in zip(ref["quarter"], ref["n"], strict=True)
            ],
            hovertemplate="%{customdata[0]}<br>BH: R$ %{y:,.0f}/m²"
            f"<br>Transações: %{{customdata[1]}}<extra>{CITY_REFERENCE_EXTRA}</extra>",
        )
    )
    themed(fig, height=370)
    fig.update_xaxes(
        dtick="M24"
        if filters.end_year - filters.start_year >= 5
        else "M12"
        if filters.end_year > filters.start_year
        else "M3",
        tickformat="%Y" if filters.end_year > filters.start_year else "%b",
        range=[f"{filters.start_year}-01-01", f"{filters.end_year}-12-31"],
    )
    fig.update_yaxes(title_text=REAL_PRICE_AXIS_TITLE, rangemode="tozero")
    # Show up to six rows before scrolling, preserving room for the trajectories.
    fig.update_layout(legend={"maxheight": 124})
    return fig


def tax_base_figure(table: pd.DataFrame, filters: Filters) -> go.Figure:
    """Retain missing or suppressed quarters instead of joining across them."""
    if table.empty or table["share"].isna().all():
        return empty_figure(TAX_BASE_EMPTY_MESSAGE)
    fig = go.Figure()
    periods = pd.date_range(
        f"{filters.start_year}-01-01", f"{filters.end_year}-10-01", freq="QS"
    )
    for property_type, label in TYPE_LABELS.items():
        rows = (
            table.loc[table["property_type"].eq(property_type)]
            .set_index("quarter")
            .reindex(periods)
        )
        if rows["share"].isna().all():
            continue
        fig.add_trace(
            go.Scatter(
                x=rows.index,
                y=rows["share"],
                mode="lines+markers",
                marker={"size": 4},
                name=label,
                connectgaps=False,
                line={"color": TYPE_COLORS[property_type], "width": 2.6},
                customdata=[
                    [quarter_label(t), number(n)]
                    for t, n in zip(rows.index, rows["n"], strict=True)
                ],
                hovertemplate="%{customdata[0]}<br>Abaixo da base: %{y:.1%}"
                "<br>Transações: %{customdata[1]}<extra>%{fullData.name}</extra>",
            )
        )
    themed(fig)
    fig.update_xaxes(tickformat="%Y", dtick="M24")
    fig.update_yaxes(range=[0, 1], tickformat=".0%", title_text=TAX_SHARE_AXIS_TITLE)
    return fig


def heaping_figure(table: pd.DataFrame) -> go.Figure:
    """Highlight centred bins near round amounts, without a fitted counterfactual."""
    if table["n"].sum() < HEAPING_MINIMUM:
        return empty_figure(HEAPING_EMPTY_MESSAGE)
    fig = go.Figure()
    for highlighted, label, color in [
        (False, HEAPING_OTHER_BINS_LABEL, NEUTRAL_BAR),
        (True, HEAPING_ROUND_BINS_LABEL, TEAL),
    ]:
        rows = table.loc[table["is_round_bin"].eq(highlighted)]
        fig.add_trace(
            go.Bar(
                x=rows["value"],
                y=rows["n"],
                width=HEAPING_BAR_WIDTH,
                name=label,
                marker={"color": color, "line": {"width": 0}},
                hovertemplate=(
                    "Faixa centrada em R$ %{x:,.0f}<br>Transações: %{y:,.0f}<extra></extra>"
                ),
            )
        )
    themed(fig)
    fig.update_layout(barmode="overlay", margin={"l": 50, "r": 18, "t": 12})
    fig.update_xaxes(title_text=NOMINAL_DECLARED_AXIS_TITLE, tickformat=",.0f", nticks=5)
    fig.update_yaxes(title_text=TRANSACTIONS_AXIS_TITLE, rangemode="tozero")
    return fig


def distance_figure(table: pd.DataFrame) -> go.Figure:
    """Draw the period medians with gaps for bands below the count threshold."""
    if not table.empty:
        unknown = set(table["period"].dropna()) - DISTANCE_PERIOD_STYLES.keys()
        if unknown:
            raise ValueError(f"Períodos de distância sem estilo: {', '.join(sorted(unknown))}.")
    if table.empty or table["median"].isna().all():
        return empty_figure(DISTANCE_EMPTY_MESSAGE)
    fig = go.Figure()
    plotted = []
    half_band = DISTANCE_BAND_WIDTH_KM / 2
    band_centres = np.arange(half_band, DISTANCE_MAX_KM, DISTANCE_BAND_WIDTH_KM)
    for period in DISTANCE_PERIODS:
        colour, width, radius = DISTANCE_PERIOD_STYLES[period]
        rows = table.loc[table["period"].eq(period)].set_index("band_km").reindex(band_centres)
        medians = rows["median"].dropna()
        if medians.empty:
            continue
        plotted.extend(medians)
        swatch = f'<span style="color:{colour};font-size:14px">■</span>'
        fig.add_trace(
            go.Scatter(
                x=rows.index,
                y=rows["median"].tolist(),
                mode="lines+markers",
                name=period,
                line={"color": colour, "width": width},
                marker={
                    "color": colour,
                    "size": 2 * radius,
                    "line": {"color": SURFACE, "width": 1.4},
                },
                meta=f"{swatch}&nbsp;&nbsp;{period}",
                connectgaps=False,
                customdata=[
                    [number(t - half_band), number(t + half_band), number(n)]
                    for t, n in zip(rows.index, rows["n"], strict=True)
                ],
                hovertemplate="%{customdata[0]}–%{customdata[1]} km<br>Mediana: R$ %{y:,.0f}/m²"
                "<br>Transações: %{customdata[2]}<br>%{meta}<extra></extra>",
            )
        )
    low, high = min(plotted), max(plotted)
    pad = DISTANCE_PAD_FRACTION * (high - low)
    step = DISTANCE_PRICE_STEP
    floor = step * np.floor((low - pad) / step)
    ceiling = step * np.ceil((high + pad) / step)
    if floor == ceiling:
        floor, ceiling = floor - step, ceiling + step
    themed(fig).update_layout(showlegend=True)
    fig.update_xaxes(
        title_text=DISTANCE_AXIS_TITLE,
        range=[0, DISTANCE_MAX_KM],
        dtick=2,
    )
    fig.update_yaxes(
        title_text=REAL_PRICE_AXIS_TITLE,
        range=[floor, ceiling],
        tick0=0,
        dtick=step,
        showgrid=True,
        separatethousands=True,
    )
    return fig


def ribbon_grid(
    table: pd.DataFrame, groups: list[str]
) -> tuple[pd.DatetimeIndex, np.ndarray, dict[str, np.ndarray]]:
    """Interpolate in log space on a shared grid that includes each zero crossing."""
    quarters = np.arange(len(table))
    crossings = {}
    for group in groups:
        values = table[group].to_numpy()
        flips = np.flatnonzero(values[:-1] * values[1:] < 0)
        crossings[group] = flips + values[flips] / (values[flips] - values[flips + 1])
    points = np.unique(np.concatenate([quarters, *crossings.values()]))
    millis = table["date"].to_numpy(dtype="datetime64[ms]").astype("int64")
    dates = pd.to_datetime(np.interp(points, quarters, millis), unit="ms")
    hedonic = np.interp(points, quarters, np.log(table["indice_hedonico"]))
    contributions = {}
    for group in groups:
        values = np.interp(points, quarters, table[group])
        values[np.searchsorted(points, crossings[group])] = 0
        contributions[group] = values
    return dates, hedonic, contributions


def band_traces(
    dates: pd.DatetimeIndex, inner: np.ndarray, outer: np.ndarray, hue: str
) -> tuple[go.Scatter, go.Scatter] | None:
    """Close each active run at zero width and leave gaps in the separators."""
    active = inner != outer
    intervals = active[:-1] | active[1:]
    edges = np.flatnonzero(np.diff(np.r_[False, intervals, False]))
    if not len(edges):
        return None
    polygon_x, polygon_y, edge_x, edge_y = [], [], [], []
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
            hoverinfo="skip",
            showlegend=False,
        ),
        go.Scatter(
            x=edge_x,
            y=edge_y,
            mode="lines",
            line={"color": SURFACE, "width": 1.6},
            hoverinfo="skip",
            showlegend=False,
        ),
    )


def label_ribbon(
    fig: go.Figure,
    final: pd.Series,
    centres: dict[str, float],
    axis_min: float,
    axis_max: float,
) -> None:
    """Place right-edge labels in plot coordinates with room between them."""
    axis_span = axis_max - axis_min
    labels = [
        (
            (centre - axis_min) / axis_span,
            f'<span style="color:{COMPOSITION_HUES[group]}">■</span> '
            f"{group}&nbsp; {composition_number(final[group])}",
            INK,
        )
        for group, centre in centres.items()
        if abs(final[group]) >= COMPOSITION_LABEL_THRESHOLD
    ]
    labels.extend(
        [
            (
                (np.log(final["indice_hedonico"]) - axis_min) / axis_span + 0.04,
                f"<b>Índice hedônico&nbsp; {number(final['indice_hedonico'])}</b>",
                TEAL,
            ),
            (
                (np.log(final["media_geometrica_bruta"]) - axis_min) / axis_span - 0.04,
                f"Média bruta&nbsp; {number(final['media_geometrica_bruta'])}",
                INK,
            ),
        ]
    )
    labels.sort(key=lambda label: label[0])
    minimum_gap = 0.065
    positions = [max(minimum_gap / 2, labels[0][0])]
    for target, _, _ in labels[1:]:
        positions.append(max(target, positions[-1] + minimum_gap))
    positions[-1] = min(1 - minimum_gap / 2, positions[-1])
    for i in range(len(positions) - 2, -1, -1):
        positions[i] = min(positions[i], positions[i + 1] - minimum_gap)
    for y, (_, label, colour) in zip(positions, labels, strict=True):
        fig.add_annotation(
            x=1,
            xref="paper",
            xanchor="left",
            xshift=6,
            y=y,
            yref="paper",
            yanchor="middle",
            text=label,
            font={"size": 11, "color": colour},
            showarrow=False,
        )


def hedonic_figure(table: pd.DataFrame) -> go.Figure:
    """Display the adjusted index and the signed composition of the raw gap."""
    fig = go.Figure()
    final = table.iloc[-1]
    groups = sorted(COMPOSITION_TERMS, key=lambda group: abs(final[group]), reverse=True)
    dates, adjusted, contributions = ribbon_grid(table, groups)
    stacks = [adjusted.copy(), adjusted.copy()]
    separators = []
    centres = {}
    for rank, group in enumerate(groups, start=2):
        hue = COMPOSITION_HUES[group]
        for stack, signed in zip(
            stacks,
            (contributions[group].clip(max=0), contributions[group].clip(min=0)),
            strict=True,
        ):
            outer = stack + signed
            if traces := band_traces(dates, stack, outer, hue):
                band, edge = traces
                fig.add_trace(band)
                separators.append(edge)
            if signed[-1]:
                centres[group] = (stack[-1] + outer[-1]) / 2
            stack[:] = outer
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                name=group,
                legendrank=rank,
                marker={"symbol": "square", "size": 8, "color": hue},
                hoverinfo="skip",
            )
        )
    fig.add_traces(separators)

    # Trace order keeps the reference above the fills and the estimate on top.
    fig.add_trace(
        go.Scatter(
            x=table["date"].iloc[[0, -1]],
            y=[100, 100],
            mode="lines",
            line={"color": INK, "width": 0.7, "dash": "dash"},
            opacity=0.45,
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
                hoverinfo="skip",
                showlegend=False,
            )
        )
    fig.add_trace(
        go.Scatter(
            x=table["date"],
            y=table["media_geometrica_bruta"],
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
            y=table["indice_hedonico"],
            mode="lines",
            name=HEDONIC_INDEX_TRACE_NAME,
            legendrank=0,
            line={"color": TEAL, "width": 2.4},
            customdata=[
                [
                    quarter_label(row["date"]),
                    number(row["indice_hedonico"], 1),
                    number(row["lower"], 1),
                    number(row["upper"], 1),
                    number(row["media_geometrica_bruta"], 1),
                    *(composition_number(row[group]) for group in groups),
                ]
                for row in table.to_dict("records")
            ],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>Índice hedônico: %{customdata[1]}"
                "<br>IC 95%: %{customdata[2]} a %{customdata[3]}"
                "<br>Média bruta: %{customdata[4]}<br><br>Composição (log × 100)"
                + "".join(
                    f"<br>{group}: %{{customdata[{i}]}}"
                    for i, group in enumerate(groups, start=5)
                )
                + "<extra></extra>"
            ),
        )
    )
    low = min(stacks[0].min(), np.log(table["lower"].min()), np.log(100))
    high = max(stacks[1].max(), np.log(table["upper"].max()), np.log(100))
    padding = max(0.025, 0.08 * (high - low))
    axis_min, axis_max = low - padding, high + padding
    floor, ceiling = np.exp([axis_min, axis_max])
    tick_step = 10 * max(1, int(np.ceil((ceiling - floor) / 70)))
    ticks = np.arange(np.ceil(floor / tick_step) * tick_step, ceiling, tick_step)
    themed(fig, height=420)
    fig.update_layout(
        margin={"l": 35, "r": 127},
        hovermode="x",
        hoverdistance=-1,
        legend={"itemclick": False, "itemdoubleclick": False},
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
    label_ribbon(fig, final, centres, axis_min, axis_max)
    return fig


def clusters_figure(models: dict, group: int | None = None) -> go.Figure:
    """Group selection changes visibility, preserving the offline fitted groups."""
    members, centres = models["members"], models["centres"]
    fig = go.Figure()
    groups = [group] if group else CLUSTER_COLORS
    for group_id in groups:
        rows = members.loc[members["group"].eq(group_id)]
        color = CLUSTER_COLORS[group_id]
        for name, trajectory in rows.groupby("neighbourhood", observed=True):
            trajectory = trajectory.sort_values("year")
            fig.add_trace(
                go.Scatter(
                    x=trajectory["year"],
                    y=trajectory["index"],
                    name=str(name).title(),
                    mode="lines",
                    line={"color": color, "width": 1},
                    opacity=0.25,
                    showlegend=False,
                    legendgroup=str(group_id),
                    customdata=trajectory[["n"]],
                    hovertemplate=(
                        "%{x}<br>Índice: %{y:.1f}<br>Transações: %{customdata[0]:,.0f}"
                        "<extra>%{fullData.name}</extra>"
                    ),
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
                hovertemplate=(
                    "%{x}<br>Centro do grupo: %{y:.1f}<extra>%{fullData.name}</extra>"
                ),
            )
        )
    themed(fig, height=410)
    fig.add_hline(y=100, line={"color": MUTED, "width": 1, "dash": "dot"})
    fig.update_xaxes(tickvals=list(YEAR_TICKS))
    fig.update_yaxes(title_text=CLUSTER_INDEX_AXIS_TITLE)
    return fig
