"""Dash interactions; the process shares source rows and caches small view results."""

from __future__ import annotations

from functools import lru_cache, wraps
from threading import Lock

import pandas as pd
from dash import ClientsideFunction, Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from bh_itbi.age import age_premiums
from bh_itbi.age_chart import age_chart_data, age_note, age_subtitle
from bh_itbi.config import (
    COMPARISON_RIDGE_LIMIT,
    DEFAULT_NEIGHBOURHOODS,
    RIDGE_MINIMUM,
)
from bh_itbi.diagnostics import (
    distance_table,
    heaping_summary,
    heaping_table,
    tax_base_table,
)
from bh_itbi.figures import (
    clusters_figure,
    distance_figure,
    distribution_figure,
    heaping_figure,
    hedonic_figure,
    map_figure,
    neighbourhood_comparison_data,
    neighbourhood_trajectories_figure,
    tax_base_figure,
    temporal_figure,
)
from bh_itbi.filters import Filters, filter_transactions
from bh_itbi.formatting import currency, number
from bh_itbi.overview import (
    distribution_quartiles,
    map_points,
    neighbourhood_price_distributions,
    summary,
)
from bh_itbi.text import (
    COMPARISON_INTERVAL_SUBTITLE,
    COMPARISON_SUBTITLE,
    DISTRIBUTION_EMPTY_SUMMARY,
    DISTRIBUTION_QUARTILE_LABELS,
    FILTER_NOTE_ACTIVE,
    FILTER_NOTE_MODELS,
    cluster_group_heading,
    comparison_caption,
    heaping_caption,
    kpi_coverage_note,
    kpi_coverage_value,
    period_text,
)
from bh_itbi.text import (
    comparison_note as format_comparison_note,
)
from bh_itbi.text import (
    map_caption as format_map_caption,
)
from bh_itbi.text import (
    scope_text as format_scope_text,
)
from bh_itbi.urls import decode_query, default_controls


def scope_text(filters: Filters) -> str:
    return format_scope_text(
        filters.property_type,
        filters.start_year,
        filters.end_year,
        filters.neighbourhoods,
    )


def clicked_neighbourhood(click_data: dict | None, available: set[str]) -> str | None:
    """Use the clicked record's source label, never infer a geographical boundary."""
    if not isinstance(click_data, dict):
        return None
    points = click_data.get("points")
    if not isinstance(points, list) or not points or not isinstance(points[0], dict):
        return None
    custom = points[0].get("customdata")
    if not isinstance(custom, list) or not custom:
        return None
    name = custom[0]
    return name if isinstance(name, str) and name in available else None


def register_callbacks(app, frame: pd.DataFrame, models: dict | None) -> None:
    view_lock = Lock()
    neighbourhood_options = set(frame["neighbourhood"].dropna())

    def serialise_view(callback):
        """Bound transaction intermediates while other threads serve light requests."""

        @wraps(callback)
        def guarded(*args, **kwargs):
            with view_lock:
                return callback(*args, **kwargs)

        return guarded

    filters_inputs = [
        Input("property-type", "value"),
        Input("year-range", "value"),
        Input("neighbourhoods", "value"),
    ]
    selection_inputs = [
        *filters_inputs,
        Input("distribution-metric", "value"),
        Input("map-style", "value"),
    ]

    # Location writes use pushState. A small clientside history bridge instead
    # replaces the current entry and reports only genuine browser navigation.
    # Keeping navigation separate from URL writes makes the callback graph acyclic.
    app.clientside_callback(
        ClientsideFunction(namespace="sharing", function_name="observeNavigation"),
        Output("url-navigation", "data"),
        Input("url-config", "data"),
    )
    app.clientside_callback(
        ClientsideFunction(namespace="sharing", function_name="updateUrl"),
        *selection_inputs,
        Input("url-ready", "data"),
        State("url-config", "data"),
    )
    app.clientside_callback(
        ClientsideFunction(namespace="comparison", function_name="update"),
        Input("comparison-data", "data"),
    )
    app.clientside_callback(
        ClientsideFunction(namespace="ageChart", function_name="update"),
        Input("age-data", "data"),
    )

    # Maps contain up to 8,000 hover records. Bound their retained memory rather
    # than keeping sixteen full sets of Plotly figures for arbitrary selections.
    @lru_cache(maxsize=2)
    def overview(filters: Filters, distribution_metric: str, map_style: str):
        selected = filter_transactions(frame, filters)
        city = (
            filter_transactions(frame, filters.city_reference())
            if filters.neighbourhoods
            else selected
        )
        points, map_stats = map_points(selected)
        values = summary(selected)
        comparison_names = filters.neighbourhoods or DEFAULT_NEIGHBOURHOODS
        comparison = selected.loc[selected["neighbourhood"].isin(comparison_names)]
        comparison_grid, comparison_rows = neighbourhood_price_distributions(comparison)
        comparison_data = neighbourhood_comparison_data(comparison_grid, comparison_rows, city)
        comparison_subtitle = (
            COMPARISON_INTERVAL_SUBTITLE
            if comparison_rows and not any(row.density is not None for row in comparison_rows)
            else COMPARISON_SUBTITLE
        )
        excluded = len(comparison_names) - len(comparison_rows)
        missing_ridge_curve = len(comparison_rows) <= COMPARISON_RIDGE_LIMIT and any(
            row.n >= RIDGE_MINIMUM and row.density is None for row in comparison_rows
        )
        show_interval_legend = comparison_subtitle == COMPARISON_SUBTITLE and any(
            row.density is None for row in comparison_rows
        )
        comparison_note = format_comparison_note(
            has_neighbourhood_filter=bool(filters.neighbourhoods),
            excluded=excluded,
            missing_ridge_curve=missing_ridge_curve,
            show_interval_legend=show_interval_legend,
        )
        map_caption = format_map_caption(map_stats["shown"], map_stats["screened"])
        quartiles = distribution_quartiles(selected, distribution_metric)
        if quartiles is not None:
            distribution_stats = [
                html.Div([html.Span(label), html.Strong(currency(value))])
                for label, value in zip(DISTRIBUTION_QUARTILE_LABELS, quartiles, strict=True)
            ]
        else:
            distribution_stats = html.P(DISTRIBUTION_EMPTY_SUMMARY)
        caption = comparison_caption(
            comparison_names, has_neighbourhood_filter=bool(filters.neighbourhoods)
        )
        return (
            map_figure(points, map_style),
            map_caption,
            number(values["n"]),
            currency(values["nominal"]),
            currency(values["real"]),
            kpi_coverage_value(values["geocoded"], values["n"]),
            kpi_coverage_note(values["geocoded"], values["n"]),
            scope_text(filters),
            temporal_figure(selected, city, filters),
            distribution_figure(selected, distribution_metric),
            distribution_stats,
            comparison_data,
            neighbourhood_trajectories_figure(comparison, city, filters),
            caption,
            comparison_note,
            comparison_subtitle,
        )

    @app.callback(
        [
            Output("geo-map", "figure"),
            Output("map-caption", "children"),
            Output("kpi-count", "children"),
            Output("kpi-nominal", "children"),
            Output("kpi-real", "children"),
            Output("kpi-coverage", "children"),
            Output("kpi-coverage-note", "children"),
            Output("scope-label", "children"),
            Output("trend-figure", "figure"),
            Output("distribution-figure", "figure"),
            Output("distribution-summary", "children"),
            Output("comparison-data", "data"),
            Output("neighbourhood-figure", "figure"),
            Output("neighbourhood-caption", "children"),
            Output("comparison-note", "children"),
            Output("comparison-subtitle", "children"),
        ],
        *selection_inputs,
    )
    @serialise_view
    def update_overview(property_type, years, neighbourhoods, metric, style):
        filters = Filters.from_controls(property_type, years, neighbourhoods)
        return overview(filters, metric, style)

    @app.callback(
        Output("property-type", "value"),
        Output("year-range", "value"),
        Output("neighbourhoods", "value"),
        Output("distribution-metric", "value"),
        Output("map-style", "value"),
        Output("url-ready", "data"),
        Input("url-navigation", "data"),
        Input("reset-filters", "n_clicks"),
        Input("geo-map", "clickData"),
        State("property-type", "value"),
        State("year-range", "value"),
        State("neighbourhoods", "value"),
    )
    def restore_selection(navigation, _clicks, click_data, property_type, years, current):
        if ctx.triggered_id == "reset-filters":
            return *default_controls(), True
        if ctx.triggered_id != "geo-map":
            if navigation is None:
                raise PreventUpdate
            return *decode_query(navigation["search"], neighbourhood_options), True
        filters = Filters.from_controls(property_type, years, [])
        available = set(filter_transactions(frame, filters)["neighbourhood"].dropna())
        selected = clicked_neighbourhood(click_data, available)
        if selected is None or current == [selected]:
            raise PreventUpdate
        return no_update, no_update, [selected], no_update, no_update, no_update

    @app.callback(Output("years-value", "children"), Input("year-range", "value"))
    def show_period(years):
        return period_text(int(years[0]), int(years[1]))

    @app.callback(
        Output("view-tabs", "data"),
        Input("tab-overview", "n_clicks"),
        Input("tab-diagnostics", "n_clicks"),
        Input("tab-models", "n_clicks"),
        prevent_initial_call=True,
    )
    def select_view(*_clicks):
        return ctx.triggered_id.removeprefix("tab-")

    @app.callback(
        Output("overview-panel", "className"),
        Output("diagnostics-panel", "className"),
        Output("models-panel", "className"),
        Output("filter-note", "children"),
        Output("property-type", "disabled"),
        Output("year-range", "disabled"),
        Output("neighbourhoods", "disabled"),
        Output("reset-filters", "disabled"),
        *[
            Output(f"tab-{name}", prop)
            for prop in ("className", "aria-selected", "tabIndex")
            for name in ("overview", "diagnostics", "models")
        ],
        Input("view-tabs", "data"),
    )
    def switch_view(tab):
        classes = [
            "view-panel" if tab == name else "view-panel is-hidden"
            for name in ("overview", "diagnostics", "models")
        ]
        fixed = tab == "models"
        note = FILTER_NOTE_MODELS if fixed else FILTER_NOTE_ACTIVE
        names = ("overview", "diagnostics", "models")
        tab_classes = [
            "view-tab view-tab-selected" if tab == name else "view-tab" for name in names
        ]
        selected = ["true" if tab == name else "false" for name in names]
        tab_indexes = [0 if tab == name else -1 for name in names]
        return *classes, note, fixed, fixed, fixed, fixed, *tab_classes, *selected, *tab_indexes

    @app.callback(
        Output("tax-figure", "figure"),
        Output("heaping-figure", "figure"),
        Output("age-data", "data"),
        Output("age-subtitle", "children"),
        Output("age-note", "children"),
        Output("distance-figure", "figure"),
        Output("heaping-caption", "children"),
        Output("diagnostic-scope", "children"),
        *filters_inputs,
        Input("view-tabs", "data"),
    )
    @serialise_view
    def update_diagnostics(property_type, years, neighbourhoods, tab):
        if tab != "diagnostics":
            raise PreventUpdate
        filters = Filters.from_controls(property_type, years, neighbourhoods)
        rows = filter_transactions(frame, filters)
        age = age_premiums(rows)
        heaping = heaping_table(rows)
        total, share = heaping_summary(heaping)
        caption = heaping_caption(total, share)
        return (
            tax_base_figure(tax_base_table(rows), filters),
            heaping_figure(heaping),
            age_chart_data(age),
            age_subtitle(filters, adjusted="adjusted" in age.table),
            age_note(age),
            distance_figure(distance_table(rows)),
            caption,
            scope_text(filters),
        )

    if models is not None:

        @app.callback(
            Output("hedonic-figure", "figure"),
            Output("clusters-figure", "figure"),
            Output("cluster-members", "children"),
            Input("cluster-group", "value"),
        )
        @serialise_view
        def update_models(group):
            group_id = None if group == "all" else int(group)
            members = models["members"].drop_duplicates(["neighbourhood", "group"])
            if group_id:
                members = members.loc[members["group"].eq(group_id)]
            content = [
                html.Div(
                    [
                        html.H3(cluster_group_heading(int(identifier), len(rows))),
                        html.P(
                            ", ".join(sorted(rows["neighbourhood"].astype(str).str.title()))
                        ),
                    ]
                )
                for identifier, rows in members.groupby("group", sort=True)
            ]
            return hedonic_figure(models["hedonic"]), clusters_figure(models, group_id), content

    app.clientside_callback(
        """function(tab) {
            window.setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 80);
            return tab;
        }""",
        Output("view-resize", "data"),
        Input("view-tabs", "data"),
        prevent_initial_call=True,
    )
