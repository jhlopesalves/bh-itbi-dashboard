"""Diagnostics tab Plotly figures and building-age premium chart payload."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from bh_itbi.age import AGE_GROUPS, AgePremiums
from bh_itbi.config import (
    AGE_REFERENCE,
    DISTANCE_BAND_WIDTH_KM,
    DISTANCE_MAX_KM,
    DISTANCE_PAD_FRACTION,
    DISTANCE_PERIODS,
    DISTANCE_PRICE_STEP,
    HEAPING_BAR_WIDTH,
    HEAPING_MINIMUM,
    QUARTER_VISIBILITY,
)
from bh_itbi.filters import Filters, quarter_range
from bh_itbi.formatting import age_percent, number, quarter_label
from bh_itbi.text.diagnostics import (
    AGE_ADJUSTED_LABEL,
    AGE_EMPTY_MESSAGE,
    AGE_REFERENCE_LABEL,
    DISTANCE_AXIS_TITLE,
    DISTANCE_EMPTY_MESSAGE,
    DISTANCE_HOVER,
    HEAPING_EMPTY_MESSAGE,
    HEAPING_HOVER,
    HEAPING_OTHER_BINS_LABEL,
    HEAPING_ROUND_BINS_LABEL,
    NOMINAL_DECLARED_AXIS_TITLE,
    TAX_BASE_EMPTY_MESSAGE,
    TAX_HOVER,
    TAX_SHARE_AXIS_TITLE,
    age_row_tooltip,
)
from bh_itbi.text.shared import (
    AGE_LABELS,
    COMPOSITION_LABELS,
    REAL_PRICE_AXIS_TITLE,
    TRANSACTIONS_AXIS_TITLE,
    TYPE_LABELS,
)
from bh_itbi.theme import (
    AGE_FILLS,
    DISTANCE_PERIOD_STYLES,
    INK,
    NEUTRAL_BAR,
    SURFACE,
    TEAL,
    TYPE_STYLES,
    empty_figure,
    end_label_text,
    themed,
)

__all__ = [
    "AgeChart",
    "AgeChartRow",
    "AgeSegment",
    "age_chart_data",
    "age_segments",
    "distance_figure",
    "heaping_figure",
    "tax_base_figure",
]


class AgeSegment(TypedDict):
    """One signed log-point segment of an age-band decomposition bar."""

    group: str
    start: float
    end: float
    subtracts: bool
    hidden: bool


class AgeChartRow(TypedDict):
    """Preformatted labels, segments, confidence interval and tooltip for an age band."""

    label: str
    reference: bool
    observed: float
    observed_label: str
    adjusted_label: str
    segments: list[AgeSegment]
    interval: tuple[float, float] | None
    tooltip: list[str]


class AgeChart(TypedDict):
    """Browser payload for the custom SVG age-premium decomposition chart."""

    rows: list[AgeChartRow]
    fills: dict[str, str]
    labels: dict[str, str]
    teal: str
    empty: str


def age_segments(
    adjusted: float, contributions: Mapping[str, float], observed: float
) -> list[AgeSegment]:
    """Stack additions then subtractions. Retain the endpoints of hidden terms."""
    segments: list[AgeSegment] = [
        {
            "group": "adjusted",
            "start": 0.0,
            "end": adjusted,
            "subtracts": False,
            "hidden": False,
        }
    ]
    ordered = sorted(contributions.items(), key=lambda item: (item[1] < 0, -abs(item[1])))
    end = adjusted
    for group, value in ordered:
        if value == 0:
            continue
        start, end = end, end + value
        segments.append(
            {
                "group": group,
                "start": start,
                "end": end,
                "subtracts": value < 0,
                "hidden": group == "quarter" and abs(value) < QUARTER_VISIBILITY,
            }
        )
    # The estimator checks the identity independently. Snap only the residual
    # floating-point error so the final endpoint and marker share a coordinate.
    segments[-1]["end"] = observed
    return segments


def age_chart_data(result: AgePremiums) -> AgeChart:
    """Keep axis coordinates in log points and send preformatted tooltip strings."""
    rows: list[AgeChartRow] = []
    visible: set[str] = set()
    for key, row in result.table.iterrows():
        label = AGE_LABELS[str(key)]
        observed = float(row["observed"])
        reference = key == AGE_REFERENCE
        observed_percent = age_percent(observed)
        adjusted_label = ""
        segments: list[AgeSegment] = []
        interval: tuple[float, float] | None = None
        adjusted_details: tuple[float, float, float, dict[str, float]] | None = None
        if not reference and "adjusted" in row:
            adjusted = float(row["adjusted"])
            adjusted_percent = age_percent(adjusted)
            contributions = {group: float(row[group]) for group in AGE_GROUPS}
            segments = age_segments(adjusted, contributions, observed)
            visible.update(segment["group"] for segment in segments if not segment["hidden"])
            lower, upper = float(row["lower"]), float(row["upper"])
            interval = (lower, upper)
            adjusted_label = f"{AGE_ADJUSTED_LABEL} {adjusted_percent}"
            adjusted_details = (adjusted, lower, upper, contributions)
        tooltip = age_row_tooltip(
            label,
            float(row["n"]),
            float(row["geometric_mean"]),
            observed,
            adjusted_details,
        )
        rows.append(
            {
                "label": label,
                "reference": reference,
                "observed": observed,
                "observed_label": AGE_REFERENCE_LABEL
                if reference
                else f"observado {observed_percent}",
                "adjusted_label": adjusted_label,
                "segments": segments,
                "interval": interval,
                "tooltip": tooltip,
            }
        )
    return {
        "rows": rows,
        "fills": {group: fill for group, fill in AGE_FILLS.items() if group in visible},
        "labels": {group: COMPOSITION_LABELS[group] for group in AGE_FILLS if group in visible},
        "teal": TEAL,
        "empty": result.unavailable or AGE_EMPTY_MESSAGE,
    }


def tax_base_figure(table: pd.DataFrame, filters: Filters) -> go.Figure:
    """Retain missing or suppressed quarters instead of joining across them."""
    if table.empty or table["share"].isna().all():
        return empty_figure(TAX_BASE_EMPTY_MESSAGE)
    fig = go.Figure()
    periods = quarter_range(filters.start_year, filters.end_year)
    for property_type, label in TYPE_LABELS.items():
        rows = (
            table.loc[table["property_type"].eq(property_type)]
            .set_index("quarter")
            .reindex(periods)
        )
        if rows["share"].isna().all():
            continue
        style = TYPE_STYLES[property_type]
        fig.add_trace(
            go.Scatter(
                x=rows.index,
                y=rows["share"],
                mode="lines+markers",
                marker={"size": 4, "symbol": style["symbol"]},
                name=label,
                connectgaps=False,
                line=dict(style["line"]),
                meta={
                    "text": end_label_text(
                        label, style["line"]["color"], swatch=style["swatch"]
                    )
                },
                customdata=[
                    [quarter_label(t), number(n)]
                    for t, n in zip(rows.index, rows["n"], strict=True)
                ],
                hovertemplate=TAX_HOVER,
            )
        )
    themed(fig).update_layout(meta={"end_labels": True})
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
        (True, HEAPING_ROUND_BINS_LABEL, INK),
    ]:
        rows = table.loc[table["is_round_bin"].eq(highlighted)]
        fig.add_trace(
            go.Bar(
                x=rows["value"],
                y=rows["n"],
                width=HEAPING_BAR_WIDTH,
                name=label,
                marker={"color": color, "line": {"width": 0}},
                hovertemplate=HEAPING_HOVER,
            )
        )
    themed(fig)
    fig.update_layout(barmode="overlay", margin={"l": 50, "r": 18, "t": 12})
    fig.update_xaxes(title_text=NOMINAL_DECLARED_AXIS_TITLE, tickformat=",.0f", nticks=5)
    fig.update_yaxes(title_text=TRANSACTIONS_AXIS_TITLE, rangemode="tozero")
    return fig


def _distance_traces(fig: go.Figure, table: pd.DataFrame) -> list[float]:
    """Draw period medians with gaps and collect the values used for axis limits."""
    plotted: list[float] = []
    half_band = DISTANCE_BAND_WIDTH_KM / 2
    band_centres = np.arange(half_band, DISTANCE_MAX_KM, DISTANCE_BAND_WIDTH_KM)
    for period in DISTANCE_PERIODS:
        colour, width, radius = DISTANCE_PERIOD_STYLES[period]
        rows = table.loc[table["period"].eq(period)].set_index("band_km").reindex(band_centres)
        medians = rows["median"].dropna()
        if medians.empty:
            continue
        plotted.extend(float(m) for m in medians)
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
                meta=end_label_text(period, colour),
                connectgaps=False,
                customdata=[
                    [number(t - half_band), number(t + half_band), number(n)]
                    for t, n in zip(rows.index, rows["n"], strict=True)
                ],
                hovertemplate=DISTANCE_HOVER,
            )
        )
    return plotted


def distance_figure(table: pd.DataFrame) -> go.Figure:
    """Draw the period medians with gaps for bands below the count threshold."""
    if not table.empty:
        unknown = set(table["period"].dropna()) - DISTANCE_PERIOD_STYLES.keys()
        if unknown:
            raise ValueError(
                f"Missing styles for distance periods: {', '.join(sorted(unknown))}."
            )
    if table.empty or table["median"].isna().all():
        return empty_figure(DISTANCE_EMPTY_MESSAGE)
    fig = go.Figure()
    plotted = _distance_traces(fig, table)
    # Keep this y-axis range calculation synchronised with fitVisiblePeriods
    # in assets/distance-labels.js.
    low, high = min(plotted), max(plotted)
    pad = DISTANCE_PAD_FRACTION * (high - low)
    step = DISTANCE_PRICE_STEP
    floor = step * np.floor((low - pad) / step)
    ceiling = step * np.ceil((high + pad) / step)
    if floor == ceiling:
        floor, ceiling = floor - step, ceiling + step
    themed(fig).update_layout(showlegend=True, meta={"pad_fraction": DISTANCE_PAD_FRACTION})
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
