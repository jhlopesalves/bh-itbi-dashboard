"""Lay out the hedonic index decomposition and neighbourhood trajectory patterns."""

from __future__ import annotations

import pandas as pd
from dash import html
from dash.development.base_component import Component

from bh_itbi.config import PATTERN_ORDER
from bh_itbi.formatting import number
from bh_itbi.layout.components import boxed_note, card, graph
from bh_itbi.models import COMPOSITION_TERMS, AuditEndpoint, HedonicMetadata, PreparedModels
from bh_itbi.text import models as text
from bh_itbi.theme import PATTERN_FIGURE_HEIGHT
from bh_itbi.views.models import pattern_member_names


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


def _hedonic_card(final: pd.Series, endpoint: AuditEndpoint | None) -> html.Section:
    """Render the index, final composition and optional sensitivity evidence."""
    body: list[Component] = [
        graph("hedonic-figure", height=420),
        html.P(
            text.hedonic_note({group: float(final[group]) for group in COMPOSITION_TERMS}),
            className="card-footnote",
        ),
    ]
    if endpoint is not None:
        body.append(
            boxed_note(
                text.SENSITIVITY_NOTE_EYEBROW,
                [
                    text.sensitivity_note(endpoint),
                    " ",
                    html.A(text.AUDIT_LINK_TEXT, href=text.AUDIT_REPORT_URL),
                ],
            )
        )
    return card(text.HEDONIC_TITLE, text.HEDONIC_SUBTITLE, body)


def _pattern_panel(models: PreparedModels, name: str) -> html.Div:
    """Place the pattern's counts and member lists around its plot."""
    summary = models.metadata["patterns"]["patterns"][name]
    firm, borderline = pattern_member_names(models.pattern_members, name)
    return html.Div(
        [
            html.H3(text.PATTERN_LABELS[name]),
            html.P(
                text.pattern_counts(summary["size"], summary["firm"]),
                className="pattern-counts",
            ),
            graph(f"pattern-figure-{name}", height=PATTERN_FIGURE_HEIGHT),
            html.Details(
                [
                    html.Summary(text.PATTERN_MEMBERS_SUMMARY),
                    html.P(f"{text.PATTERN_FIRM_LABEL}: {', '.join(firm) or '—'}"),
                    html.P(f"{text.PATTERN_BORDERLINE_LABEL}: {', '.join(borderline) or '—'}"),
                ]
            ),
        ],
        className="pattern-panel",
    )


def _patterns_card(models: PreparedModels) -> html.Section:
    """Describe the fixed population and show comparable pattern panels."""
    metadata = models.metadata["patterns"]
    sizes = metadata["patterns"]
    total = metadata["n_neighbourhoods"]
    borderline = (total - sum(summary["firm"] for summary in sizes.values())) / total
    largest_se = max(sizes[name]["max_centre_se"] for name in ("falling", "stable"))
    note = text.patterns_footnote(
        metadata["draws"],
        metadata["firm_share"],
        (largest_se, sizes["rising"]["max_centre_se"]),
        metadata["ari_median"],
        borderline,
    )
    return card(
        text.PATTERNS_TITLE,
        text.patterns_subtitle(total, metadata["period_minimum"]),
        [
            html.Div(
                [_pattern_panel(models, name) for name in PATTERN_ORDER],
                className="pattern-grid",
            ),
            html.P(
                [
                    note,
                    " ",
                    html.A(text.AUDIT_LINK_TEXT, href=text.AUDIT_REPORT_URL),
                ],
                className="card-footnote",
            ),
        ],
        class_name="patterns-card",
    )


def models_panel(models: PreparedModels | None, endpoint: AuditEndpoint | None) -> html.Div:
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
            _hedonic_card(final, endpoint),
            _patterns_card(models),
        ]
    return html.Div(content, id="models-panel", className="view-panel is-hidden")
