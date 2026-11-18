"""Portuguese editorial layout; analytical content is supplied by callbacks."""

from __future__ import annotations

from dash import dcc, html

from bh_itbi import text
from bh_itbi.config import (
    CLUSTER_K,
    SOURCE_BLOB_URL,
    SOURCE_URL,
    YEAR_TICKS,
    YEARS,
)
from bh_itbi.formatting import number
from bh_itbi.models import COMPOSITION_TERMS
from bh_itbi.text import (
    COMPARISON_INTERVAL_SUBTITLE,
    COMPARISON_SUBTITLE,
    DROPDOWN_LABELS,
    hedonic_note,
)
from bh_itbi.theme import CLUSTER_COLORS, TEAL, empty_figure
from bh_itbi.urls import DEFAULT_MAP_STYLE, DEFAULT_METRIC, QUERY_OPTIONS, default_controls

__all__ = [
    "COMPARISON_INTERVAL_SUBTITLE",
    "COMPARISON_SUBTITLE",
    "DROPDOWN_LABELS",
    "GRAPH_CONFIG",
    "build_layout",
    "card",
    "diagnostics_panel",
    "dropdown",
    "graph",
    "hedonic_note",
    "methodology",
    "metric",
    "models_panel",
    "overview_panel",
]

GRAPH_CONFIG = {
    "displaylogo": False,
    "locale": "pt-BR",
    "responsive": True,
    "scrollZoom": False,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d", "sendChartToCloud"],
    "toImageButtonOptions": {"format": "png", "scale": 2, "filename": "mercado-residencial-bh"},
}


def dropdown(identifier: str, **kwargs):
    return dcc.Dropdown(
        id=identifier, className="control-dropdown", labels=DROPDOWN_LABELS, **kwargs
    )


def graph(identifier: str, *, height=360, map_view=False):
    """Give Plotly an explicit frame to avoid percentage-height cycles in a grid."""
    config = GRAPH_CONFIG | ({"scrollZoom": True} if map_view else {})
    return dcc.Graph(
        id=identifier,
        figure=empty_figure(text.LOADING_MESSAGE, height),
        config=config,
        responsive=True,
        className="plot",
        style={"height": height, "width": "100%"},
    )


def card(title, subtitle, body, *, class_name="", extra=None):
    """Keep the body flat: Dash does not resolve nested lists of components."""
    return html.Section(
        [
            html.Div(
                [
                    html.Div([html.H2(title), html.P(subtitle, className="chart-subtitle")]),
                    extra,
                ],
                className="card-heading",
            ),
            *(body if isinstance(body, list) else [body]),
        ],
        className=f"chart-card {class_name}",
    )


def metric(label, identifier, unit, note=None):
    return html.Div(
        [
            html.P(label, className="metric-label"),
            html.Div("—", id=identifier, className="metric-value"),
            html.P(unit, className="metric-unit"),
            html.P(note, className="metric-note") if note else None,
        ],
        className="metric",
    )


def overview_panel():
    return html.Div(
        [
            html.Div(
                [
                    html.P(text.OVERVIEW_EYEBROW, className="eyebrow"),
                    html.P(
                        id="scope-label",
                        className="scope-label",
                        role="status",
                        **{"aria-live": "polite"},
                    ),
                ],
                className="section-line",
            ),
            html.Div(
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
            ),
            html.Div(
                [
                    card(
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
                    ),
                    card(
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
                            html.Div(
                                id="distribution-summary", className="distribution-summary"
                            ),
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
                    ),
                ],
                className="spatial-grid",
            ),
            html.Div(
                [
                    card(
                        text.TREND_TITLE,
                        text.TREND_SUBTITLE,
                        [
                            graph("trend-figure"),
                            html.P(text.TREND_FOOTNOTE, className="card-footnote"),
                        ],
                    ),
                    card(
                        text.COMPARISON_TITLE,
                        html.Span(COMPARISON_SUBTITLE, id="comparison-subtitle"),
                        [
                            dcc.Store(id="comparison-data"),
                            html.Div(
                                html.Div(id="comparison-plot"),
                                className="comparison-scroll",
                            ),
                            html.P(id="comparison-note", className="card-footnote"),
                        ],
                    ),
                ],
                className="analysis-grid",
            ),
            card(
                text.TRAJECTORIES_TITLE,
                text.TRAJECTORIES_SUBTITLE,
                [
                    graph("neighbourhood-figure", height=370),
                    html.P(id="neighbourhood-caption", className="card-footnote"),
                ],
            ),
        ],
        id="overview-panel",
        className="view-panel",
    )


def diagnostics_panel():
    return html.Div(
        [
            html.Div(
                [
                    html.P(text.DIAGNOSTICS_EYEBROW, className="eyebrow"),
                    html.P(text.DIAGNOSTICS_DESCRIPTION, className="section-description"),
                ],
                className="section-intro",
            ),
            html.P(id="diagnostic-scope", className="scope-banner", role="status"),
            html.Div(
                [
                    card(
                        text.TAX_TITLE,
                        text.TAX_SUBTITLE,
                        [
                            graph("tax-figure"),
                            html.P(text.TAX_FOOTNOTE, className="card-footnote"),
                        ],
                    ),
                    card(
                        text.HEAPING_TITLE,
                        text.HEAPING_SUBTITLE,
                        [
                            graph("heaping-figure"),
                            html.P(id="heaping-caption", className="card-footnote"),
                        ],
                    ),
                    card(
                        text.AGE_TITLE,
                        html.Span(id="age-subtitle"),
                        [
                            dcc.Store(id="age-data"),
                            html.Div(
                                html.P(text.LOADING_MESSAGE, className="comparison-empty"),
                                id="age-plot",
                            ),
                            html.P(id="age-note", className="card-footnote"),
                        ],
                        class_name="age-card",
                    ),
                    card(
                        text.DISTANCE_TITLE,
                        text.DISTANCE_SUBTITLE,
                        [
                            graph("distance-figure"),
                            html.P(text.DISTANCE_FOOTNOTE, className="card-footnote"),
                        ],
                    ),
                ],
                className="diagnostics-grid",
            ),
        ],
        id="diagnostics-panel",
        className="view-panel is-hidden",
    )


def models_panel(models):
    if models is None:
        content = html.P(text.MODELS_UNAVAILABLE_BANNER, className="scope-banner")
    else:
        metadata = models["metadata"]
        hedonic = metadata["hedonic"]
        clusters = metadata["clusters"]
        final = models["hedonic"].iloc[-1]
        content = [
            html.Div(
                [
                    html.P(text.MODELS_EYEBROW, className="eyebrow"),
                    html.H2(text.MODELS_SECTION_TITLE, className="section-title"),
                    html.P(text.MODELS_DESCRIPTION, className="section-description"),
                ],
                className="section-intro",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Strong(number(hedonic["n"])),
                            html.Span(text.MODEL_METRIC_OBSERVATIONS),
                        ]
                    ),
                    html.Div(
                        [
                            html.Strong(number(hedonic["neighbourhoods"])),
                            html.Span(text.MODEL_METRIC_NEIGHBOURHOODS),
                        ]
                    ),
                    html.Div(
                        [
                            html.Strong(number(hedonic["r_squared"], 3)),
                            html.Span(text.MODEL_METRIC_R2),
                        ]
                    ),
                ],
                className="model-metrics",
            ),
            card(
                text.HEDONIC_TITLE,
                text.HEDONIC_SUBTITLE,
                [
                    graph("hedonic-figure", height=420),
                    html.P(
                        hedonic_note({group: final[group] for group in COMPOSITION_TERMS}),
                        className="card-footnote",
                    ),
                ],
            ),
            card(
                text.CLUSTERS_TITLE,
                text.clusters_subtitle(clusters["n_neighbourhoods"]),
                [
                    graph("clusters-figure", height=410),
                    html.P(
                        text.clusters_footnote(clusters["silhouettes"][str(CLUSTER_K)]),
                        className="card-footnote",
                    ),
                    html.Details(
                        [
                            html.Summary(text.CLUSTERS_MEMBERS_SUMMARY),
                            html.Div(id="cluster-members", className="members-list"),
                        ],
                        className="members-details",
                    ),
                ],
                extra=html.Div(
                    [
                        html.Label(
                            text.CLUSTER_GROUP_LABEL,
                            htmlFor="cluster-group",
                            className="sr-only",
                        ),
                        dropdown(
                            "cluster-group",
                            options=[
                                {"label": text.CLUSTER_ALL_GROUPS_LABEL, "value": "all"},
                                *[
                                    {
                                        "label": html.Span(
                                            [
                                                html.Span(
                                                    className="cluster-option-swatch",
                                                    style={"backgroundColor": colour},
                                                    **{"aria-hidden": "true"},
                                                ),
                                                f"Grupo {group}",
                                            ],
                                            className="cluster-option",
                                        ),
                                        "value": str(group),
                                    }
                                    for group, colour in CLUSTER_COLORS.items()
                                ],
                            ],
                            value="all",
                            clearable=False,
                            searchable=False,
                        ),
                    ],
                    className="cluster-field",
                ),
            ),
        ]
    return html.Div(content, id="models-panel", className="view-panel is-hidden")


def methodology():
    return html.Details(
        [
            html.Summary(text.METHODOLOGY_SUMMARY),
            html.Div(
                [
                    html.Div(
                        [
                            html.H3(text.METHODOLOGY_OBSERVED_HEADING),
                            html.P(text.METHODOLOGY_OBSERVED_P1),
                            html.P(text.METHODOLOGY_OBSERVED_P2),
                        ]
                    ),
                    html.Div(
                        [
                            html.H3(text.METHODOLOGY_TIME_HEADING),
                            html.P(text.METHODOLOGY_TIME_P1),
                            html.P(text.METHODOLOGY_TIME_P2),
                        ]
                    ),
                    html.Div(
                        [
                            html.H3(text.METHODOLOGY_GEO_HEADING),
                            html.P(text.METHODOLOGY_GEO_P1),
                            html.P(
                                [
                                    text.METHODOLOGY_GEO_P2_PREFIX,
                                    html.A(
                                        text.METHODOLOGY_DICTIONARY_LINK,
                                        href=f"{SOURCE_BLOB_URL}/DATA_DICTIONARY.md",
                                        target="_blank",
                                        rel="noopener noreferrer",
                                    ),
                                    " · ",
                                    html.A(
                                        text.METHODOLOGY_VERSION_LINK,
                                        href=f"{SOURCE_BLOB_URL}/README.md",
                                        target="_blank",
                                        rel="noopener noreferrer",
                                    ),
                                ]
                            ),
                        ]
                    ),
                ],
                className="methodology-grid",
            ),
        ],
        id="metodologia",
        className="methodology",
    )


def build_layout(neighbourhoods: list[str], models: dict | None, raw_rows: int):
    return html.Div(
        [
            dcc.Store(id="url-navigation"),
            dcc.Store(id="url-ready", data=False),
            dcc.Store(
                id="url-config",
                data={"options": QUERY_OPTIONS, "defaults": default_controls()},
            ),
            html.A(text.SKIP_LINK_TEXT, href="#conteudo", className="skip-link"),
            html.Header(
                [
                    html.Div(
                        [
                            html.Span(text.MASTHEAD_EYEBROW, className="eyebrow"),
                            html.A(
                                text.MASTHEAD_ABOUT_LINK,
                                href="#metodologia",
                                className="about-link",
                            ),
                        ],
                        className="masthead-top",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H1(text.APP_TITLE),
                                    html.P(text.APP_SUBTITLE, className="subtitle"),
                                ],
                                className="masthead-title",
                            ),
                            html.Div(
                                [
                                    html.P(text.MASTHEAD_META_LABEL, className="meta-label"),
                                    html.Dl(
                                        [
                                            html.Dt(text.MASTHEAD_PERIOD_DT),
                                            html.Dd(text.MASTHEAD_PERIOD_DD),
                                            html.Dt(text.MASTHEAD_ROWS_DT),
                                            html.Dd(number(raw_rows)),
                                            html.Dt(text.MASTHEAD_REAL_DT),
                                            html.Dd(text.MASTHEAD_REAL_DD),
                                        ],
                                        className="masthead-facts",
                                    ),
                                ],
                                className="masthead-meta",
                            ),
                        ],
                        className="masthead-main",
                    ),
                ],
                className="masthead",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label(
                                        text.PROPERTY_TYPE_LABEL,
                                        htmlFor="property-type",
                                        id="property-type-label",
                                    ),
                                    dropdown(
                                        "property-type",
                                        options=[
                                            {
                                                "label": text.TYPE_LABELS["apartment"],
                                                "value": "apartment",
                                            },
                                            {
                                                "label": text.TYPE_LABELS["house"],
                                                "value": "house",
                                            },
                                            {
                                                "label": text.ALL_TYPES_LABEL,
                                                "value": "all",
                                            },
                                        ],
                                        value="all",
                                        clearable=False,
                                        searchable=False,
                                    ),
                                ],
                                className="filter-field type-field",
                                role="group",
                                **{"aria-labelledby": "property-type-label"},
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Label(text.PERIOD_LABEL, id="years-label"),
                                            html.Span(
                                                text.MASTHEAD_PERIOD_DD,
                                                id="years-value",
                                                className="period-value",
                                            ),
                                        ],
                                        className="period-heading",
                                    ),
                                    dcc.RangeSlider(
                                        id="year-range",
                                        min=YEARS[0],
                                        max=YEARS[-1],
                                        step=1,
                                        value=[YEARS[0], YEARS[-1]],
                                        allowCross=False,
                                        marks={y: str(y) for y in YEARS if y in YEAR_TICKS},
                                        tooltip={
                                            "placement": "bottom",
                                            "always_visible": False,
                                        },
                                        updatemode="mouseup",
                                        allow_direct_input=False,
                                    ),
                                ],
                                className="filter-field years-field",
                                role="group",
                                **{"aria-labelledby": "years-label"},
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        text.NEIGHBOURHOODS_LABEL,
                                        htmlFor="neighbourhoods",
                                        id="neighbourhoods-label",
                                    ),
                                    dropdown(
                                        "neighbourhoods",
                                        options=[
                                            {"label": name.title(), "value": name}
                                            for name in neighbourhoods
                                        ],
                                        value=[],
                                        multi=True,
                                        placeholder=text.ALL_NEIGHBOURHOODS_LABEL,
                                        clearable=True,
                                    ),
                                ],
                                className="filter-field neighbourhood-field",
                                role="group",
                                **{"aria-labelledby": "neighbourhoods-label"},
                            ),
                            html.Button(
                                text.RESET_FILTERS_LABEL,
                                id="reset-filters",
                                className="button button-quiet reset-button",
                            ),
                        ],
                        id="filter-controls",
                        className="filters",
                    ),
                    html.P(
                        text.FILTER_NOTE_ACTIVE,
                        id="filter-note",
                        className="filter-note",
                        role="status",
                    ),
                ],
                className="filter-area",
            ),
            html.Div(
                [
                    html.Button(
                        label,
                        id=f"tab-{name}",
                        role="tab",
                        className="view-tab view-tab-selected"
                        if name == "overview"
                        else "view-tab",
                        tabIndex=0 if name == "overview" else -1,
                        **{
                            "aria-selected": "true" if name == "overview" else "false",
                            "aria-controls": f"{name}-panel",
                        },
                    )
                    for name, label in text.TAB_LABELS
                ],
                className="view-tabs view-tabs-parent",
                role="tablist",
                **{"aria-label": text.TABLIST_ARIA_LABEL},
            ),
            dcc.Store(id="view-tabs", data="overview"),
            html.Main(
                [
                    dcc.Loading(
                        overview_panel(),
                        type="circle",
                        color=TEAL,
                        delay_show=250,
                        delay_hide=80,
                    ),
                    dcc.Loading(
                        diagnostics_panel(),
                        type="circle",
                        color=TEAL,
                        delay_show=250,
                        delay_hide=80,
                    ),
                    models_panel(models),
                ],
                id="conteudo",
            ),
            methodology(),
            html.Footer(
                [
                    html.Span(text.FOOTER_BRAND, className="footer-brand"),
                    html.P(text.FOOTER_PROVENANCE),
                    html.A(
                        text.FOOTER_SOURCE_LINK,
                        href=SOURCE_URL,
                        target="_blank",
                        rel="noopener noreferrer",
                    ),
                ],
                className="footer",
            ),
            dcc.Store(id="view-resize"),
        ],
        className="app-shell",
    )
