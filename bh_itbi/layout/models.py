"""Models tab layout: hedonic index decomposition and k-means trajectory clusters."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
from dash import html
from dash.development.base_component import Component

from bh_itbi.cluster import ClusterMetadata
from bh_itbi.config import CLUSTER_K
from bh_itbi.formatting import number
from bh_itbi.layout.components import card, dropdown, graph, html_attributes
from bh_itbi.models import COMPOSITION_TERMS, HedonicMetadata, PreparedModels
from bh_itbi.text import models as text
from bh_itbi.theme import CLUSTER_COLORS
from bh_itbi.views.models import ClusterGroupView


def cluster_members(groups: Sequence[ClusterGroupView]) -> list[html.Div]:
    """Render the heading and member names of each visible group."""
    return [html.Div([html.H3(group.heading), html.P(group.members_text)]) for group in groups]


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


def _cluster_selector() -> html.Div:
    """Render the group selector with the trajectory colour swatches."""
    return html.Div(
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
                                        **html_attributes(aria_hidden="true"),
                                    ),
                                    text.cluster_group_name(group),
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
    )


def _clusters_card(clusters: ClusterMetadata) -> html.Section:
    """Render the trajectory figure and member disclosure."""
    return card(
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
        extra=_cluster_selector(),
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
            _clusters_card(metadata["clusters"]),
        ]
    return html.Div(content, id="models-panel", className="view-panel is-hidden")
