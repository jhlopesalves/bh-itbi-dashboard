"""Dash interactions; the process shares source rows and caches small view results."""

from __future__ import annotations

from functools import lru_cache

import pandas as pd
from dash import Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from bh_itbi.analysis import (
    DEFAULT_NEIGHBOURHOODS,
    TYPE_LABELS,
    Filters,
    age_table,
    distance_table,
    distribution_quartiles,
    filter_transactions,
    heaping_summary,
    heaping_table,
    map_points,
    quantile_table,
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
    neighbourhood_comparison_figure,
    neighbourhood_trajectories_figure,
    number,
    tax_base_figure,
    temporal_figure,
)


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
    filters_inputs = [
        Input("property-type", "value"),
        Input("year-range", "value"),
        Input("neighbourhoods", "value"),
    ]

    @lru_cache(maxsize=16)
    def overview(filters: Filters, distribution_metric: str, map_style: str):
        selected = filter_transactions(frame, filters)
        city = filter_transactions(frame, filters.city_reference())
        points, map_stats = map_points(selected)
        values = summary(selected)
        comparison_names = filters.neighbourhoods or DEFAULT_NEIGHBOURHOODS
        comparison = selected.loc[selected["neighbourhood"].isin(comparison_names)]
        comparison_stats = quantile_table(comparison, ["neighbourhood"], minimum=15)
        comparison_fig = neighbourhood_comparison_figure(comparison_stats)
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
            comparison_fig,
            neighbourhood_trajectories_figure(comparison, city, filters),
            caption,
            {"height": int(comparison_fig.layout.height), "width": "100%"},
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
            Output("comparison-figure", "figure"),
            Output("neighbourhood-figure", "figure"),
            Output("neighbourhood-caption", "children"),
            Output("comparison-figure", "style"),
        ],
        *filters_inputs,
        Input("distribution-metric", "value"),
        Input("map-style", "value"),
    )
    def update_overview(property_type, years, neighbourhoods, metric, style):
        filters = Filters.from_controls(property_type, years, neighbourhoods)
        return overview(filters, metric, style)

    @app.callback(
        Output("property-type", "value"),
        Output("year-range", "value"),
        Output("neighbourhoods", "value"),
        Input("reset-filters", "n_clicks"),
        Input("geo-map", "clickData"),
        State("property-type", "value"),
        State("year-range", "value"),
        State("neighbourhoods", "value"),
        prevent_initial_call=True,
    )
    def select_neighbourhood_or_reset(_clicks, click_data, property_type, years, current):
        if ctx.triggered_id == "reset-filters":
            return "apartment", [2016, 2025], []
        filters = Filters.from_controls(property_type, years, [])
        available = set(filter_transactions(frame, filters)["neighbourhood"].dropna())
        selected = clicked_neighbourhood(click_data, available)
        if selected is None or current == [selected]:
            raise PreventUpdate
        return no_update, no_update, [selected]

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
