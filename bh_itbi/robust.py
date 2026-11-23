"""Clip by year without the inverse-variance weighting of standardised Huber loss."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from bh_itbi.config import (
    GAUSSIAN_MAD_CONSISTENCY,
    HEDONIC_MIN_NEIGHBOURHOODS,
    HUBER_TUNING,
    IDENTITY_TOLERANCE,
    ROBUST_MAX_ITERATIONS,
    ROBUST_TOLERANCE,
)

SCORE_TOLERANCE = 1e-10
FIXED_POINT_TOLERANCE = 1e-6


class RobustFitError(ValueError):
    """An estimator or its inference failed a numerical check."""


@dataclass(frozen=True)
class LinearDesign:
    """Aligned model arrays, with one name and term per design column."""

    x: NDArray[np.float64]
    y: NDArray[np.float64]
    columns: NDArray[np.str_]
    terms: NDArray[np.str_]
    quarters: NDArray[np.str_]
    years: NDArray[np.signedinteger]
    property_types: NDArray[np.str_]
    groups: NDArray[np.signedinteger]


@dataclass(frozen=True)
class RobustFit:
    """Final weighted solution, residual thresholds and convergence checks."""

    coefficients: NDArray[np.float64]
    weights: NDArray[np.float64]
    scales: NDArray[np.float64]
    thresholds: NDArray[np.float64]
    iterations: int
    score_max: float
    fixed_point_gap: float
    quarter_residual_max: float


def mad_scale(values: NDArray[np.float64]) -> float:
    """Estimate Gaussian-equivalent dispersion from the median absolute deviation."""
    if values.size == 0:
        return float("nan")
    return float(np.median(np.abs(values - np.median(values))) / GAUSSIAN_MAD_CONSISTENCY)


def _huber_weights(
    residuals: NDArray[np.float64], thresholds: NDArray[np.float64]
) -> NDArray[np.float64]:
    absolute = np.abs(residuals)
    return np.divide(
        thresholds, absolute, out=np.ones_like(residuals), where=absolute > thresholds
    )


def _residual_scales(
    residuals: NDArray[np.float64], masks: tuple[NDArray[np.bool_], ...]
) -> NDArray[np.float64]:
    return np.array([mad_scale(residuals[mask]) for mask in masks])


def _robust_lstsq(x: NDArray[np.float64], y: NDArray[np.float64]) -> NDArray[np.float64]:
    coefficients, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
    if rank != x.shape[1]:
        raise RobustFitError("Huber estimation requires a full-rank design.")
    return coefficients


def _huber_checks(
    design: LinearDesign,
    coefficients: NDArray[np.float64],
    weights: NDArray[np.float64],
    thresholds: NDArray[np.float64],
) -> tuple[float, float, float]:
    residuals = design.y - design.x @ coefficients
    weighted = weights * residuals
    score = float(np.max(np.abs(design.x.T @ weighted)) / len(weights))
    gap = float(np.max(np.abs(_huber_weights(residuals, thresholds) - weights)))
    _, quarter = np.unique(design.quarters, return_inverse=True)
    means = np.bincount(quarter, weights=weighted) / np.bincount(quarter, weights=weights)
    quarter_max = float(np.max(np.abs(means)))
    if not (
        score < SCORE_TOLERANCE
        and gap < FIXED_POINT_TOLERANCE
        and quarter_max < IDENTITY_TOLERANCE
    ):
        raise RobustFitError(
            f"Huber post-fit checks failed (score {score:.3g}, "
            f"fixed-point gap {gap:.3g}, quarterly residual mean {quarter_max:.3g})."
        )
    return score, gap, quarter_max


def fit_huber(
    design: LinearDesign,
    *,
    by_year: bool = False,
    tuning: float = HUBER_TUNING,
    tolerance: float = ROBUST_TOLERANCE,
    max_iterations: int = ROBUST_MAX_ITERATIONS,
) -> RobustFit:
    """Solve the Huber score with MAD thresholds and final-solve weights."""
    if not (tuning > 0 and tolerance > 0 and max_iterations >= 1) or not design.y.size:
        raise RobustFitError("Huber estimation requires data and positive tuning and limits.")
    coefficients = _robust_lstsq(design.x, design.y)
    codes = (
        np.unique(design.years, return_inverse=True)[1]
        if by_year
        else np.zeros(len(design.y), dtype=np.intp)
    )
    masks = tuple(codes == code for code in range(int(codes.max()) + 1))
    residuals = design.y - design.x @ coefficients
    scales = _residual_scales(residuals, masks)
    if np.isposinf(tuning):
        weights = np.ones_like(residuals)
        thresholds = np.full_like(residuals, np.inf)
        checks = _huber_checks(design, coefficients, weights, thresholds)
        return RobustFit(coefficients, weights, scales, thresholds, 1, *checks)
    for iteration in range(1, max_iterations + 1):
        if not np.all(np.isfinite(scales) & (scales > 0)):
            raise RobustFitError("Huber estimation requires finite, positive residual scales.")
        weights = _huber_weights(residuals, tuning * scales[codes])
        root = np.sqrt(weights)
        updated = _robust_lstsq(design.x * root[:, None], design.y * root)
        residuals = design.y - design.x @ updated
        updated_scales = _residual_scales(residuals, masks)
        coefficient_gap = np.max(np.abs(updated - coefficients))
        scale_gap = np.max(np.abs(updated_scales / scales - 1))
        if coefficient_gap < tolerance and scale_gap < tolerance:
            thresholds = tuning * updated_scales[codes]
            checks = _huber_checks(design, updated, weights, thresholds)
            return RobustFit(updated, weights, updated_scales, thresholds, iteration, *checks)
        coefficients, scales = updated, updated_scales
    raise RobustFitError(f"Huber IRLS did not converge in {max_iterations} iterations.")


def huber_covariance(design: LinearDesign, fit: RobustFit) -> NDArray[np.float64]:
    """Estimate the neighbourhood-clustered sandwich at the final thresholds."""
    x = design.x
    n, rank = x.shape
    groups, inverse = np.unique(design.groups, return_inverse=True)
    g = len(groups)
    if g < HEDONIC_MIN_NEIGHBOURHOODS or n <= rank:
        raise RobustFitError(
            "Clustered inference needs two clusters and residual degrees of freedom."
        )
    residuals = design.y - x @ fit.coefficients
    active = x[np.abs(residuals) <= fit.thresholds]
    bread = active.T @ active
    try:
        np.linalg.cholesky(bread)
    except np.linalg.LinAlgError as error:
        raise RobustFitError("The Huber sandwich bread is singular.") from error
    del active
    if np.linalg.matrix_rank(bread) != rank:
        raise RobustFitError("The Huber sandwich bread is singular.")
    scores = np.zeros((g, rank))
    psi = np.clip(residuals, -fit.thresholds, fit.thresholds)
    np.add.at(scores, inverse, x * psi[:, None])
    transformed = np.linalg.solve(bread, scores.T)
    correction = (g / (g - 1)) * ((n - 1) / (n - rank))
    return correction * (transformed @ transformed.T)


def weighted_decomposition(
    design: LinearDesign,
    coefficients: NDArray[np.float64],
    weights: NDArray[np.float64],
    terms: dict[str, str],
) -> dict[str, NDArray[np.float64]]:
    """Decompose weighted quarterly log means relative to the earliest quarter."""
    _, inverse = np.unique(design.quarters, return_inverse=True)
    totals = np.bincount(inverse, weights=weights)
    means: dict[str, NDArray[np.float64]] = {}
    for label, term in terms.items():
        columns = np.flatnonzero(design.terms == term)
        contribution = design.x[:, columns] @ coefficients[columns]
        means[label] = np.bincount(inverse, weights=weights * contribution) / totals
    means["mean_change"] = np.bincount(inverse, weights=weights * design.y) / totals
    changes = {label: mean - mean[0] for label, mean in means.items()}
    error = changes["mean_change"] - sum(changes[label] for label in terms)
    if not np.all(np.abs(error) < IDENTITY_TOLERANCE):
        raise RobustFitError("The weighted decomposition fails the accounting identity.")
    return {**changes, "identity_error": error}
