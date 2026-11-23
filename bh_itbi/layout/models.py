"""Lay out the hedonic index decomposition and neighbourhood trajectories."""

from __future__ import annotations

import pandas as pd
from dash import html
from dash.development.base_component import Component

from bh_itbi.cluster import ClusterMetadata
from bh_itbi.config import REPOSITORY_URL
from bh_itbi.formatting import number
from bh_itbi.layout.components import card, graph
from bh_itbi.models import COMPOSITION_TERMS, HedonicMetadata, PreparedModels
from bh_itbi.text import models as text


def _models_intro() -> html.Div:
    """Introduce the fixed populations used for model estimates."""
    return html.Div(
        [
            html.P(text.MODELS_EYEBROW, className="eyebrow"),
            html.H2(text.MODELS_SECTION_TITLE, className="section-title"),
            html.P(text.MODELS_DESCRIPTION, className="section-description"),
        ],
        className="section-intro",
    )


def _model_metrics(hedonic: HedonicMetadata) -> html.Div:
    """Render the hedonic sample size, coverage and R²."""
    return html.Div(
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
    )


def _hedonic_card(final: pd.Series) -> html.Section:
    """Render the hedonic index and its final composition note."""
    return card(
        text.HEDONIC_TITLE,
        text.HEDONIC_SUBTITLE,
        [
            graph("hedonic-figure", height=420),
            html.P(
                text.hedonic_note({group: float(final[group]) for group in COMPOSITION_TERMS}),
                className="card-footnote",
            ),
        ],
    )


def _annual_trajectories_card(clusters: ClusterMetadata) -> html.Section:
    """Render the figure for the fixed neighbourhood coverage."""
    return card(
        text.TRAJECTORIES_MODEL_TITLE,
        text.trajectories_subtitle(clusters["n_neighbourhoods"]),
        [
            graph("trajectories-figure", height=410),
            html.P(
                [
                    text.TRAJECTORIES_FOOTNOTE,
                    " ",
                    html.A(
                        text.TRAJECTORIES_AUDIT_LINK_TEXT,
                        href=f"{REPOSITORY_URL}/blob/main/docs/robustness/report.md",
                    ),
                ],
                className="card-footnote",
            ),
        ],
    )


def models_panel(models: PreparedModels | None) -> html.Div:
    """Build the fixed-population models tab panel or an unavailable banner."""
    if models is None:
        content: Component | list[Component] = html.P(
            text.MODELS_UNAVAILABLE_BANNER, className="scope-banner"
        )
    else:
        metadata = models.metadata
        final = models.hedonic.iloc[-1]
        content = [
            _models_intro(),
            _model_metrics(metadata["hedonic"]),
            _hedonic_card(final),
            _annual_trajectories_card(metadata["clusters"]),
        ]
    return html.Div(content, id="models-panel", className="view-panel is-hidden")
