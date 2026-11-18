"""Overview tab analytical summaries, spatial sample and neighbourhood distributions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from bh_itbi.config import (
    COMPARISON_MINIMUM,
    COMPARISON_RIDGE_LIMIT,
    DEFAULT_NEIGHBOURHOODS,
    DISTRIBUTION_MINIMUM,
    KDE_GRID_SIZE,
    KDE_MASS_TOLERANCE,
    MAP_SAMPLE_SEED,
    MAP_SAMPLE_SIZE,
    MAP_TRIM_QUANTILES,
    NEIGHBOURHOOD_QUARTER_MINIMUM,
    RIDGE_MINIMUM,
    SUMMARY_MINIMUM,
    TEMPORAL_MINIMUM,
)
from bh_itbi.filters import Filters
from bh_itbi.stats import log_price_density, quantile_table, silverman_bandwidth
from bh_itbi.text import TYPE_LABELS


@dataclass(frozen=True)
class NeighbourhoodDistribution:
    """Exact price quantiles and, when estimable, a density on the shared log grid."""

    neighbourhood: str
    n: int
    quantiles: tuple[float, float, float, float, float]
    bandwidth: float | None
    density: np.ndarray | None


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
    samples: list[
        tuple[
            str,
            int,
            tuple[float, float, float, float, float],
            float | None,
            np.ndarray | None,
        ]
    ] = []
    lo, hi = np.inf, -np.inf
    for neighbourhood, prices in grouped:
        n = len(prices)
        if n < COMPARISON_MINIMUM:
            continue
        p10, p25, median, p75, p90 = (
            float(q) for q in prices.quantile([0.10, 0.25, 0.50, 0.75, 0.90])
        )
        log_prices = None
        bandwidth = None
        if not intervals_only and n >= RIDGE_MINIMUM:
            log_prices = np.log(prices.to_numpy())
            bandwidth = silverman_bandwidth(log_prices)
            if bandwidth > 0:
                lo = min(lo, float(log_prices.min()) - 3 * bandwidth)
                hi = max(hi, float(log_prices.max()) + 3 * bandwidth)
        samples.append(
            (str(neighbourhood), n, (p10, p25, median, p75, p90), bandwidth, log_prices)
        )

    grid = np.linspace(lo, hi, KDE_GRID_SIZE) if lo < hi else np.empty(0)
    rows: list[NeighbourhoodDistribution] = []
    for neighbourhood, n, quantiles, bandwidth, log_prices in samples:
        density = None
        if bandwidth and log_prices is not None:
            estimate = log_price_density(log_prices, grid, bandwidth)
            # A broad shared grid can under-resolve a highly concentrated KDE.
            # Retain the exact interval if the sampled curve loses material mass.
            if abs(np.trapezoid(estimate, grid) - 1) < KDE_MASS_TOLERANCE:
                density = estimate
        rows.append(NeighbourhoodDistribution(neighbourhood, n, quantiles, bandwidth, density))
    rows.sort(key=lambda row: (-row.quantiles[2], row.neighbourhood))
    return grid, rows


def temporal_table(
    frame: pd.DataFrame, filters: Filters, *, neighbourhood: bool = False
) -> pd.DataFrame:
    """Reindex every calendar period, including absent and suppressed periods."""
    period, group, minimum = (
        ("quarter", "neighbourhood", NEIGHBOURHOOD_QUARTER_MINIMUM)
        if neighbourhood
        else ("month", "property_type", TEMPORAL_MINIMUM)
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
        quantile_table(frame, ["quarter"], minimum=TEMPORAL_MINIMUM)
        .set_index("quarter")
        .reindex(periods)
        .rename_axis("quarter")
        .reset_index()
    )


def distribution_quartiles(
    frame: pd.DataFrame, column: str, minimum: int = DISTRIBUTION_MINIMUM
) -> pd.Series | None:
    """Quartiles of positive observations for the selected distribution metric."""
    values = frame.loc[frame[column].gt(0), column]
    if len(values) < minimum:
        return None
    return values.quantile([0.25, 0.5, 0.75])


def map_points(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Apply the positive-area and face-centroid screen, P2–P98 trim and seeded sample.

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
    limits = candidates["price_per_m2_brl"].quantile(list(MAP_TRIM_QUANTILES))
    screened = candidates.loc[candidates["price_per_m2_brl"].between(*limits)]
    points = screened.sample(
        n=min(MAP_SAMPLE_SIZE, len(screened)), random_state=MAP_SAMPLE_SEED
    )
    return points, {
        "candidates": len(candidates),
        "screened": len(screened),
        "shown": len(points),
        "lower": limits.iloc[0],
        "upper": limits.iloc[1],
    }


def summary(frame: pd.DataFrame, minimum: int = SUMMARY_MINIMUM) -> dict:
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
