"""Small, testable estimators and filter semantics shared by the Dash views."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from bh_itbi.data import YEARS

TYPE_LABELS = {"apartment": "Apartamentos", "house": "Casas"}
DEFAULT_NEIGHBOURHOODS = ("SAVASSI", "LOURDES", "BURITIS", "CASTELO", "CENTRO")
AGE_LABELS = {
    "new": "Até 2 anos / na planta",
    "3_10": "3 a 10 anos",
    "11_25": "11 a 25 anos",
    "26_plus": "26 anos ou mais",
}
DISTANCE_PERIODS = {
    "2016–2018": (2016, 2018),
    "2019–2021": (2019, 2021),
    "2022–2025": (2022, 2025),
}


@dataclass(frozen=True)
class Filters:
    """Shared population filters; neighbourhood membership is recorded by the source."""

    property_type: str = "apartment"
    start_year: int = 2016
    end_year: int = 2025
    neighbourhoods: tuple[str, ...] = ()

    @classmethod
    def from_controls(cls, property_type, years, neighbourhoods) -> Filters:
        years = years if years is not None else [YEARS[0], YEARS[-1]]
        start, end = (int(year) for year in years)
        if property_type not in {"apartment", "house", "all"}:
            raise ValueError("Tipo de imóvel inválido.")
        if start not in YEARS or end not in YEARS or start > end:
            raise ValueError("Período inválido.")
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


def quantile_table(
    frame: pd.DataFrame,
    groups: list[str],
    column: str = "price_per_m2_brl_real",
    minimum: int = 1,
) -> pd.DataFrame:
    """Linear-interpolated pandas quartiles, with count-based suppression.

    The count is of non-null measurements, rather than group size. Rows below
    the minimum remain present with missing estimates so time-series gaps can
    be represented honestly. P25–P75 describes dispersion, not a confidence band.
    """
    data = frame[groups + [column]]
    data = data.loc[data[column].notna()]
    grouped = data.groupby(groups, observed=True)[column]
    result = grouped.quantile([0.25, 0.5, 0.75]).unstack()
    result = result.reindex(columns=[0.25, 0.5, 0.75])
    result.columns = ["p25", "median", "p75"]
    result["n"] = grouped.count()
    result.loc[result["n"] < minimum, ["p25", "median", "p75"]] = np.nan
    return result.reset_index()


def temporal_table(
    frame: pd.DataFrame, filters: Filters, *, neighbourhood: bool = False
) -> pd.DataFrame:
    """Reindex every calendar period, including absent and suppressed periods."""
    period, group, minimum = (
        ("quarter", "neighbourhood", 15) if neighbourhood else ("month", "property_type", 30)
    )
    result = quantile_table(frame, [period, group], minimum=minimum)
    periods = pd.date_range(
        f"{filters.start_year}-01-01",
        f"{filters.end_year}-12-01",
        freq="QS" if neighbourhood else "MS",
    )
    members = (
        list(filters.neighbourhoods or DEFAULT_NEIGHBOURHOODS)
        if neighbourhood
        else list(TYPE_LABELS)
        if filters.property_type == "all"
        else [filters.property_type]
    )
    index = pd.MultiIndex.from_product([periods, members], names=[period, group])
    return result.set_index([period, group]).reindex(index).reset_index()


def city_quarterly_table(frame: pd.DataFrame, filters: Filters) -> pd.DataFrame:
    """Pooled city quarterly quartiles across the active period (minimum n = 30)."""
    periods = pd.date_range(
        f"{filters.start_year}-01-01", f"{filters.end_year}-10-01", freq="QS"
    )
    return (
        quantile_table(frame, ["quarter"], minimum=30)
        .set_index("quarter")
        .reindex(periods)
        .rename_axis("quarter")
        .reset_index()
    )


def distribution_quartiles(
    frame: pd.DataFrame, column: str, minimum: int = 5
) -> pd.Series | None:
    """Quartiles of positive observations for the selected distribution metric."""
    values = frame.loc[frame[column].gt(0), column]
    if len(values) < minimum:
        return None
    return values.quantile([0.25, 0.5, 0.75])


def map_points(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Notebook cell 5's area/precision screen, P2–P98 trim and seeded sample.

    This sample is *only* for drawing. All summaries and analytical figures use
    the original filtered eligible records. Identical centroids are not jittered
    or treated as precise property locations.
    """
    columns = [
        "neighbourhood",
        "property_type",
        "built_area_m2",
        "transaction_date",
        "lat",
        "lon",
        "price_per_m2_brl",
    ]
    candidates = frame.loc[frame["face_geocoded"] & frame["built_area_m2"].gt(0), columns]
    limits = candidates["price_per_m2_brl"].quantile([0.02, 0.98])
    screened = candidates.loc[candidates["price_per_m2_brl"].between(*limits)]
    points = screened.sample(n=min(8000, len(screened)), random_state=42)
    return points, {
        "candidates": len(candidates),
        "screened": len(screened),
        "shown": len(points),
        "lower": limits.iloc[0],
        "upper": limits.iloc[1],
    }


def summary(frame: pd.DataFrame, minimum: int = 5) -> dict:
    """Count all eligible records but suppress small-sample headline medians."""
    count = len(frame)
    nominal = frame["price_per_m2_brl"].dropna()
    real = frame["price_per_m2_brl_real"].dropna()
    return {
        "n": count,
        "nominal": nominal.median() if len(nominal) >= minimum else np.nan,
        "real": real.median() if len(real) >= minimum else np.nan,
        "real_n": len(real),
        "geocoded": int(frame["face_geocoded"].sum()),
    }


def diagnostic_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Cell 15's extra positive-built-area screen, without altering main KPIs."""
    return frame.loc[frame["built_area_m2"] > 0]


def tax_base_table(frame: pd.DataFrame) -> pd.DataFrame:
    """A share's denominator includes only positive, recorded tax bases."""
    data = frame.loc[
        frame["built_area_m2"].gt(0) & frame["value_tax_base_brl"].gt(0),
        ["quarter", "property_type", "value_declared_brl", "value_tax_base_brl"],
    ]
    data["below"] = data["value_declared_brl"] < data["value_tax_base_brl"]
    result = data.groupby(["quarter", "property_type"], observed=True).agg(
        share=("below", "mean"), n=("below", "size")
    )
    result.loc[result["n"] < 100, "share"] = np.nan
    return result.reset_index()


def heaping_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Notebook's R$5,000-centred bins, including its half-to-even tie rule.

    A highlighted bin is *near* a multiple of R$50,000, not necessarily an exact
    multiple. This distinction corrects the notebook's original chart wording.
    """
    data = frame.loc[
        frame["built_area_m2"].gt(0)
        & frame["year"].between(2023, 2025)
        & frame["value_declared_brl"].between(50_000, 1_000_000),
        ["value_declared_brl"],
    ]
    centres = (data["value_declared_brl"] / 5000).round().mul(5000).astype(int)
    counts = centres.value_counts().reindex(range(50_000, 1_000_001, 5000), fill_value=0)
    result = counts.rename_axis("value").reset_index(name="n")
    result["is_round_bin"] = result["value"].mod(50_000).eq(0)
    return result


def heaping_summary(table: pd.DataFrame) -> tuple[int, float]:
    """Total observations and share in bins centred on R$50,000 multiples."""
    total = int(table["n"].sum())
    share = (
        float(table.loc[table["is_round_bin"], "n"].sum() / total) if total else float("nan")
    )
    return total, share


def age_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Recent apartments, pooled P99 exclusion, then quartiles within age band."""
    data = frame.loc[
        frame["built_area_m2"].gt(0)
        & frame["property_type"].eq("apartment")
        & frame["year"].between(2023, 2025)
        & frame["building_age_band"].isin(AGE_LABELS)
        & frame["price_per_m2_brl_real"].notna(),
        ["building_age_band", "price_per_m2_brl_real"],
    ]
    cap = data["price_per_m2_brl_real"].quantile(0.99)
    return quantile_table(
        data.loc[data["price_per_m2_brl_real"] <= cap], ["building_age_band"], minimum=15
    )


def distance_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Straight-line, street-face-centroid distances; 1 km bins, n >= 50."""
    data = frame.loc[
        frame["built_area_m2"].gt(0)
        & frame["property_type"].eq("apartment")
        & frame["year"].between(2016, 2025)
        & frame["distance_km"].lt(14)
        & frame["price_per_m2_brl_real"].notna(),
        ["year", "distance_km", "price_per_m2_brl_real"],
    ]
    data["band_km"] = np.floor(data["distance_km"]) + 0.5
    data["period"] = pd.cut(
        data["year"], bins=[2015, 2018, 2021, 2025], labels=list(DISTANCE_PERIODS)
    )
    return quantile_table(data, ["period", "band_km"], minimum=50)
