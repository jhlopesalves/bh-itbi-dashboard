"""Estimate and bootstrap composition-adjusted biennial neighbourhood patterns."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import permutations
from typing import TYPE_CHECKING, TypedDict

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from threadpoolctl import threadpool_limits

from bh_itbi.config import (
    CLUSTER_K_RANGE,
    CLUSTER_RANDOM_STATE,
    END_YEAR,
    INDEX_BASE,
    PATTERN_DRAWS,
    PATTERN_FIRM_SHARE,
    PATTERN_K,
    PATTERN_N_INIT,
    PATTERN_ORDER,
    PATTERN_PERIOD_MINIMUM,
    PATTERN_PERIODS,
    PATTERN_RESAMPLING,
    PATTERN_SEED,
    START_YEAR,
)
from bh_itbi.resampling import block_face_pattern_medians

if TYPE_CHECKING:
    from sklearn.cluster import KMeans

type _CellSampler = Callable[[pd.DataFrame, np.random.Generator, int], NDArray[np.float64]]
_PERMUTATIONS = tuple(permutations(range(PATTERN_K)))
_CENTRE_QUANTILES = (0.10, 0.90)


class ClusteringError(ValueError):
    """The data or fitted centres cannot identify the three trajectory patterns."""


class PatternSettings(TypedDict):
    """Fixed estimation and bootstrap settings."""

    k: int
    n_init: int
    random_state: int
    period_minimum: int
    draws: int
    seed: int
    firm_share: float
    resampling: str


class PatternSummary(TypedDict):
    """Pattern membership counts and centre quantiles in period order."""

    size: int
    firm: int
    p10: list[float]
    p90: list[float]


class PatternMetadata(PatternSettings):
    """Composition adjustment, fit diagnostics and resampling agreement."""

    n_neighbourhoods: int
    inertia: float
    silhouettes: dict[str, float | None]
    ari_median: float
    ari_p10: float
    ari_p90: float
    separation_share: float
    falling_first: list[float]
    rising_last: list[float]
    rising_size: list[float]
    patterns: dict[str, PatternSummary]
    adjustment: dict[str, float]
    age_reference: str


@dataclass(frozen=True)
class PatternSample:
    """Eligible cells in alphabetical neighbourhood and chronological period order."""

    cells: list[pd.DataFrame]
    counts: pd.DataFrame
    shapes: NDArray[np.float64]
    adjustment: dict[str, float]
    age_reference: str


@dataclass(frozen=True)
class PatternStability:
    """Agreement, separation and centre ranges across aligned refits."""

    shares: NDArray[np.float64]
    centre_ranges: NDArray[np.float64]
    ari_median: float
    ari_p10: float
    ari_p90: float
    separation_share: float
    rising_size: list[float]


def pattern_settings() -> PatternSettings:
    """Expose the settings shared by preparation and audit provenance."""
    return {
        "k": PATTERN_K,
        "n_init": PATTERN_N_INIT,
        "random_state": CLUSTER_RANDOM_STATE,
        "period_minimum": PATTERN_PERIOD_MINIMUM,
        "draws": PATTERN_DRAWS,
        "seed": PATTERN_SEED,
        "firm_share": PATTERN_FIRM_SHARE,
        "resampling": PATTERN_RESAMPLING,
    }


def centre_pattern_rows(medians: NDArray[np.float64]) -> NDArray[np.float64]:
    """Remove each neighbourhood's mean across the five log medians."""
    return medians - medians.mean(axis=-1, keepdims=True)


def _adjust_pattern_prices(
    rows: pd.DataFrame,
) -> tuple[NDArray[np.float64], dict[str, float], str]:
    """Fit the pooled least-squares adjustment and retain the intercept in the values."""
    price = rows["price_per_m2_brl_real"].to_numpy(dtype=float)
    if not np.isfinite(price).all() or (price <= 0).any():
        raise ClusteringError("Trajectory patterns require finite, positive real prices.")
    band = rows["building_age_band"].astype("category")
    dummies = pd.get_dummies(band, drop_first=True, dtype=float)
    log_area = np.log(rows["built_area_m2"].to_numpy(dtype=float))
    design = np.column_stack((np.ones(len(rows)), log_area, dummies))
    log_price = np.log(price)
    coefficients = np.linalg.lstsq(design, log_price, rcond=None)[0]
    adjusted = log_price - design[:, 1:] @ coefficients[1:]
    terms = ("intercept", "log_area", *(str(term) for term in dummies.columns))
    return (
        adjusted,
        dict(zip(terms, map(float, coefficients), strict=True)),
        str(band.cat.categories[0]),
    )


def pattern_sample(frame: pd.DataFrame) -> PatternSample:
    """Build the fixed complete-case sample and retain all eligible cells for resampling."""
    rows = frame.loc[
        frame["year"].between(START_YEAR, END_YEAR)
        & frame["property_type"].eq("apartment")
        & frame["built_area_m2"].gt(0)
        & frame["price_per_m2_brl_real"].notna()
        & frame["building_age_band"].notna()
    ]
    if rows.empty:
        raise ClusteringError("No apartments meet the trajectory-pattern population rules.")
    adjusted, coefficients, age_reference = _adjust_pattern_prices(rows)
    periods = (rows["year"].to_numpy(dtype=int) - START_YEAR) // 2
    rows = rows.assign(adjusted_log_price=adjusted, period=np.asarray(PATTERN_PERIODS)[periods])
    grouped = rows.groupby(["neighbourhood", "period"], observed=True, sort=True)
    counts = grouped.size().unstack().reindex(columns=PATTERN_PERIODS).sort_index()
    counts = counts.loc[counts.ge(PATTERN_PERIOD_MINIMUM).all(axis=1)]
    medians = grouped["adjusted_log_price"].median().unstack().reindex_like(counts)
    cells = [
        grouped.get_group((name, period)) for name in counts.index for period in PATTERN_PERIODS
    ]
    return PatternSample(
        cells,
        counts,
        centre_pattern_rows(medians.to_numpy(dtype=float)),
        coefficients,
        age_reference,
    )


def fit_pattern_kmeans(
    shapes: NDArray[np.float64], k: int = PATTERN_K, *, n_init: int = PATTERN_N_INIT
) -> KMeans:
    """Fit the requested partition, keeping scikit-learn out of serving imports."""
    from sklearn.cluster import KMeans  # noqa: PLC0415

    # The lazy import must load OpenMP before setting its thread limit.
    with threadpool_limits(limits=2):
        return KMeans(
            n_clusters=k,
            n_init=n_init,  # pyright: ignore[reportArgumentType]
            random_state=CLUSTER_RANDOM_STATE,
        ).fit(shapes)


def named_pattern_order(centres: NDArray[np.float64]) -> tuple[int, int, int]:
    """Find falling and rising from their endpoints, then assign the remaining centre."""
    falling = int(centres[:, 0].argmax())
    rising = int(centres[:, -1].argmax())
    if falling == rising:
        raise ClusteringError("The same centre has the largest first and last values.")
    stable = next(label for label in range(PATTERN_K) if label not in {falling, rising})
    return falling, stable, rising


def align_pattern_labels(
    reference: NDArray[np.float64], centres: NDArray[np.float64]
) -> tuple[int, ...]:
    """Return draw labels in reference order by minimum summed squared centre distance."""
    return min(
        _PERMUTATIONS,
        key=lambda order: float(np.square(reference - centres[list(order)]).sum()),
    )


def _pattern_silhouettes(
    matrix: NDArray[np.float64], fitted: KMeans, distinct: int
) -> dict[str, float | None]:
    """Report scores only where the data can support the candidate partition."""
    from sklearn.metrics import silhouette_score  # noqa: PLC0415

    scores: dict[str, float | None] = {}
    for k in CLUSTER_K_RANGE:
        scores[str(k)] = None
        if k <= distinct and k < len(matrix):
            candidate = fitted if k == PATTERN_K else fit_pattern_kmeans(matrix, k)
            labels = candidate.labels_
            if labels is not None and np.unique(labels).size == k:
                scores[str(k)] = float(silhouette_score(matrix, labels))
    return scores


def _independent_pattern_medians(
    cell: pd.DataFrame, rng: np.random.Generator, draws: int
) -> NDArray[np.float64]:
    """Draw a full cell's records with replacement for every bootstrap replicate."""
    values = cell["adjusted_log_price"].to_numpy(dtype=float)
    return np.median(rng.choice(values, size=(draws, len(values))), axis=1)


def _identifies_named_patterns(
    centres: NDArray[np.float64], order: tuple[int, int, int]
) -> bool:
    """Check the endpoint naming rule after aligning a draw to the fitted labels."""
    try:
        return named_pattern_order(centres) == order
    except ClusteringError:
        return False


def _pattern_bootstrap(
    sample: PatternSample,
    fitted: KMeans,
    order: tuple[int, int, int],
    resample_cell: _CellSampler,
) -> PatternStability:
    """Refit centred cell medians and compare each partition with the full-data fit."""
    from sklearn.metrics import adjusted_rand_score  # noqa: PLC0415

    rng = np.random.default_rng(PATTERN_SEED)
    # The stream traverses alphabetical neighbourhoods and chronological periods.
    draws = np.stack([resample_cell(cell, rng, PATTERN_DRAWS) for cell in sample.cells], axis=1)
    shapes = centre_pattern_rows(draws.reshape(PATTERN_DRAWS, *sample.shapes.shape))
    reference_labels = fitted.labels_
    assert reference_labels is not None
    matches = np.zeros(len(reference_labels), dtype=int)
    aris = np.empty(PATTERN_DRAWS)
    aligned_centres = np.empty((PATTERN_DRAWS, PATTERN_K, len(PATTERN_PERIODS)))
    identified = np.empty(PATTERN_DRAWS, dtype=bool)
    sizes = np.empty((PATTERN_DRAWS, PATTERN_K), dtype=int)
    for i, matrix in enumerate(shapes):
        draw = fit_pattern_kmeans(matrix)
        labels = draw.labels_
        assert labels is not None
        permutation = align_pattern_labels(fitted.cluster_centers_, draw.cluster_centers_)
        aligned_centres[i] = draw.cluster_centers_[list(permutation)]
        aligned_labels = np.argsort(permutation)[labels]
        matches += aligned_labels == reference_labels
        identified[i] = _identifies_named_patterns(aligned_centres[i], order)
        sizes[i] = np.bincount(aligned_labels, minlength=PATTERN_K)
        aris[i] = adjusted_rand_score(reference_labels, labels)
    lo, median, hi = np.quantile(aris, [0.10, 0.5, 0.90])
    return PatternStability(
        shares=matches / PATTERN_DRAWS,
        centre_ranges=np.quantile(
            INDEX_BASE * np.exp(aligned_centres), _CENTRE_QUANTILES, axis=0
        ),
        ari_median=float(median),
        ari_p10=float(lo),
        ari_p90=float(hi),
        separation_share=float(identified.mean()),
        rising_size=np.quantile(sizes[:, order[-1]], _CENTRE_QUANTILES).tolist(),
    )


def _pattern_tables(
    sample: PatternSample,
    fitted: KMeans,
    order: tuple[int, int, int],
    stability: PatternStability,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Construct long-form member and centre tables in display units."""
    labels = fitted.labels_
    assert labels is not None
    names = np.asarray(PATTERN_ORDER)
    index = INDEX_BASE * np.exp(sample.shapes)
    members = pd.DataFrame(
        {
            "neighbourhood": np.repeat(sample.counts.index.to_numpy(), len(PATTERN_PERIODS)),
            "period": np.tile(PATTERN_PERIODS, len(sample.counts)),
            "index": index.ravel(),
            "n": sample.counts.to_numpy(dtype=int).ravel(),
            "pattern": np.repeat(names[np.argsort(order)[labels]], len(PATTERN_PERIODS)),
            "membership_share": np.repeat(stability.shares, len(PATTERN_PERIODS)),
        }
    )
    members["firm"] = members["membership_share"].ge(PATTERN_FIRM_SHARE)
    centres = pd.DataFrame(
        {
            "pattern": np.repeat(names, len(PATTERN_PERIODS)),
            "period": np.tile(PATTERN_PERIODS, PATTERN_K),
            "index": (INDEX_BASE * np.exp(fitted.cluster_centers_[list(order)])).ravel(),
            "p10": stability.centre_ranges[0, list(order)].ravel(),
            "p90": stability.centre_ranges[1, list(order)].ravel(),
        }
    )
    return members, centres


def trajectory_patterns(
    frame: pd.DataFrame, *, resample_cell: _CellSampler = block_face_pattern_medians
) -> tuple[pd.DataFrame, pd.DataFrame, PatternMetadata]:
    """Estimate the fixed patterns and bootstrap their centres and membership."""
    with threadpool_limits(limits=2):
        sample = pattern_sample(frame)
        distinct = len(np.unique(sample.shapes, axis=0))
        if distinct < PATTERN_K:
            raise ClusteringError(
                f"At least {PATTERN_K} distinct complete trajectories are needed."
            )
        fitted = fit_pattern_kmeans(sample.shapes)
        order = named_pattern_order(fitted.cluster_centers_)
        silhouettes = _pattern_silhouettes(sample.shapes, fitted, distinct)
        stability = _pattern_bootstrap(sample, fitted, order, resample_cell)
    members, centres = _pattern_tables(sample, fitted, order, stability)
    membership = members.drop_duplicates("neighbourhood")
    summary: dict[str, PatternSummary] = {}
    for name, label in zip(PATTERN_ORDER, order, strict=True):
        selected = membership.loc[membership["pattern"].eq(name)]
        summary[name] = {
            "size": len(selected),
            "firm": int(selected["firm"].sum()),
            "p10": stability.centre_ranges[0, label].tolist(),
            "p90": stability.centre_ranges[1, label].tolist(),
        }
    inertia = fitted.inertia_
    assert inertia is not None
    return (
        members,
        centres,
        {
            **pattern_settings(),
            "resampling": "independent_records"
            if resample_cell is _independent_pattern_medians
            else PATTERN_RESAMPLING,
            "n_neighbourhoods": len(sample.counts),
            "inertia": float(inertia),
            "silhouettes": silhouettes,
            "ari_median": stability.ari_median,
            "ari_p10": stability.ari_p10,
            "ari_p90": stability.ari_p90,
            "separation_share": stability.separation_share,
            "falling_first": stability.centre_ranges[:, order[0], 0].tolist(),
            "rising_last": stability.centre_ranges[:, order[-1], -1].tolist(),
            "rising_size": stability.rising_size,
            "patterns": summary,
            "adjustment": sample.adjustment,
            "age_reference": sample.age_reference,
        },
    )
