"""Shared population filter value object and transaction subsetting."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

import pandas as pd

from bh_itbi.config import END_YEAR, RESIDENTIAL_TYPES, START_YEAR, YEARS


@dataclass(frozen=True)
class Filters:
    """Shared population filters; neighbourhood membership is recorded by the source."""

    property_type: str = "all"
    start_year: int = START_YEAR
    end_year: int = END_YEAR
    neighbourhoods: tuple[str, ...] = ()

    @classmethod
    def from_controls(
        cls,
        property_type: str | None,
        years: Iterable[int | str] | None,
        neighbourhoods: Iterable[str] | None,
    ) -> Filters:
        """Validate Dash control values and normalise selected neighbourhood names."""
        year_values = list(years) if years is not None else [YEARS[0], YEARS[-1]]
        start, end = (int(year) for year in year_values)
        if property_type is None or property_type not in (*RESIDENTIAL_TYPES, "all"):
            raise ValueError("Invalid property type.")
        if start not in YEARS or end not in YEARS or start > end:
            raise ValueError("Invalid year range.")
        return cls(property_type, start, end, tuple(sorted(set(neighbourhoods or []))))

    def city_reference(self) -> Filters:
        """Keep type and dates, explicitly remove the neighbourhood restriction."""
        return replace(self, neighbourhoods=())


def filter_transactions(frame: pd.DataFrame, filters: Filters) -> pd.DataFrame:
    """Filter raw eligible records; an unknown neighbourhood is empty."""
    mask = frame["year"].between(filters.start_year, filters.end_year)
    if filters.property_type != "all":
        mask &= frame["property_type"].eq(filters.property_type)
    if filters.neighbourhoods:
        mask &= frame["neighbourhood"].isin(filters.neighbourhoods)
    return frame.loc[mask]


def positive_area(frame: pd.DataFrame) -> pd.Series:
    """Select rows with a strictly positive recorded built area."""
    return frame["built_area_m2"].gt(0)


def positive_area_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply the positive-built-area screen to an eligible population."""
    return frame.loc[positive_area(frame)]


def month_range(start_year: int, end_year: int) -> pd.DatetimeIndex:
    """Return every calendar month start in the inclusive year interval."""
    return pd.date_range(f"{start_year}-01-01", f"{end_year}-12-01", freq="MS")


def quarter_range(start_year: int, end_year: int) -> pd.DatetimeIndex:
    """Return every calendar quarter start in the inclusive year interval."""
    return pd.date_range(f"{start_year}-01-01", f"{end_year}-10-01", freq="QS")
