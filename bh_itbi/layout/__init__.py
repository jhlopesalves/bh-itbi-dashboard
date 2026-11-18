"""Assemble the full dashboard shell from masthead, controls, view panels and footer."""

from __future__ import annotations

from collections.abc import Sequence

from dash import dcc, html

from bh_itbi.layout.components import GRAPH_CONFIG, card, dropdown, graph, metric
from bh_itbi.layout.controls import filter_area, view_tablist
from bh_itbi.layout.diagnostics import diagnostics_panel
from bh_itbi.layout.masthead import masthead
from bh_itbi.layout.methodology import footer, methodology
from bh_itbi.layout.models import models_panel
from bh_itbi.layout.overview import overview_panel
from bh_itbi.models import PreparedModels
from bh_itbi.text import shared as text
from bh_itbi.text.models import (
    hedonic_note,
)
from bh_itbi.text.overview import (
    COMPARISON_INTERVAL_SUBTITLE,
    COMPARISON_SUBTITLE,
)
from bh_itbi.text.shared import (
    DROPDOWN_LABELS,
)
from bh_itbi.theme import TEAL
from bh_itbi.urls import QUERY_OPTIONS, default_controls

__all__ = [
    "COMPARISON_INTERVAL_SUBTITLE",
    "COMPARISON_SUBTITLE",
    "DROPDOWN_LABELS",
    "GRAPH_CONFIG",
    "build_layout",
    "card",
    "diagnostics_panel",
    "dropdown",
    "footer",
    "graph",
    "hedonic_note",
    "masthead",
    "methodology",
    "metric",
    "models_panel",
    "overview_panel",
]


def build_layout(
    neighbourhoods: Sequence[str], models: PreparedModels | None, raw_rows: int
) -> html.Div:
    """Construct the root Dash component tree for the application shell."""
    return html.Div(
        [
            dcc.Store(id="url-navigation"),
            dcc.Store(id="url-ready", data=False),
            dcc.Store(
                id="url-config",
                data={"options": QUERY_OPTIONS, "defaults": default_controls()},
            ),
            html.A(text.SKIP_LINK_TEXT, href="#conteudo", className="skip-link"),
            masthead(raw_rows),
            filter_area(neighbourhoods),
            view_tablist(),
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
            footer(),
            dcc.Store(id="view-resize"),
        ],
        className="app-shell",
    )
