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
COMPARISON_MINIMUM = 15
RIDGE_MINIMUM = 50
COMPARISON_RIDGE_LIMIT = 8


@dataclass(frozen=True)
class Filters:
    """Shared population filters; neighbourhood membership is recorded by the source."""

    property_type: str = "all"
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


@dataclass(frozen=True)
class NeighbourhoodDistribution:
    """Exact price quantiles and, when estimable, a density on the shared log grid."""

    neighbourhood: str
    n: int
    quantiles: tuple[float, float, float, float, float]
    bandwidth: float | None
    density: np.ndarray | None


def silverman_bandwidth(log_prices: np.ndarray) -> float:
    """Silverman's robust normal-reference bandwidth, in natural-log units."""
    q25, q75 = np.quantile(log_prices, [0.25, 0.75])
    spread = min(log_prices.std(ddof=1), (q75 - q25) / 1.34)
    return float(0.9 * spread * log_prices.size ** (-1 / 5))


def log_price_density(log_prices: np.ndarray, grid: np.ndarray, bandwidth: float) -> np.ndarray:
    """Evaluate the Gaussian KDE exactly, bounding the temporary kernel matrix."""
    density = np.zeros_like(grid)
    for start in range(0, log_prices.size, 1024):
        kernel = grid[:, None] - log_prices[None, start : start + 1024]
        kernel /= bandwidth
        np.square(kernel, out=kernel)
        kernel *= -0.5
        np.exp(kernel, out=kernel)
        density += kernel.sum(axis=1)
    return density / (log_prices.size * bandwidth * np.sqrt(2 * np.pi))


def neighbourhood_price_distributions(
    frame: pd.DataFrame,
) -> tuple[np.ndarray, list[NeighbourhoodDistribution]]:
    """Summarise positive real prices, sorted by descending median.

    With up to eight eligible neighbourhoods, each non-degenerate sample of
    at least 50 prices contributes to the shared 512-point grid.
    """
    price = "price_per_m2_brl_real"
    values = frame.loc[frame[price].gt(0) & frame[price].lt(np.inf), ["neighbourhood", price]]
    grouped = values.groupby("neighbourhood", observed=True)[price]
    intervals_only = grouped.size().ge(COMPARISON_MINIMUM).sum() > COMPARISON_RIDGE_LIMIT
    samples = []
    lo, hi = np.inf, -np.inf
    for neighbourhood, prices in grouped:
        n = len(prices)
        if n < COMPARISON_MINIMUM:
            continue
        p10, p25, median, p75, p90 = prices.quantile([0.10, 0.25, 0.50, 0.75, 0.90])
        log_prices = None
        bandwidth = None
        if not intervals_only and n >= RIDGE_MINIMUM:
            log_prices = np.log(prices.to_numpy())
            bandwidth = silverman_bandwidth(log_prices)
            if bandwidth > 0:
                lo = min(lo, log_prices.min() - 3 * bandwidth)
                hi = max(hi, log_prices.max() + 3 * bandwidth)
        samples.append(
            (str(neighbourhood), n, (p10, p25, median, p75, p90), bandwidth, log_prices)
        )

    grid = np.linspace(lo, hi, 512) if lo < hi else np.empty(0)
    rows = []
    for neighbourhood, n, quantiles, bandwidth, log_prices in samples:
        density = None
        if bandwidth and log_prices is not None:
            estimate = log_price_density(log_prices, grid, bandwidth)
            # A broad shared grid can under-resolve a highly concentrated KDE.
            # Retain the exact interval if the sampled curve loses material mass.
            if abs(np.trapezoid(estimate, grid) - 1) < 1e-3:
                density = estimate
        rows.append(NeighbourhoodDistribution(neighbourhood, n, quantiles, bandwidth, density))
    rows.sort(key=lambda row: (-row.quantiles[2], row.neighbourhood))
    return grid, rows


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
