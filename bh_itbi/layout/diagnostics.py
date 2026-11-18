"""Diagnostics tab layout: tax-base, round-number heaping, age-premium and distance cards."""

from __future__ import annotations

from dash import dcc, html

from bh_itbi.layout.components import card, graph
from bh_itbi.text import diagnostics as diagnostics_copy, shared as shared_copy


def _tax_base_card() -> html.Section:
    """Render the declared value and tax-base comparison."""
    return card(
        diagnostics_copy.TAX_TITLE,
        diagnostics_copy.TAX_SUBTITLE,
        [
            graph("tax-figure"),
            html.P(diagnostics_copy.TAX_FOOTNOTE, className="card-footnote"),
        ],
    )


def _heaping_card() -> html.Section:
    """Render the round-number heaping diagnostic."""
    return card(
        diagnostics_copy.HEAPING_TITLE,
        diagnostics_copy.HEAPING_SUBTITLE,
        [
            graph("heaping-figure"),
            html.P(id="heaping-caption", className="card-footnote"),
        ],
    )


def _age_premium_card() -> html.Section:
    """Render the age premium SVG host and explanatory copy."""
    return card(
        diagnostics_copy.AGE_TITLE,
        html.Span(id="age-subtitle"),
        [
            dcc.Store(id="age-data"),
            html.Div(
                html.P(shared_copy.LOADING_MESSAGE, className="comparison-empty"),
                id="age-plot",
            ),
            html.P(id="age-note", className="card-footnote"),
        ],
        class_name="age-card",
    )


def _distance_card() -> html.Section:
    """Render the price gradient by distance from Praça Sete."""
    return card(
        diagnostics_copy.DISTANCE_TITLE,
        diagnostics_copy.DISTANCE_SUBTITLE,
        [
            graph("distance-figure"),
            html.P(diagnostics_copy.DISTANCE_FOOTNOTE, className="card-footnote"),
        ],
    )


def diagnostics_panel() -> html.Div:
    """Build the diagnostics tab panel."""
    return html.Div(
        [
            html.Div(
                [
                    html.P(diagnostics_copy.DIAGNOSTICS_EYEBROW, className="eyebrow"),
                    html.P(
                        diagnostics_copy.DIAGNOSTICS_DESCRIPTION,
                        className="section-description",
                    ),
                ],
                className="section-intro",
            ),
            html.P(id="diagnostic-scope", className="scope-banner", role="status"),
            html.Div(
                [_tax_base_card(), _heaping_card(), _age_premium_card(), _distance_card()],
                className="diagnostics-grid",
            ),
        ],
        id="diagnostics-panel",
        className="view-panel is-hidden",
    )
