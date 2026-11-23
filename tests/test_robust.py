"""Check Huber point estimates, clustered inference and weighted composition."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
import statsmodels.formula.api as smf
from threadpoolctl import threadpool_limits

from bh_itbi.config import IDENTITY_TOLERANCE
from bh_itbi.models import (
    COMPOSITION_TERMS,
    FORMULA,
    QUARTER_TERM,
    hedonic_composition,
    model_population,
)
from bh_itbi.robust import (
    LinearDesign,
    RobustFitError,
    fit_huber,
    huber_covariance,
    weighted_decomposition,
)


@pytest.fixture
def design() -> LinearDesign:
    rng = np.random.default_rng(140)
    quarter = np.repeat(np.arange(8), 160)
    years = 2016 + quarter // 4
    groups = rng.integers(0, 15, len(quarter))
    area = rng.normal(4.5, 1, len(quarter))
    house = rng.integers(0, 2, len(quarter))
    x = np.column_stack(
        (np.ones(len(quarter)), quarter[:, None] == np.arange(1, 8), area, house)
    )
    y = x @ np.r_[8, np.arange(1, 8) / 30, -0.15, -0.18]
    y += rng.normal(0, np.where(years == 2016, 0.13, 0.4))
    return LinearDesign(
        x=x,
        y=y,
        columns=np.array(["intercept", *[f"q{i}" for i in range(1, 8)], "area", "house"]),
        terms=np.array(["intercept", *(["quarter"] * 7), "area", "type"]),
        quarters=np.array(
            [f"{year}Q{q % 4 + 1}" for year, q in zip(years, quarter, strict=True)]
        ),
        years=years,
        property_types=np.where(house, "house", "apartment"),
        groups=groups,
    )


def test_no_clipping_reproduces_clustered_ols(design: LinearDesign) -> None:
    ols = sm.OLS(design.y, design.x).fit(cov_type="cluster", cov_kwds={"groups": design.groups})
    fit = fit_huber(design, tuning=np.inf, by_year=True)
    np.testing.assert_allclose(fit.coefficients, ols.params, rtol=1e-10, atol=0)
    np.testing.assert_allclose(
        huber_covariance(design, fit), ols.cov_params(), rtol=1e-8, atol=0
    )


@pytest.mark.parametrize("by_year", [False, True])
def test_converged_fit_solves_score_and_minimises_conditional_loss(
    design: LinearDesign, by_year: bool
) -> None:
    fit = fit_huber(design, by_year=by_year)
    assert fit.score_max < 1e-10
    assert fit.fixed_point_gap < 1e-6
    assert fit.quarter_residual_max < IDENTITY_TOLERANCE

    def loss(coefficients: np.ndarray) -> float:
        absolute = np.abs(design.y - design.x @ coefficients)
        clipped = np.minimum(absolute, fit.thresholds)
        return float((absolute * clipped - 0.5 * clipped**2).sum())

    optimum = loss(fit.coefficients)
    perturbations = 1e-4 * np.random.default_rng(288).normal(size=(12, len(fit.coefficients)))
    assert all(loss(fit.coefficients + delta) >= optimum for delta in perturbations)
    contributions = weighted_decomposition(
        design,
        fit.coefficients,
        fit.weights,
        {"adjusted": "quarter", "area": "area", "type": "type"},
    )
    assert np.max(np.abs(contributions["identity_error"])) < IDENTITY_TOLERANCE


def test_unit_weight_decomposition_matches_published_ols(snapshot_frame: pd.DataFrame) -> None:
    population = model_population(snapshot_frame)
    formula = smf.ols(FORMULA, data=population)
    with threadpool_limits(limits=2):
        fit = formula.fit()
    design = LinearDesign(
        x=formula.exog,
        y=formula.endog,
        columns=np.array(formula.exog_names),
        terms=np.repeat(
            list(formula.data.model_spec.term_name_slices),
            [sl.stop - sl.start for sl in formula.data.model_spec.term_name_slices.values()],
        ),
        quarters=population["quarter_label"].to_numpy(dtype=str),
        years=population["year"].to_numpy(dtype=int),
        property_types=population["property_type"].to_numpy(dtype=str),
        groups=population["neighbourhood"].cat.codes.to_numpy(),
    )
    terms = {**COMPOSITION_TERMS, "adjusted": QUARTER_TERM}
    result = weighted_decomposition(
        design, fit.params.to_numpy(), np.ones(len(population)), terms
    )
    expected = hedonic_composition(fit, population["quarter_label"]).rename(
        columns={"raw": "mean_change"}
    )
    for term, values in result.items():
        np.testing.assert_allclose(values, expected[term], atol=1e-10, rtol=0)


def test_huber_quarter_effects_resist_early_negative_contamination(
    design: LinearDesign,
) -> None:
    rng = np.random.default_rng(376)
    affected = rng.choice(
        np.flatnonzero(design.quarters == "2016Q2"), len(design.y) // 20, False
    )
    contaminated = design.y.copy()
    contaminated[affected] -= 4.0
    sample = replace(design, y=contaminated)
    robust = fit_huber(sample).coefficients[1:8]
    ols = np.linalg.lstsq(sample.x, sample.y, rcond=None)[0][1:8]
    expected = np.arange(1, 8) / 30
    assert np.linalg.norm(robust - expected) < np.linalg.norm(ols - expected)


def test_one_year_scale_equals_global_scale(design: LinearDesign) -> None:
    single_year = replace(design, years=np.full_like(design.years, 2016))
    global_fit = fit_huber(single_year)
    year_fit = fit_huber(single_year, by_year=True)
    for name in ("coefficients", "weights", "scales", "thresholds"):
        np.testing.assert_array_equal(getattr(year_fit, name), getattr(global_fit, name))
    assert year_fit.iterations == global_fit.iterations


def test_year_scales_reflect_different_residual_dispersion(design: LinearDesign) -> None:
    first, second = fit_huber(design, by_year=True).scales
    assert 0.10 < first < 0.17
    assert 0.33 < second < 0.47


def test_fails_when_irls_does_not_converge(design: LinearDesign) -> None:
    with pytest.raises(RobustFitError, match="did not converge"):
        fit_huber(design, max_iterations=1)


def test_sandwich_rejects_singular_bread(design: LinearDesign) -> None:
    fit = fit_huber(design)
    no_active_rows = replace(fit, thresholds=np.zeros(len(design.y)))
    with pytest.raises(RobustFitError, match="sandwich bread is singular"):
        huber_covariance(design, no_active_rows)
