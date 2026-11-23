"""Define the frozen hedonic sensitivity protocol and estimate its specifications."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from statistics import NormalDist
from typing import TYPE_CHECKING, cast

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from numpy.typing import NDArray

from bh_itbi.config import (
    AUDIT_CLUSTER_DRAWS,
    AUDIT_MEDIAN_DRAWS,
    AUDIT_SEED,
    GAUSSIAN_MAD_CONSISTENCY,
    HEDONIC_ALPHA,
    HUBER_TUNING,
    IDENTITY_TOLERANCE,
    INDEX_BASE,
    RESIDENTIAL_TYPES,
    ROBUST_MAX_ITERATIONS,
    ROBUST_TOLERANCE,
    YEARS,
)
from bh_itbi.data import DataError
from bh_itbi.models import COMPOSITION_TERMS, FORMULA, QUARTER_TERM, model_population
from bh_itbi.robust import (
    FIXED_POINT_TOLERANCE,
    SCORE_TOLERANCE,
    LinearDesign,
    RobustFit,
    fit_huber,
    huber_covariance,
    weighted_decomposition,
)

if TYPE_CHECKING:
    from patsy.design_info import DesignInfo

QUARTERS = tuple(f"{year}Q{quarter}" for year in YEARS for quarter in range(1, 5))
TERMS = {"adjusted": QUARTER_TERM, **COMPOSITION_TERMS}
INTERVAL_QUANTILE = NormalDist().inv_cdf(1 - HEDONIC_ALPHA / 2)


class SensitivityError(ValueError):
    """A specification cannot be estimated under the frozen protocol."""


@dataclass(frozen=True)
class Specification:
    """An estimator and the inclusive bounds of its operational population."""

    spec_id: str
    family: str
    rule: str
    estimator: str = "OLS"
    price_min: int | None = None
    price_max: int | None = None
    ratio_min: float | None = None
    area_window: tuple[int, int] | None = None
    property_type: str | None = None


@dataclass(frozen=True)
class Protocol:
    """Ordered specifications, numerical tolerances and the random design."""

    specifications: tuple[Specification, ...]
    protocol_id: str = "hedonic-sensitivity-v1"
    tuning: float = HUBER_TUNING
    mad_consistency: float = GAUSSIAN_MAD_CONSISTENCY
    tolerance: float = ROBUST_TOLERANCE
    max_iterations: int = ROBUST_MAX_ITERATIONS
    score_tolerance: float = SCORE_TOLERANCE
    fixed_point_tolerance: float = FIXED_POINT_TOLERANCE
    identity_tolerance: float = IDENTITY_TOLERANCE
    seed: int = AUDIT_SEED
    cluster_draws: int = AUDIT_CLUSTER_DRAWS
    median_draws: int = AUDIT_MEDIAN_DRAWS

    def canonical_json(self) -> str:
        """Represent the protocol as canonical UTF-8 JSON for hashing."""
        return json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    @property
    def sha256(self) -> str:
        """Hash the exact bytes written to the protocol file."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


PROTOCOL = Protocol(
    (
        Specification("baseline", "reference", "Retain the published model population"),
        *(
            Specification(
                f"price_floor_{floor:04d}",
                "real price floor",
                f"Real price per m² ≥ R${floor:,}",
                price_min=floor,
            )
            for floor in (500, 750, 1000, 1250, 1500)
        ),
        Specification(
            "price_ceiling_30000",
            "real price ceiling",
            "Real price per m² ≤ R$30,000",
            price_max=30_000,
        ),
        *(
            Specification(
                f"ratio_floor_{floor:03d}",
                "declared/base floor",
                f"Declared/base ≥ {floor / 100:.2f}",
                ratio_min=floor / 100,
            )
            for floor in (30, 40, 50, 60, 70)
        ),
        Specification(
            "area_20_1000", "area window", "Area in [20, 1,000] m²", area_window=(20, 1000)
        ),
        Specification(
            "combined_reference_v2",
            "reference audit screen",
            "Real price per m² in [R$1,000, R$30,000] and area in [20, 1,000] m²",
            price_min=1000,
            price_max=30_000,
            area_window=(20, 1000),
        ),
        Specification(
            "apartments_only", "property type", "Apartments only", property_type="apartment"
        ),
        Specification("houses_only", "property type", "Houses only", property_type="house"),
        Specification(
            "huber_global",
            "estimator",
            "Retain the published model population",
            "Huber (global scale)",
        ),
        Specification(
            "huber_year",
            "estimator",
            "Retain the published model population",
            "Huber (year scales)",
        ),
    )
)


@dataclass(frozen=True)
class BaselineFit:
    """Baseline residuals and quarter-effect covariance, including the fixed base."""

    residuals: NDArray[np.float64]
    covariance: NDArray[np.float64]


@dataclass(frozen=True)
class SensitivityResults:
    """Protocol tables and numerical inputs retained for subsequent diagnostics."""

    specifications: pd.DataFrame
    index: pd.DataFrame
    decomposition: pd.DataFrame
    exclusions: pd.DataFrame
    population: pd.DataFrame
    baseline: BaselineFit
    huber_fits: dict[str, RobustFit]


@dataclass(frozen=True)
class _SpecificationFit:
    """Estimator results in the subset design's column order."""

    coefficients: NDArray[np.float64]
    covariance: NDArray[np.float64]
    residuals: NDArray[np.float64]
    weights: NDArray[np.float64]
    r_squared: float | None = None
    residual_sd: float | None = None
    huber: RobustFit | None = None


def sensitivity_design(population: pd.DataFrame) -> LinearDesign:
    """Build the published formula matrix and retain its original term encoding."""
    formula = smf.ols(FORMULA, data=population, missing="raise")
    slices = cast("DesignInfo", formula.data.model_spec).term_name_slices
    terms = np.repeat(list(slices), [span.stop - span.start for span in slices.values()])
    return LinearDesign(
        x=np.asarray(formula.exog),
        y=np.asarray(formula.endog),
        columns=np.array(formula.exog_names),
        terms=terms,
        quarters=population["quarter_label"].to_numpy(dtype=str),
        years=population["year"].to_numpy(dtype=int),
        property_types=population["property_type"].to_numpy(dtype=str),
        groups=np.asarray(population["neighbourhood"].cat.codes, dtype=np.intp),
    )


def specification_mask(
    population: pd.DataFrame, specification: Specification
) -> NDArray[np.bool_]:
    """Evaluate a screen once on the published population, retaining its boundaries."""
    tax_base = population["value_tax_base_brl"]
    if not tax_base.gt(0).all():
        raise DataError(
            "The published model population needs a positive tax base for every row."
        )
    keep = np.ones(len(population), dtype=bool)
    price = population["price_per_m2_brl_real"]
    if specification.price_min is not None:
        keep &= price.ge(specification.price_min).to_numpy()
    if specification.price_max is not None:
        keep &= price.le(specification.price_max).to_numpy()
    if specification.ratio_min is not None:
        keep &= (
            (population["value_declared_brl"] / tax_base).ge(specification.ratio_min).to_numpy()
        )
    if specification.area_window is not None:
        keep &= population["built_area_m2"].between(*specification.area_window).to_numpy()
    if specification.property_type is not None:
        keep &= population["property_type"].eq(specification.property_type).to_numpy()
    return keep


def _subset_columns(x: NDArray[np.float64], terms: NDArray[np.str_]) -> NDArray[np.bool_]:
    keep = np.any(x, axis=0)
    sums = x.sum(axis=0)
    for term in np.unique(terms[np.char.startswith(terms, "C(")]):
        levels = np.flatnonzero((terms == term) & keep)
        # When the original reference level vanishes, these indicators sum to
        # the intercept. Absorb the first remaining level into the intercept.
        if levels.size and sums[levels].sum() == len(x):
            keep[levels[0]] = False
    return keep


def specification_design(
    design: LinearDesign, mask: NDArray[np.bool_], *, spec_id: str
) -> LinearDesign:
    """Require the complete quarter window and remove unused factor columns."""
    quarters = design.quarters[mask]
    if tuple(np.unique(quarters)) != QUARTERS:
        missing = ", ".join(sorted(set(QUARTERS) - set(quarters)))
        raise SensitivityError(f"{spec_id} does not retain every protocol quarter: {missing}.")
    if mask.all():
        return design
    x = design.x[mask]
    keep = _subset_columns(x, design.terms)
    return LinearDesign(
        x=x if keep.all() else x[:, keep],
        y=design.y[mask],
        columns=design.columns[keep],
        terms=design.terms[keep],
        quarters=quarters,
        years=design.years[mask],
        property_types=design.property_types[mask],
        groups=design.groups[mask],
    )


def exclusion_counts(
    design: LinearDesign, mask: NDArray[np.bool_], spec_id: str
) -> pd.DataFrame:
    """Count removals in every year and type cell, including empty ones."""
    grid = pd.MultiIndex.from_product(
        [YEARS, RESIDENTIAL_TYPES], names=["year", "property_type"]
    )
    rows = pd.DataFrame(
        {"year": design.years, "property_type": design.property_types, "removed": ~mask}
    )
    counts = (
        rows.groupby(["year", "property_type"])["removed"]
        .agg(n_population="size", n_removed="sum")
        .reindex(grid, fill_value=0)
        .reset_index()
    )
    counts["share_removed"] = counts["n_removed"] / counts["n_population"].replace(0, np.nan)
    counts["share_removed"] = counts["share_removed"].fillna(0.0)
    counts.insert(0, "spec_id", spec_id)
    return counts


def _estimate_specification(
    design: LinearDesign, specification: Specification
) -> _SpecificationFit:
    if specification.estimator == "OLS":
        ols = sm.OLS(design.y, design.x).fit(
            cov_type="cluster", cov_kwds={"groups": design.groups}
        )
        return _SpecificationFit(
            coefficients=np.asarray(ols.params),
            covariance=np.asarray(ols.cov_params()),
            residuals=np.asarray(ols.resid),
            weights=np.ones(len(design.y)),
            r_squared=float(ols.rsquared),
            residual_sd=float(np.sqrt(ols.mse_resid)),
        )
    robust = fit_huber(design, by_year=specification.spec_id == "huber_year")
    return _SpecificationFit(
        coefficients=robust.coefficients,
        covariance=huber_covariance(design, robust),
        residuals=design.y - design.x @ robust.coefficients,
        weights=robust.weights,
        huber=robust,
    )


def _quarter_estimates(
    design: LinearDesign, fit: _SpecificationFit, spec_id: str
) -> tuple[pd.DataFrame, NDArray[np.float64]]:
    positions = {name: j for j, name in enumerate(design.columns)}
    indices = [positions[f"{QUARTER_TERM}[T.{quarter}]"] for quarter in QUARTERS[1:]]
    tau = np.r_[0.0, fit.coefficients[indices]]
    covariance = np.pad(fit.covariance[np.ix_(indices, indices)], (1, 0))
    se = np.sqrt(covariance.diagonal())
    bounds = INTERVAL_QUANTILE * se
    if not (np.isfinite(tau).all() and np.isfinite(se).all()):
        raise SensitivityError(f"{spec_id} produced non-finite quarter estimates or intervals.")
    _, counts = np.unique(design.quarters, return_counts=True)
    table = pd.DataFrame(
        {
            "spec_id": spec_id,
            "quarter": QUARTERS,
            "n": counts,
            "tau": tau,
            "se": se,
            "index": INDEX_BASE * np.exp(tau),
            "lower": INDEX_BASE * np.exp(tau - bounds),
            "upper": INDEX_BASE * np.exp(tau + bounds),
        }
    )
    return table, covariance


def _specification_summary(
    spec: Specification,
    trajectory: pd.DataFrame,
    fit: _SpecificationFit,
    design: LinearDesign,
    subset: LinearDesign,
) -> dict[str, object]:
    removed = len(design.y) - len(subset.y)
    endpoint = trajectory.iloc[-1]
    deviations = trajectory["log_dev_from_baseline"].abs()
    # Include the base quarter so that the first change is 2016Q2 minus 2016Q1.
    changes = trajectory["tau"].diff().iloc[1:]
    huber = fit.huber
    return {
        "spec_id": spec.spec_id,
        "family": spec.family,
        "estimator": spec.estimator,
        "rule": spec.rule,
        "n": len(subset.y),
        "n_removed": removed,
        "share_removed": removed / len(design.y),
        "dropped_columns": json.dumps(
            [c for c in design.columns if c not in subset.columns], ensure_ascii=False
        ),
        "min_quarter_n": trajectory["n"].min(),
        "r_squared": fit.r_squared,
        "residual_sd": fit.residual_sd,
        "huber_scale": float(huber.scales[0])
        if spec.spec_id == "huber_global" and huber
        else None,
        "share_downweighted": float(np.mean(huber.weights < 1)) if huber else None,
        "iterations": huber.iterations if huber else None,
        "score_max": huber.score_max if huber else None,
        "fixed_point_gap": huber.fixed_point_gap if huber else None,
        "index_2016Q3": trajectory.loc[trajectory["quarter"].eq("2016Q3"), "index"].iloc[0],
        "index_2025Q4": endpoint["index"],
        "lower_2025Q4": endpoint["lower"],
        "upper_2025Q4": endpoint["upper"],
        "cumulative_log_change": endpoint["tau"],
        "max_abs_log_dev": deviations.max(),
        "quarter_of_max_dev": trajectory["quarter"].iloc[deviations.argmax()],
        "rms_log_dev": np.sqrt(deviations.pow(2).mean()),
        "lag1_autocorr_changes": changes.autocorr(lag=1),
    }


def run_specifications(frame: pd.DataFrame) -> SensitivityResults:
    """Fit every fixed specification sequentially on subsets of one formula design."""
    population = model_population(frame)
    design = sensitivity_design(population)
    summaries: list[dict[str, object]] = []
    trajectories: list[pd.DataFrame] = []
    decompositions: list[pd.DataFrame] = []
    exclusions: list[pd.DataFrame] = []
    huber_fits: dict[str, RobustFit] = {}
    baseline: BaselineFit | None = None
    for spec in PROTOCOL.specifications:
        mask = specification_mask(population, spec)
        subset = specification_design(design, mask, spec_id=spec.spec_id)
        fit = _estimate_specification(subset, spec)
        trajectory, covariance = _quarter_estimates(subset, fit, spec.spec_id)
        if spec.spec_id == "baseline":
            baseline = BaselineFit(fit.residuals, covariance)
        if fit.huber is not None:
            huber_fits[spec.spec_id] = fit.huber
        reference = trajectories[0] if trajectories else trajectory
        trajectory["log_dev_from_baseline"] = trajectory["tau"] - reference["tau"]
        summaries.append(_specification_summary(spec, trajectory, fit, design, subset))
        trajectories.append(trajectory)
        parts = weighted_decomposition(subset, fit.coefficients, fit.weights, TERMS)
        decompositions.append(
            pd.DataFrame(
                {
                    "spec_id": spec.spec_id,
                    "quarter": QUARTERS,
                    "mean_kind": "huber_weighted" if fit.huber else "unweighted",
                    **parts,
                }
            )
        )
        exclusions.append(exclusion_counts(design, mask, spec.spec_id))
        del subset, fit
    assert baseline is not None
    return SensitivityResults(
        pd.DataFrame(summaries),
        pd.concat(trajectories, ignore_index=True),
        pd.concat(decompositions, ignore_index=True),
        pd.concat(exclusions, ignore_index=True),
        population,
        baseline,
        huber_fits,
    )
