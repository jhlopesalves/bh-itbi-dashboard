"""Quartile tables, Silverman bandwidth, Gaussian KDE evaluation and tail trimming."""

from __future__ import annotations

import numpy as np
import pandas as pd

from bh_itbi.config import KDE_BATCH_SIZE, KDE_TRIM_FRACTION, QUARTILE_PROBABILITIES


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
    data = frame[[*groups, column]]
    data = data.loc[data[column].notna()]
    grouped = data.groupby(groups, observed=True)[column]
    probabilities = np.array(QUARTILE_PROBABILITIES)
    result = grouped.quantile(probabilities).unstack()
    result = result.reindex(columns=probabilities)
    result.columns = ["p25", "median", "p75"]
    result["n"] = grouped.count()
    result.loc[result["n"] < minimum, ["p25", "median", "p75"]] = np.nan
    return result.reset_index()


def silverman_bandwidth(log_prices: np.ndarray) -> float:
    """Silverman's robust normal-reference bandwidth, in natural-log units."""
    lower_quartile, _, upper_quartile = QUARTILE_PROBABILITIES
    q25, q75 = np.quantile(log_prices, [lower_quartile, upper_quartile])
    spread = min(float(log_prices.std(ddof=1)), float((q75 - q25) / 1.34))
    return float(0.9 * spread * log_prices.size ** (-1 / 5))


def log_price_density(log_prices: np.ndarray, grid: np.ndarray, bandwidth: float) -> np.ndarray:
    """Evaluate the Gaussian KDE exactly, bounding the temporary kernel matrix."""
    density = np.zeros_like(grid)
    for start in range(0, log_prices.size, KDE_BATCH_SIZE):
        kernel = grid[:, None] - log_prices[None, start : start + KDE_BATCH_SIZE]
        kernel /= bandwidth
        np.square(kernel, out=kernel)
        kernel *= -0.5
        np.exp(kernel, out=kernel)
        density += kernel.sum(axis=1)
    return density / (log_prices.size * bandwidth * np.sqrt(2 * np.pi))


def trim_log_density(grid: np.ndarray, density: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Trim the outer tails at 1.5% of peak, preserving any troughs between modes."""
    threshold = KDE_TRIM_FRACTION * density.max()
    visible = np.flatnonzero(density > threshold)
    first, last = visible[0], visible[-1]
    log_prices = grid[first : last + 1]
    heights = density[first : last + 1]
    if first > 0:
        left = np.interp(threshold, density[first - 1 : first + 1], grid[first - 1 : first + 1])
        log_prices = np.r_[left, log_prices]
        heights = np.r_[threshold, heights]
    if last < len(grid) - 1:
        right = np.interp(threshold, density[[last + 1, last]], grid[[last + 1, last]])
        log_prices = np.r_[log_prices, right]
        heights = np.r_[heights, threshold]
    return np.exp(log_prices), heights
