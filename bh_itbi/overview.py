"""Overview tab analytical summaries, spatial sample and neighbourhood distributions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

import numpy as np
import pandas as pd

from bh_itbi.config import (
    COMPARISON_MINIMUM,
    COMPARISON_PROBABILITIES,
    COMPARISON_RIDGE_LIMIT,
    DEFAULT_NEIGHBOURHOODS,
    DISTRIBUTION_MINIMUM,
    END_YEAR,
    KDE_BANDWIDTH_EXTENT,
    KDE_GRID_SIZE,
    KDE_MASS_TOLERANCE,
    MAP_SAMPLE_SEED,
    MAP_SAMPLE_SIZE,
    MAP_TRIM_QUANTILES,
    NEIGHBOURHOOD_QUARTER_MINIMUM,
    QUARTILE_PROBABILITIES,
    RESIDENTIAL_TYPES,
    RIDGE_MINIMUM,
    START_YEAR,
    SUMMARY_MINIMUM,
    TEMPORAL_MINIMUM,
)
from bh_itbi.filters import Filters, month_range, positive_area, quarter_range
from bh_itbi.stats import log_price_density, quantile_table, silverman_bandwidth


@dataclass(frozen=True)
class NeighbourhoodDistribution:
    """Exact price quantiles and, when estimable, a density on the shared log grid."""

    neighbourhood: str
    n: int
    quantiles: tuple[float, float, float, float, float]
    bandwidth: float | None
    density: np.ndarray | None


@dataclass(frozen=True)
class MapStats:
    """Candidate, P2–P98 screened and sampled counts for the point map."""

    candidates: int
    screened: int
    shown: int
    lower: float
    upper: float


class MapScales(TypedDict):
    """Fixed colour bounds and upper marker area from the full map population."""

    price_lower: float
    price_upper: float
    area_reference: float


@dataclass(frozen=True)
class Summary:
    """Eligible record counts, headline medians and face-geocoded coverage."""

    n: int
    latest_real: float
    latest_year: int
    real: float
    real_n: int
    geocoded: int


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
            float(q) for q in prices.quantile(COMPARISON_PROBABILITIES)
        )
        log_prices = None
        bandwidth = None
        if not intervals_only and n >= RIDGE_MINIMUM:
            log_prices = np.log(prices.to_numpy())
            bandwidth = silverman_bandwidth(log_prices)
            if bandwidth > 0:
                lo = min(lo, float(log_prices.min()) - KDE_BANDWIDTH_EXTENT * bandwidth)
                hi = max(hi, float(log_prices.max()) + KDE_BANDWIDTH_EXTENT * bandwidth)
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
    periods = (
        quarter_range(filters.start_year, filters.end_year)
        if neighbourhood
        else month_range(filters.start_year, filters.end_year)
    )
    members = (
        list(filters.neighbourhoods or DEFAULT_NEIGHBOURHOODS)
        if neighbourhood
        else list(RESIDENTIAL_TYPES)
        if filters.property_type == "all"
        else [filters.property_type]
    )
    index = pd.MultiIndex.from_product([periods, members], names=[period, group])
    return result.set_index([period, group]).reindex(index).reset_index()


def city_quarterly_table(frame: pd.DataFrame, filters: Filters) -> pd.DataFrame:
    """Pooled city quarterly quartiles across the active period (minimum n = 30)."""
    periods = quarter_range(filters.start_year, filters.end_year)
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
    return values.quantile(QUARTILE_PROBABILITIES)


def _map_candidate_mask(frame: pd.DataFrame) -> pd.Series:
    """Select records with a face centroid and positive built area."""
    return frame["face_geocoded"] & positive_area(frame)


def map_reference_scales(frame: pd.DataFrame) -> MapScales:
    """Compute scale limits on eligible, face-geocoded records with positive area."""
    eligible = frame["year"].between(START_YEAR, END_YEAR)
    population = frame.loc[
        eligible & _map_candidate_mask(frame), ["price_per_m2_brl_real", "built_area_m2"]
    ]
    low, high = MAP_TRIM_QUANTILES
    prices = population["price_per_m2_brl_real"]
    lower, upper = prices.quantile([low, high])
    return {
        "price_lower": float(lower),
        "price_upper": float(upper),
        "area_reference": float(population["built_area_m2"].quantile(high)),
    }


def map_points(frame: pd.DataFrame, scales: MapScales) -> tuple[pd.DataFrame, MapStats]:
    """Apply the map screen, fixed real-price limits and seeded sample.

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
        "price_per_m2_brl_real",
    ]
    candidates = frame.loc[_map_candidate_mask(frame), columns]
    lower, upper = scales["price_lower"], scales["price_upper"]
    screened = candidates.loc[candidates["price_per_m2_brl_real"].between(lower, upper)]
    points = screened.sample(
        n=min(MAP_SAMPLE_SIZE, len(screened)), random_state=MAP_SAMPLE_SEED
    )
    return points, MapStats(
        candidates=len(candidates),
        screened=len(screened),
        shown=len(points),
        lower=lower,
        upper=upper,
    )


def summary(frame: pd.DataFrame, end_year: int, minimum: int = SUMMARY_MINIMUM) -> Summary:
    """Count all eligible records but suppress small-sample headline medians."""
    count = len(frame)
    real = frame["price_per_m2_brl_real"].dropna()
    latest = frame.loc[frame["year"].eq(end_year), "price_per_m2_brl_real"].dropna()
    return Summary(
        n=count,
        latest_real=float(latest.median()) if len(latest) >= minimum else float(np.nan),
        latest_year=end_year,
        real=float(real.median()) if len(real) >= minimum else float(np.nan),
        real_n=len(real),
        geocoded=int(frame["face_geocoded"].sum()),
    )
