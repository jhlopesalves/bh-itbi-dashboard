"""Pure view-model assembly for the diagnostics tab."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from bh_itbi.age import AgePremiums, age_premiums
from bh_itbi.diagnostics import (
    distance_table,
    heaping_summary,
    heaping_table,
    tax_base_table,
)
from bh_itbi.filters import Filters, filter_transactions
from bh_itbi.text.diagnostics import age_note, age_subtitle, heaping_caption
from bh_itbi.text.shared import scope_text


@dataclass(frozen=True)
class DiagnosticsView:
    """Typed diagnostic tables, age estimates and formatted captions."""

    tax_base: pd.DataFrame
    heaping: pd.DataFrame
    age: AgePremiums
    distance: pd.DataFrame
    age_subtitle: str
    age_note: str
    heaping_caption: str
    diagnostic_scope: str


def _age_adjustment_note(result: AgePremiums) -> str:
    """Extract quarter contributions for the age adjustment footnote."""
    adjusted = "adjusted" in result.table
    quarter_values = (
        {str(key): float(value) for key, value in result.table["quarter"].items()}
        if adjusted
        else {}
    )
    return age_note(
        adjusted=adjusted,
        quarter_values=quarter_values,
        unavailable=result.unavailable,
        excluded=result.excluded,
    )


def build_diagnostics_view(frame: pd.DataFrame, filters: Filters) -> DiagnosticsView:
    """Compute all diagnostic tables, age premiums and copy for the active filters."""
    rows = filter_transactions(frame, filters)
    age = age_premiums(rows)
    heaping = heaping_table(rows)
    total, share = heaping_summary(heaping)
    return DiagnosticsView(
        tax_base=tax_base_table(rows),
        heaping=heaping,
        age=age,
        distance=distance_table(rows),
        age_subtitle=age_subtitle(
            filters.property_type,
            filters.start_year,
            filters.end_year,
            has_neighbourhoods=bool(filters.neighbourhoods),
            adjusted="adjusted" in age.table,
        ),
        age_note=_age_adjustment_note(age),
        heaping_caption=heaping_caption(total, share),
        diagnostic_scope=scope_text(
            filters.property_type, filters.start_year, filters.end_year, filters.neighbourhoods
        ),
    )
