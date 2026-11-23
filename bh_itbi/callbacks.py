"""Dash callback wiring, LRU view caching and thread-safe serialisation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from functools import lru_cache, wraps
from threading import Lock
from typing import Protocol, TypedDict

import pandas as pd
import plotly.graph_objects as go
from dash import ClientsideFunction, Dash, Input, NoUpdate, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from bh_itbi.figures import (
    AgeChart,
    ComparisonPlot,
    age_chart_data,
    distance_figure,
    distribution_figure,
    heaping_figure,
    hedonic_figure,
    map_figure,
    neighbourhood_comparison_data,
    neighbourhood_trajectories_figure,
    tax_base_figure,
    temporal_figure,
    trajectories_figure,
)
from bh_itbi.filters import Filters
from bh_itbi.layout.overview import distribution_summary
from bh_itbi.models import PreparedModels
from bh_itbi.text.shared import TAB_LABELS, period_text
from bh_itbi.urls import decode_query, default_controls
from bh_itbi.views import (
    build_diagnostics_view,
    build_overview_view,
    build_tab_view,
)
from bh_itbi.views.overview import selection_from_map


class _ViewSerialiser(Protocol):
    """A decorator that preserves each callback's own input and output types."""

    def __call__[**P, R](self, callback: Callable[P, R], /) -> Callable[P, R]: ...


class Navigation(TypedDict):
    """Only the query string of the browser history event affects the server."""

    search: str | None


type SelectionOutput = (
    tuple[str, list[int], list[str], str, str, bool]
    | tuple[NoUpdate, NoUpdate, list[str], NoUpdate, NoUpdate, NoUpdate]
)
type OverviewOutput = dict[str, str | go.Figure | ComparisonPlot | list[html.Div] | html.P]
type DiagnosticsOutput = dict[str, str | go.Figure | AgeChart]
type ModelsOutput = dict[str, go.Figure]

FILTERS_INPUTS: tuple[Input, ...] = (
    Input("property-type", "value"),
    Input("year-range", "value"),
    Input("neighbourhoods", "value"),
)
SELECTION_INPUTS: tuple[Input, ...] = (
    *FILTERS_INPUTS,
    Input("distribution-metric", "value"),
    Input("map-style", "value"),
)

OVERVIEW_OUTPUTS: dict[str, Output] = {
    "geo_map": Output("geo-map", "figure"),
    "map_caption": Output("map-caption", "children"),
    "kpi_count": Output("kpi-count", "children"),
    "kpi_nominal": Output("kpi-nominal", "children"),
    "kpi_real": Output("kpi-real", "children"),
    "kpi_coverage": Output("kpi-coverage", "children"),
    "kpi_coverage_note": Output("kpi-coverage-note", "children"),
    "scope_label": Output("scope-label", "children"),
    "trend_figure": Output("trend-figure", "figure"),
    "distribution_figure": Output("distribution-figure", "figure"),
    "distribution_summary": Output("distribution-summary", "children"),
    "comparison_data": Output("comparison-data", "data"),
    "neighbourhood_figure": Output("neighbourhood-figure", "figure"),
    "neighbourhood_caption": Output("neighbourhood-caption", "children"),
    "comparison_note": Output("comparison-note", "children"),
    "comparison_subtitle": Output("comparison-subtitle", "children"),
}

DIAGNOSTICS_OUTPUTS: dict[str, Output] = {
    "tax_figure": Output("tax-figure", "figure"),
    "heaping_figure": Output("heaping-figure", "figure"),
    "age_data": Output("age-data", "data"),
    "age_subtitle": Output("age-subtitle", "children"),
    "age_note": Output("age-note", "children"),
    "distance_figure": Output("distance-figure", "figure"),
    "heaping_caption": Output("heaping-caption", "children"),
    "diagnostic_scope": Output("diagnostic-scope", "children"),
}

MODELS_OUTPUTS: dict[str, Output] = {
    "hedonic_figure": Output("hedonic-figure", "figure"),
    "trajectories_figure": Output("trajectories-figure", "figure"),
}

TAB_PROPERTIES = {"class": "className", "selected": "aria-selected", "index": "tabIndex"}
TAB_NAMES = tuple(name for name, _ in TAB_LABELS)
SWITCH_VIEW_OUTPUTS: dict[str, Output] = {
    "overview_panel_class": Output("overview-panel", "className"),
    "diagnostics_panel_class": Output("diagnostics-panel", "className"),
    "models_panel_class": Output("models-panel", "className"),
    "filter_note": Output("filter-note", "children"),
    "property_type_disabled": Output("property-type", "disabled"),
    "year_range_disabled": Output("year-range", "disabled"),
    "neighbourhoods_disabled": Output("neighbourhoods", "disabled"),
    "reset_filters_disabled": Output("reset-filters", "disabled"),
    **{
        f"tab_{name}_{key}": Output(f"tab-{name}", prop)
        for key, prop in TAB_PROPERTIES.items()
        for name in TAB_NAMES
    },
}


def _register_clientside_callbacks(app: Dash) -> None:
    """Wire browser history and custom SVG renderers without server round-trips."""
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
        *SELECTION_INPUTS,
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


def _register_selection_callbacks(
    app: Dash, frame: pd.DataFrame, neighbourhood_options: set[str]
) -> None:
    """Register selection updates from navigation, reset and map clicks."""

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
    def restore_selection(
        navigation: Navigation | None,
        _clicks: int | None,
        click_data: Mapping[str, object] | None,
        property_type: str | None,
        years: Sequence[int] | None,
        current: Sequence[str] | None,
    ) -> SelectionOutput:
        if ctx.triggered_id == "reset-filters":
            return *default_controls(), True
        if ctx.triggered_id != "geo-map":
            if navigation is None:
                raise PreventUpdate
            return *decode_query(navigation["search"], neighbourhood_options), True
        filters = Filters.from_controls(property_type, years, [])
        selection = selection_from_map(frame, filters, click_data, current)
        if selection is None:
            raise PreventUpdate
        return no_update, no_update, selection, no_update, no_update, no_update

    @app.callback(Output("years-value", "children"), Input("year-range", "value"))
    def show_period(years: Sequence[int]) -> str:
        return period_text(int(years[0]), int(years[1]))


def _register_tab_callbacks(app: Dash) -> None:
    """Register tab selection and synchronise panel, ARIA and filter state."""

    @app.callback(
        Output("view-tabs", "data"),
        Input("tab-overview", "n_clicks"),
        Input("tab-diagnostics", "n_clicks"),
        Input("tab-models", "n_clicks"),
        prevent_initial_call=True,
    )
    def select_view(*_clicks: int | None) -> str:
        return str(ctx.triggered_id).removeprefix("tab-")

    @app.callback(SWITCH_VIEW_OUTPUTS, Input("view-tabs", "data"))
    def switch_view(tab: str) -> dict[str, str | bool | int]:
        view = build_tab_view(tab)
        attributes = {
            "class": view.tab_classes,
            "selected": view.tab_selected,
            "index": view.tab_indexes,
        }
        return {
            "overview_panel_class": view.panel_classes["overview"],
            "diagnostics_panel_class": view.panel_classes["diagnostics"],
            "models_panel_class": view.panel_classes["models"],
            "filter_note": view.filter_note,
            "property_type_disabled": view.filters_disabled,
            "year_range_disabled": view.filters_disabled,
            "neighbourhoods_disabled": view.filters_disabled,
            "reset_filters_disabled": view.filters_disabled,
            **{
                f"tab_{name}_{key}": values[name]
                for key, values in attributes.items()
                for name in TAB_NAMES
            },
        }


def _view_serialiser(view_lock: Lock) -> _ViewSerialiser:
    """Share one lock across callbacks that hold transaction intermediates."""

    def serialise_view[**P, R](callback: Callable[P, R]) -> Callable[P, R]:
        """Bound transaction intermediates while other threads serve light requests."""

        @wraps(callback)
        def guarded(*args: P.args, **kwargs: P.kwargs) -> R:
            with view_lock:
                return callback(*args, **kwargs)

        return guarded

    return serialise_view


def _register_overview_callback(
    app: Dash, frame: pd.DataFrame, serialise_view: _ViewSerialiser
) -> None:
    """Register the overview with a bounded cache of rendered selections."""

    # Maps contain up to 8,000 hover records. Bound their retained memory rather
    # than keeping sixteen full sets of Plotly figures for arbitrary selections.
    @lru_cache(maxsize=2)
    def overview(filters: Filters, distribution_metric: str, map_style: str) -> OverviewOutput:
        view = build_overview_view(frame, filters, distribution_metric)
        return {
            "geo_map": map_figure(view.points, map_style),
            "map_caption": view.map_caption,
            "kpi_count": view.kpi_count,
            "kpi_nominal": view.kpi_nominal,
            "kpi_real": view.kpi_real,
            "kpi_coverage": view.kpi_coverage,
            "kpi_coverage_note": view.kpi_coverage_note,
            "scope_label": view.scope_label,
            "trend_figure": temporal_figure(view.selected, view.city, filters),
            "distribution_figure": distribution_figure(view.selected, distribution_metric),
            "distribution_summary": distribution_summary(view.quartiles),
            "comparison_data": neighbourhood_comparison_data(
                view.comparison_grid, view.comparison_rows, view.city, filters.neighbourhoods
            ),
            "neighbourhood_figure": neighbourhood_trajectories_figure(
                view.comparison, view.city, filters
            ),
            "neighbourhood_caption": view.neighbourhood_caption,
            "comparison_note": view.comparison_note,
            "comparison_subtitle": view.comparison_subtitle,
        }

    @app.callback(OVERVIEW_OUTPUTS, *SELECTION_INPUTS)
    @serialise_view
    def update_overview(
        property_type: str | None,
        years: Sequence[int] | None,
        neighbourhoods: Sequence[str] | None,
        metric: str,
        style: str,
    ) -> OverviewOutput:
        filters = Filters.from_controls(property_type, years, neighbourhoods)
        return overview(filters, metric, style)


def _register_diagnostics_callback(
    app: Dash, frame: pd.DataFrame, serialise_view: _ViewSerialiser
) -> None:
    """Compute diagnostics on demand when their tab is active."""

    @app.callback(DIAGNOSTICS_OUTPUTS, *FILTERS_INPUTS, Input("view-tabs", "data"))
    @serialise_view
    def update_diagnostics(
        property_type: str | None,
        years: Sequence[int] | None,
        neighbourhoods: Sequence[str] | None,
        tab: str,
    ) -> DiagnosticsOutput:
        if tab != "diagnostics":
            raise PreventUpdate
        filters = Filters.from_controls(property_type, years, neighbourhoods)
        view = build_diagnostics_view(frame, filters)
        return {
            "tax_figure": tax_base_figure(view.tax_base, filters),
            "heaping_figure": heaping_figure(view.heaping),
            "age_data": age_chart_data(view.age),
            "age_subtitle": view.age_subtitle,
            "age_note": view.age_note,
            "distance_figure": distance_figure(view.distance),
            "heaping_caption": view.heaping_caption,
            "diagnostic_scope": view.diagnostic_scope,
        }


def _register_models_callback(
    app: Dash, models: PreparedModels, serialise_view: _ViewSerialiser
) -> None:
    """Register the fixed-population index and neighbourhood figures."""

    @app.callback(MODELS_OUTPUTS, Input("view-tabs", "data"))
    @serialise_view
    def update_models(_tab: str) -> ModelsOutput:
        return {
            "hedonic_figure": hedonic_figure(models.hedonic),
            "trajectories_figure": trajectories_figure(models),
        }


def _register_resize_callback(app: Dash) -> None:
    """Resize the browser charts after their tab becomes visible."""
    app.clientside_callback(
        """function(tab) {
            window.setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 80);
            return tab;
        }""",
        Output("view-resize", "data"),
        Input("view-tabs", "data"),
        prevent_initial_call=True,
    )


def register_callbacks(app: Dash, frame: pd.DataFrame, models: PreparedModels | None) -> None:
    """Register all client and server callbacks on the Dash application."""
    serialise_view = _view_serialiser(Lock())
    neighbourhood_options = set(frame["neighbourhood"].dropna())

    _register_clientside_callbacks(app)
    _register_overview_callback(app, frame, serialise_view)
    _register_selection_callbacks(app, frame, neighbourhood_options)
    _register_tab_callbacks(app)
    _register_diagnostics_callback(app, frame, serialise_view)
    if models is not None:
        _register_models_callback(app, models, serialise_view)
    _register_resize_callback(app)
