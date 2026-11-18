"""Shared filter controls and accessible view tablist."""

from __future__ import annotations

from collections.abc import Sequence

from dash import dcc, html

from bh_itbi.config import YEAR_TICKS, YEARS
from bh_itbi.layout.components import dropdown, html_attributes
from bh_itbi.text import shared as text


def _property_type_field() -> html.Div:
    """Render the residential property-type selector."""
    return html.Div(
        [
            html.Label(
                text.PROPERTY_TYPE_LABEL,
                htmlFor="property-type",
                id="property-type-label",
            ),
            dropdown(
                "property-type",
                options=[
                    {
                        "label": text.TYPE_LABELS["apartment"],
                        "value": "apartment",
                    },
                    {
                        "label": text.TYPE_LABELS["house"],
                        "value": "house",
                    },
                    {
                        "label": text.ALL_TYPES_LABEL,
                        "value": "all",
                    },
                ],
                value="all",
                clearable=False,
                searchable=False,
            ),
        ],
        className="filter-field type-field",
        role="group",
        **html_attributes(aria_labelledby="property-type-label"),
    )


def _period_field() -> html.Div:
    """Render the year-range control and its current period."""
    return html.Div(
        [
            html.Div(
                [
                    html.Label(text.PERIOD_LABEL, id="years-label"),
                    html.Span(
                        text.MASTHEAD_PERIOD_DD,
                        id="years-value",
                        className="period-value",
                    ),
                ],
                className="period-heading",
            ),
            dcc.RangeSlider(
                id="year-range",
                min=YEARS[0],
                max=YEARS[-1],
                step=1,
                value=[YEARS[0], YEARS[-1]],
                allowCross=False,
                marks={y: str(y) for y in YEARS if y in YEAR_TICKS},
                tooltip={
                    "placement": "bottom",
                    "always_visible": False,
                },
                updatemode="mouseup",
                allow_direct_input=False,
            ),
        ],
        className="filter-field years-field",
        role="group",
        **html_attributes(aria_labelledby="years-label"),
    )


def _neighbourhood_field(neighbourhoods: Sequence[str]) -> html.Div:
    """Render the source neighbourhoods as a multi-select control."""
    return html.Div(
        [
            html.Label(
                text.NEIGHBOURHOODS_LABEL,
                htmlFor="neighbourhoods",
                id="neighbourhoods-label",
            ),
            dropdown(
                "neighbourhoods",
                options=[{"label": name.title(), "value": name} for name in neighbourhoods],
                value=[],
                multi=True,
                placeholder=text.ALL_NEIGHBOURHOODS_LABEL,
                clearable=True,
            ),
        ],
        className="filter-field neighbourhood-field",
        role="group",
        **html_attributes(aria_labelledby="neighbourhoods-label"),
    )


def filter_area(neighbourhoods: Sequence[str]) -> html.Div:
    """Render the shared filters and their scope note."""
    return html.Div(
        [
            html.Div(
                [
                    _property_type_field(),
                    _period_field(),
                    _neighbourhood_field(neighbourhoods),
                    html.Button(
                        text.RESET_FILTERS_LABEL,
                        id="reset-filters",
                        className="button button-quiet reset-button",
                    ),
                ],
                id="filter-controls",
                className="filters",
            ),
            html.P(
                text.FILTER_NOTE_ACTIVE,
                id="filter-note",
                className="filter-note",
                role="status",
            ),
        ],
        className="filter-area",
    )


def view_tablist() -> html.Div:
    """Render the three-section segmented navigation tablist."""
    return html.Div(
        [
            html.Button(
                label,
                id=f"tab-{name}",
                role="tab",
                className="view-tab view-tab-selected" if name == "overview" else "view-tab",
                tabIndex=0 if name == "overview" else -1,
                **html_attributes(
                    aria_selected="true" if name == "overview" else "false",
                    aria_controls=f"{name}-panel",
                ),
            )
            for name, label in text.TAB_LABELS
        ],
        className="view-tabs view-tabs-parent",
        role="tablist",
        **html_attributes(aria_label=text.TABLIST_ARIA_LABEL),
    )
