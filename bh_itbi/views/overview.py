"""Pure view-model assembly and map click validation for the overview tab."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from bh_itbi.config import (
    COMPARISON_RIDGE_LIMIT,
    DEFAULT_NEIGHBOURHOODS,
    RIDGE_MINIMUM,
)
from bh_itbi.filters import Filters, filter_transactions
from bh_itbi.formatting import currency, number
from bh_itbi.overview import (
    NeighbourhoodDistribution,
    distribution_quartiles,
    map_points,
    neighbourhood_price_distributions,
    summary,
)
from bh_itbi.text.overview import (
    COMPARISON_INTERVAL_SUBTITLE,
    COMPARISON_SUBTITLE,
    DISTRIBUTION_QUARTILE_LABELS,
    comparison_caption,
    comparison_note,
    kpi_coverage_note,
    kpi_coverage_value,
    map_caption,
)
from bh_itbi.text.shared import scope_text


@dataclass(frozen=True)
class OverviewView:
    """Typed intermediate data and formatted Portuguese copy for the overview tab."""

    selected: pd.DataFrame
    city: pd.DataFrame
    points: pd.DataFrame
    comparison: pd.DataFrame
    comparison_grid: np.ndarray
    comparison_rows: tuple[NeighbourhoodDistribution, ...]
    quartiles: tuple[tuple[str, str], ...] | None
    map_caption: str
    kpi_count: str
    kpi_nominal: str
    kpi_real: str
    kpi_coverage: str
    kpi_coverage_note: str
    scope_label: str
    neighbourhood_caption: str
    comparison_note: str
    comparison_subtitle: str


def clicked_neighbourhood(
    click_data: Mapping[str, object] | None, available: set[str]
) -> str | None:
    """Use the clicked record's source label, never infer a geographical boundary."""
    if not isinstance(click_data, Mapping):
        return None
    points = click_data.get("points")
    if not isinstance(points, list) or not points or not isinstance(points[0], Mapping):
        return None
    custom = points[0].get("customdata")
    if not isinstance(custom, list) or not custom:
        return None
    name = custom[0]
    return name if isinstance(name, str) and name in available else None


def selection_from_map(
    frame: pd.DataFrame,
    filters: Filters,
    click_data: Mapping[str, object] | None,
    current: Sequence[str] | None,
) -> list[str] | None:
    """Return a changed selection only when the clicked neighbourhood is available."""
    available = set(filter_transactions(frame, filters)["neighbourhood"].dropna())
    selected = clicked_neighbourhood(click_data, available)
    if selected is None or list(current or []) == [selected]:
        return None
    return [selected]


def _comparison_card_copy(
    filters: Filters, requested_count: int, rows: Sequence[NeighbourhoodDistribution]
) -> tuple[str, str]:
    """Explain which neighbourhoods and curves are shown in the comparison card."""
    comparison_subtitle = (
        COMPARISON_INTERVAL_SUBTITLE
        if rows and not any(row.density is not None for row in rows)
        else COMPARISON_SUBTITLE
    )
    excluded = requested_count - len(rows)
    missing_ridge_curve = len(rows) <= COMPARISON_RIDGE_LIMIT and any(
        row.n >= RIDGE_MINIMUM and row.density is None for row in rows
    )
    show_interval_legend = comparison_subtitle == COMPARISON_SUBTITLE and any(
        row.density is None for row in rows
    )
    note = comparison_note(
        has_neighbourhood_filter=bool(filters.neighbourhoods),
        excluded=excluded,
        missing_ridge_curve=missing_ridge_curve,
        show_interval_legend=show_interval_legend,
    )
    return note, comparison_subtitle


def build_overview_view(
    frame: pd.DataFrame, filters: Filters, distribution_metric: str
) -> OverviewView:
    """Compute filtered subsets, KPIs, quartiles and explanatory captions for overview."""
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
    note, comparison_subtitle = _comparison_card_copy(
        filters, len(comparison_names), comparison_rows
    )
    raw_quartiles = distribution_quartiles(selected, distribution_metric)
    quartiles = (
        tuple(
            (label, currency(float(val)))
            for label, val in zip(DISTRIBUTION_QUARTILE_LABELS, raw_quartiles, strict=True)
        )
        if raw_quartiles is not None
        else None
    )
    return OverviewView(
        selected=selected,
        city=city,
        points=points,
        comparison=comparison,
        comparison_grid=comparison_grid,
        comparison_rows=tuple(comparison_rows),
        quartiles=quartiles,
        map_caption=map_caption(map_stats.shown, map_stats.screened),
        kpi_count=number(values.n),
        kpi_nominal=currency(values.nominal),
        kpi_real=currency(values.real),
        kpi_coverage=kpi_coverage_value(values.geocoded, values.n),
        kpi_coverage_note=kpi_coverage_note(values.geocoded, values.n),
        scope_label=scope_text(
            filters.property_type, filters.start_year, filters.end_year, filters.neighbourhoods
        ),
        neighbourhood_caption=comparison_caption(
            comparison_names, has_neighbourhood_filter=bool(filters.neighbourhoods)
        ),
        comparison_note=note,
        comparison_subtitle=comparison_subtitle,
    )
