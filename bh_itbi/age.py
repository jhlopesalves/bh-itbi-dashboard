"""Age premiums for the selected recent apartments, in natural log points."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from bh_itbi.analysis import AGE_LABELS
from bh_itbi.models import hedonic_complete_cases

AGE_YEARS = (2023, 2025)
AGE_REFERENCE = "26_plus"
AGE_MINIMUM = 15
AGE_GROUPS = ("Bairro", "Área", "Trimestre")
AGE_INTERVAL = 1.96
FEW_NEIGHBOURHOODS = "Ajuste indisponível: a seleção tem menos de 20 bairros."
UNIDENTIFIED_ADJUSTMENT = "Ajuste indisponível: a seleção não identifica todos os efeitos."
MISSING_REFERENCE = "São necessárias 15 transações na faixa de referência (26 anos ou mais)."


@dataclass(frozen=True)
class AgePremiums:
    """Band estimates, completeness and reasons an estimate is unavailable."""

    table: pd.DataFrame
    excluded: dict[str, int]
    neighbourhoods: int
    unavailable: str | None = None


def within_neighbourhood(
    y: NDArray[np.float64], x: NDArray[np.float64], neighbourhood: pd.Categorical
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]] | None:
    """Return slopes, CR1 standard errors and fitted neighbourhood intercepts.

    The codes cover consecutive, populated categories. Demeaning absorbs one
    intercept per neighbourhood. The CR1 correction still counts every absorbed
    intercept, as in full OLS with an intercept and neighbourhood dummies.
    """
    codes = neighbourhood.codes
    groups = len(neighbourhood.categories)
    counts = np.bincount(codes)
    values = np.column_stack((y, x))
    means = np.zeros((groups, values.shape[1]))
    np.add.at(means, codes, values)
    means /= counts[:, None]
    within = values - means[codes]
    response, design = within[:, 0], within[:, 1:]
    left, singular, right = np.linalg.svd(design, full_matrices=False)
    tolerance = np.finfo(float).eps * max(design.shape) * singular[0]
    residual_df = len(y) - groups - x.shape[1]
    if residual_df <= 0 or singular[-1] <= tolerance:
        return None

    inverse = (right.T / singular) @ left.T
    beta = inverse @ response
    residuals = response - design @ beta
    # The cluster sandwich is a sum of squares of projected cluster scores.
    scores = np.zeros((groups, len(beta)))
    np.add.at(scores, codes, inverse.T * residuals[:, None])
    correction = groups / (groups - 1) * (len(y) - 1) / residual_df
    se = np.sqrt(correction * np.square(scores).sum(axis=0))
    intercepts = means[:, 0] - means[:, 1:] @ beta
    return beta, se, intercepts


def age_premiums(frame: pd.DataFrame) -> AgePremiums:
    """Compare geometric means, then decompose the adjusted selection if identified."""
    recent = frame.loc[
        frame["property_type"].eq("apartment")
        & frame["year"].between(*AGE_YEARS)
        & frame["building_age_band"].isin(AGE_LABELS)
    ]
    data = hedonic_complete_cases(recent)
    band = data["building_age_band"]
    counts = band.value_counts().reindex(AGE_LABELS, fill_value=0)
    bands = counts.index[counts >= AGE_MINIMUM].tolist()
    excluded = {str(key): int(n) for key, n in counts.items() if n < AGE_MINIMUM}
    data = data.loc[band.isin(bands)]
    groups = data["neighbourhood"].nunique()
    if recent.empty:
        return AgePremiums(pd.DataFrame(), {}, groups)
    if AGE_REFERENCE not in bands:
        return AgePremiums(pd.DataFrame(), excluded, groups, MISSING_REFERENCE)

    band = data["building_age_band"]
    y = np.log(data["price_per_m2_brl_real"].to_numpy())
    means = pd.Series(y).groupby(band.to_numpy()).mean().reindex(bands)
    table = pd.DataFrame(
        {
            "n": counts.loc[bands],
            "geometric_mean": np.exp(means),
            "observed": means - means[AGE_REFERENCE],
        }
    )
    if groups < 20:
        return AgePremiums(table, excluded, groups, FEW_NEIGHBOURHOODS)
    if len(bands) == 1:
        return AgePremiums(table, excluded, groups)

    contrasts = [key for key in bands if key != AGE_REFERENCE]
    ages = band.to_numpy()[:, None] == np.asarray(contrasts)
    area = np.log(data["built_area_m2"].to_numpy())
    quarter = data["quarter"].to_numpy()
    quarters = quarter[:, None] == np.unique(quarter)[1:]
    x = np.column_stack((ages, area, quarters))
    neighbourhood = pd.Categorical(data["neighbourhood"]).remove_unused_categories()
    fit = within_neighbourhood(y, x, neighbourhood)
    if fit is None:
        return AgePremiums(table, excluded, groups, UNIDENTIFIED_ADJUSTMENT)
    beta, se, intercepts = fit

    area_index = len(contrasts)
    components = (
        pd.DataFrame(
            {
                "Bairro": intercepts[neighbourhood.codes],
                "Área": area * beta[area_index],
                "Trimestre": quarters @ beta[area_index + 1 :],
            }
        )
        .groupby(band.to_numpy())
        .mean()
    )
    table[list(AGE_GROUPS)] = components - components.loc[AGE_REFERENCE]
    adjusted = pd.Series(beta[:area_index], index=contrasts).reindex(bands, fill_value=0)
    margin = pd.Series(AGE_INTERVAL * se[:area_index], index=contrasts).reindex(
        bands, fill_value=0
    )
    table["adjusted"] = adjusted
    table["lower"] = adjusted - margin
    table["upper"] = adjusted + margin
    table["identity_error"] = table["observed"] - adjusted - table[list(AGE_GROUPS)].sum(axis=1)
    if not table["identity_error"].abs().lt(1e-8).all():
        raise ValueError("A decomposição por idade não satisfaz a identidade contábil.")
    return AgePremiums(table, excluded, groups)
