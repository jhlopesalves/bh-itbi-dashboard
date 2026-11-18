"""Overview tab layout: KPI summary strip, spatial grid and temporal/comparison cards."""

from __future__ import annotations

from collections.abc import Sequence

from dash import dcc, html

from bh_itbi.layout.components import card, dropdown, graph, html_attributes, metric
from bh_itbi.text import overview as text
from bh_itbi.urls import DEFAULT_MAP_STYLE, DEFAULT_METRIC


def distribution_summary(
    quartiles: Sequence[tuple[str, str]] | None,
) -> list[html.Div] | html.P:
    """Render the available quartiles or the distribution empty state."""
    if quartiles is None:
        return html.P(text.DISTRIBUTION_EMPTY_SUMMARY)
    return [html.Div([html.Span(label), html.Strong(value)]) for label, value in quartiles]


def _overview_heading() -> html.Div:
    """Label the overview and show the active filter scope."""
    return html.Div(
        [
            html.P(text.OVERVIEW_EYEBROW, className="eyebrow"),
            html.P(
                id="scope-label",
                className="scope-label",
                role="status",
                **html_attributes(aria_live="polite"),
            ),
        ],
        className="section-line",
    )


def _kpi_strip() -> html.Div:
    """Render the four headline statistics."""
    return html.Div(
        [
            metric(text.KPI_COUNT_LABEL, "kpi-count", text.KPI_COUNT_UNIT),
            metric(text.KPI_NOMINAL_LABEL, "kpi-nominal", text.KPI_NOMINAL_UNIT),
            metric(text.KPI_REAL_LABEL, "kpi-real", text.KPI_REAL_UNIT),
            html.Div(
                [
                    html.P(text.KPI_COVERAGE_LABEL, className="metric-label"),
                    html.Div("—", id="kpi-coverage", className="metric-value"),
                    html.P(text.KPI_COVERAGE_UNIT, className="metric-unit"),
                    html.P(id="kpi-coverage-note", className="metric-note"),
                ],
                className="metric",
            ),
        ],
        className="metrics",
    )


def _map_card() -> html.Section:
    """Render the point map and its basemap control."""
    return card(
        text.MAP_TITLE,
        text.MAP_SUBTITLE,
        [
            graph("geo-map", height=540, map_view=True),
            html.P(id="map-caption", className="card-footnote", role="status"),
        ],
        class_name="map-card",
        extra=html.Div(
            [
                html.Label(
                    text.MAP_STYLE_LABEL,
                    htmlFor="map-style",
                    className="sr-only",
                ),
                dropdown(
                    "map-style",
                    options=[
                        {"label": label, "value": value}
                        for label, value in text.MAP_STYLE_OPTIONS
                    ],
                    value=DEFAULT_MAP_STYLE,
                    clearable=False,
                    searchable=False,
                ),
            ],
            className="map-style-field",
        ),
    )


def _distribution_card() -> html.Section:
    """Render the histogram, measure selector and quartile summary."""
    return card(
        text.DISTRIBUTION_TITLE,
        text.DISTRIBUTION_SUBTITLE,
        [
            html.Div(
                [
                    html.Label(
                        text.DISTRIBUTION_METRIC_LABEL,
                        htmlFor="distribution-metric",
                        className="sr-only",
                    ),
                    dropdown(
                        "distribution-metric",
                        options=[
                            {"label": label, "value": key}
                            for key, label in text.DISTRIBUTION_LABELS.items()
                        ],
                        value=DEFAULT_METRIC,
                        clearable=False,
                        searchable=False,
                    ),
                ],
                className="distribution-control",
            ),
            graph("distribution-figure", height=330),
            html.Div(id="distribution-summary", className="distribution-summary"),
            html.P(text.DISTRIBUTION_FOOTNOTE, className="card-footnote"),
            html.Div(
                [
                    html.P(text.GEOGRAPHY_NOTE_EYEBROW, className="eyebrow"),
                    html.P(text.GEOGRAPHY_NOTE_BODY),
                ],
                className="geography-note",
            ),
        ],
        class_name="distribution-card",
    )


def _trend_card() -> html.Section:
    """Render the monthly price series."""
    return card(
        text.TREND_TITLE,
        text.TREND_SUBTITLE,
        [
            graph("trend-figure"),
            html.P(text.TREND_FOOTNOTE, className="card-footnote"),
        ],
    )


def _comparison_card() -> html.Section:
    """Render the SVG comparison host and its captions."""
    return card(
        text.COMPARISON_TITLE,
        html.Span(text.COMPARISON_SUBTITLE, id="comparison-subtitle"),
        [
            dcc.Store(id="comparison-data"),
            html.Div(
                html.Div(id="comparison-plot"),
                className="comparison-scroll",
            ),
            html.P(id="comparison-note", className="card-footnote"),
        ],
    )


def _trajectories_card() -> html.Section:
    """Render the neighbourhood trajectories and city reference."""
    return card(
        text.TRAJECTORIES_TITLE,
        text.TRAJECTORIES_SUBTITLE,
        [
            graph("neighbourhood-figure", height=370),
            html.P(id="neighbourhood-caption", className="card-footnote"),
        ],
    )


def overview_panel() -> html.Div:
    """Build the overview tab panel."""
    return html.Div(
        [
            _overview_heading(),
            _kpi_strip(),
            html.Div([_map_card(), _distribution_card()], className="spatial-grid"),
            html.Div([_trend_card(), _comparison_card()], className="analysis-grid"),
            _trajectories_card(),
        ],
        id="overview-panel",
        className="view-panel",
    )
