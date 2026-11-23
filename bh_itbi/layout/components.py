"""Reusable Dash layout primitives: cards, metrics, graph frames and dropdowns."""

from __future__ import annotations

from typing import Any, TypedDict, Unpack, cast

from dash import dcc, html
from dash.development.base_component import Component

from bh_itbi.text import shared as text
from bh_itbi.theme import empty_figure

GRAPH_CONFIG: dcc.Graph.Config = {
    "displaylogo": False,
    "locale": "pt-BR",
    "responsive": True,
    "scrollZoom": False,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d", "sendChartToCloud"],
    "toImageButtonOptions": {"format": "png", "scale": 2, "filename": "mercado-residencial-bh"},
}


class DropdownOption(TypedDict):
    """Label and value rendered by a dashboard dropdown."""

    label: str | Component
    value: str


class DropdownSettings(TypedDict, total=False):
    """Dropdown properties that vary across dashboard controls."""

    options: list[DropdownOption]
    value: str | list[str]
    clearable: bool
    searchable: bool
    multi: bool
    placeholder: str


def html_attributes(**values: str) -> dict[str, Any]:
    """Spell Dash's runtime aria-* and data-* properties omitted by its type hints."""
    return {name.replace("_", "-"): value for name, value in values.items()}


def dropdown(identifier: str, **settings: Unpack[DropdownSettings]) -> dcc.Dropdown:
    """Build a styled Dash dropdown with standard Portuguese control labels."""
    # The copy module has no Dash dependency. Its keys mirror Dash's Labels schema.
    labels = cast(dcc.Dropdown.Labels, text.DROPDOWN_LABELS)
    return dcc.Dropdown(id=identifier, className="control-dropdown", labels=labels, **settings)


def graph(identifier: str, *, height: int = 360, map_view: bool = False) -> dcc.Graph:
    """Give Plotly an explicit frame to avoid percentage-height cycles in a grid."""
    config = GRAPH_CONFIG.copy()
    if map_view:
        config["scrollZoom"] = True
    return dcc.Graph(
        id=identifier,
        figure=empty_figure(text.LOADING_MESSAGE, height),
        config=config,
        responsive=True,
        className="plot",
        style={"height": height, "width": "100%"},
    )


def card(
    title: str,
    subtitle: str | Component,
    body: Component | list[Component],
    *,
    class_name: str = "",
    extra: Component | None = None,
) -> html.Section:
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


def metric(
    label: str, identifier: str, unit: str | Component, note: str | None = None
) -> html.Div:
    """Render one headline KPI block in the overview statistical summary."""
    return html.Div(
        [
            html.P(label, className="metric-label"),
            html.Div("—", id=identifier, className="metric-value"),
            html.P(unit, className="metric-unit"),
            html.P(note, className="metric-note") if note else None,
        ],
        className="metric",
    )


def boxed_note(eyebrow: str, body: str | list[str | Component]) -> html.Div:
    """Render a short qualification beneath a figure and its footnote."""
    return html.Div(
        [html.P(eyebrow, className="eyebrow"), html.P(body)],
        className="boxed-note",
    )
