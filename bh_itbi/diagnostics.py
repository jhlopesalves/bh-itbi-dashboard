"""Diagnostic tables for tax-base divergence, round-number heaping and distance gradients."""

from __future__ import annotations

import numpy as np
import pandas as pd

from bh_itbi.config import (
    DISTANCE_BAND_WIDTH_KM,
    DISTANCE_MAX_KM,
    DISTANCE_MINIMUM,
    DISTANCE_PERIOD_BINS,
    DISTANCE_PERIODS,
    END_YEAR,
    HEAPING_BIN_WIDTH,
    HEAPING_MAX_VALUE,
    HEAPING_MIN_VALUE,
    HEAPING_ROUND_MULTIPLE,
    HEAPING_YEARS,
    START_YEAR,
    TAX_BASE_MINIMUM,
)
from bh_itbi.filters import positive_area
from bh_itbi.stats import quantile_table
from bh_itbi.text.shared import (
    AGE_LABELS,
)

__all__ = [
    "AGE_LABELS",
    "distance_table",
    "heaping_summary",
    "heaping_table",
    "tax_base_table",
]


def tax_base_table(frame: pd.DataFrame) -> pd.DataFrame:
    """A share's denominator includes only positive, recorded tax bases."""
    data = frame.loc[
        positive_area(frame) & frame["value_tax_base_brl"].gt(0),
        ["quarter", "property_type", "value_declared_brl", "value_tax_base_brl"],
    ]
    data["below"] = data["value_declared_brl"] < data["value_tax_base_brl"]
    result = data.groupby(["quarter", "property_type"], observed=True).agg(
        share=("below", "mean"), n=("below", "size")
    )
    result.loc[result["n"] < TAX_BASE_MINIMUM, "share"] = np.nan
    return result.reset_index()


def heaping_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Count transactions in R$5,000-centred bins using the half-to-even tie rule.

    A highlighted bin is *near* a multiple of R$50,000, not necessarily an exact
    multiple.
    """
    data = frame.loc[
        positive_area(frame)
        & frame["year"].between(*HEAPING_YEARS)
        & frame["value_declared_brl"].between(HEAPING_MIN_VALUE, HEAPING_MAX_VALUE),
        ["value_declared_brl"],
    ]
    centres = (
        (data["value_declared_brl"] / HEAPING_BIN_WIDTH)
        .round()
        .mul(HEAPING_BIN_WIDTH)
        .astype(int)
    )
    counts = centres.value_counts().reindex(
        range(HEAPING_MIN_VALUE, HEAPING_MAX_VALUE + 1, HEAPING_BIN_WIDTH), fill_value=0
    )
    result = counts.rename_axis("value").reset_index(name="n")
    result["is_round_bin"] = result["value"].mod(HEAPING_ROUND_MULTIPLE).eq(0)
    return result


def heaping_summary(table: pd.DataFrame) -> tuple[int, float]:
    """Total observations and share in bins centred on R$50,000 multiples."""
    total = int(table["n"].sum())
    share = (
        float(table.loc[table["is_round_bin"], "n"].sum() / total) if total else float("nan")
    )
    return total, share


def distance_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Straight-line, street-face-centroid distances; 1 km bins, n >= 50."""
    data = frame.loc[
        positive_area(frame)
        & frame["property_type"].eq("apartment")
        & frame["year"].between(START_YEAR, END_YEAR)
        & frame["distance_km"].lt(DISTANCE_MAX_KM)
        & frame["price_per_m2_brl_real"].notna(),
        ["year", "distance_km", "price_per_m2_brl_real"],
    ]
    data["band_km"] = (
        np.floor(data["distance_km"] / DISTANCE_BAND_WIDTH_KM) * DISTANCE_BAND_WIDTH_KM
        + DISTANCE_BAND_WIDTH_KM / 2
    )
    data["period"] = pd.cut(
        data["year"], bins=list(DISTANCE_PERIOD_BINS), labels=list(DISTANCE_PERIODS)
    )
    return quantile_table(data, ["period", "band_km"], minimum=DISTANCE_MINIMUM)
