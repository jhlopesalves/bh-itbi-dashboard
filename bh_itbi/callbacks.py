"""Dash interactions; the process shares source rows and caches small view results."""

from __future__ import annotations

from functools import lru_cache, wraps
from threading import Lock

import pandas as pd
from dash import ClientsideFunction, Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from bh_itbi.analysis import (
    COMPARISON_RIDGE_LIMIT,
    DEFAULT_NEIGHBOURHOODS,
    RIDGE_MINIMUM,
    TYPE_LABELS,
    Filters,
    age_table,
    distance_table,
    distribution_quartiles,
    filter_transactions,
    heaping_summary,
    heaping_table,
    map_points,
    neighbourhood_price_distributions,
    summary,
    tax_base_table,
)
from bh_itbi.figures import (
    age_figure,
    clusters_figure,
    currency,
    distance_figure,
    distribution_figure,
    heaping_figure,
    hedonic_figure,
    map_figure,
    neighbourhood_comparison_data,
    neighbourhood_trajectories_figure,
    number,
    tax_base_figure,
    temporal_figure,
)
from bh_itbi.layout import COMPARISON_INTERVAL_SUBTITLE, COMPARISON_SUBTITLE
from bh_itbi.urls import decode_query, default_controls


def scope_text(filters: Filters) -> str:
    period = (
        str(filters.start_year)
        if filters.start_year == filters.end_year
        else f"{filters.start_year}–{filters.end_year}"
    )
    label = TYPE_LABELS.get(filters.property_type, "Apartamentos e casas")
    neighbourhood = (
        ", ".join(name.title() for name in filters.neighbourhoods) or "Toda a cidade"
    )
    return f"{label} · {period} · {neighbourhood}"


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
        comparison_note = (
            "A mediana da cidade inclui todos os bairros para o tipo de imóvel "
            "e o período selecionados."
        )
        if not filters.neighbourhoods:
            comparison_note += " Sem seleção, exibem-se cinco bairros de referência."
        if excluded == 1:
            comparison_note += " 1 bairro com menos de 15 transações não exibido."
        elif excluded:
            comparison_note += (
                f" {number(excluded)} bairros com menos de 15 transações não exibidos."
            )
        if len(comparison_rows) <= COMPARISON_RIDGE_LIMIT and any(
            row.n >= RIDGE_MINIMUM and row.density is None for row in comparison_rows
        ):
            comparison_note += (
                " Curvas indisponíveis na escala comum de densidade "
                "são exibidas como intervalos."
            )
        if comparison_subtitle == COMPARISON_SUBTITLE and any(
            row.density is None for row in comparison_rows
        ):
            comparison_note += (
                " Nos resumos, o ponto marca a mediana e a faixa clara cobre P10–P90."
            )
        map_caption = (
            f"{number(map_stats['shown'])} pontos de {number(map_stats['screened'])} "
            "registros entre P2 e P98, após exigir localização de face e área positiva. "
            "Amostra de até 8.000 pontos; os indicadores usam todo o recorte elegível."
        )
        quartiles = distribution_quartiles(selected, distribution_metric)
        if quartiles is not None:
            distribution_stats = [
                html.Div([html.Span(label), html.Strong(currency(value))])
                for label, value in zip(["P25", "Mediana", "P75"], quartiles, strict=True)
            ]
        else:
            distribution_stats = html.P("Amostra insuficiente para resumir esta distribuição.")
        caption = (
            "Comparação: "
            + ", ".join(name.title() for name in comparison_names)
            + ". "
            + (
                "Os bairros selecionados também filtram o mapa e o resumo. "
                if filters.neighbourhoods
                else "Sem filtro de bairro, exibem-se cinco bairros de referência. "
            )
            + "A referência de Belo Horizonte preserva tipo e período, sem filtro geográfico."
        )
        return (
            map_figure(points, map_style),
            map_caption,
            number(values["n"]),
            currency(values["nominal"]),
            currency(values["real"]),
            f"{number(100 * values['geocoded'] / values['n'], 1)}%" if values["n"] else "—",
            f"{number(values['geocoded'])} de {number(values['n'])} registros",
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
        return str(years[0]) if years[0] == years[1] else f"{years[0]}–{years[1]}"

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
        note = (
            "Índices estimados sobre populações fixas de 2016–2025; "
            "os filtros não se aplicam a esta seção."
            if fixed
            else "Filtros aplicados ao panorama e aos diagnósticos."
        )
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
        Output("age-figure", "figure"),
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
        heaping = heaping_table(rows)
        total, share = heaping_summary(heaping)
        caption = (
            f"{number(total)} registros nesta janela; {number(share * 100, 1)}% em faixas "
            "centradas em múltiplos de R$ 50 mil. A faixa inclui valores próximos ao múltiplo; "
            "não é a proporção de valores exatamente redondos."
            if total >= 5
            else "Sem amostra suficiente para este diagnóstico no recorte ativo."
        )
        return (
            tax_base_figure(tax_base_table(rows), filters),
            heaping_figure(heaping),
            age_figure(age_table(rows)),
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
                        html.H3(f"Grupo {int(identifier)} · {len(rows)} bairros"),
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
