"""Explicit, offline model preparation. Nothing in this module fits on a click.

The fixed population, formula and covariance estimator follow notebook cell 23.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bh_itbi.analysis import diagnostic_rows

FORMULA = (
    "log_price ~ log_area + C(building_age_band) + C(property_type)"
    " + C(neighbourhood) + C(quarter_label)"
)


def model_population(frame: pd.DataFrame) -> pd.DataFrame:
    """Complete-case residential sample, neighbourhoods with >= 100 records."""
    data = diagnostic_rows(frame)
    data = data.loc[
        data["year"].between(2016, 2025)
        & data["price_per_m2_brl_real"].notna()
        & data["building_age_band"].notna()
        & data["neighbourhood"].notna()
    ].copy()
    if not data["price_per_m2_brl_real"].gt(0).all():
        raise ValueError("Valores reais não positivos impedem o logaritmo do modelo.")
    sizes = data["neighbourhood"].value_counts()
    data = data.loc[data["neighbourhood"].isin(sizes.index[sizes >= 100])].copy()
    # Remove unused levels so the formula matches the notebook's string columns.
    for column in ["neighbourhood", "building_age_band", "property_type"]:
        data[column] = data[column].astype("category").cat.remove_unused_categories()
    data["quarter_label"] = data["transaction_date"].dt.to_period("Q").astype(str)
    data["log_price"] = np.log(data["price_per_m2_brl_real"])
    data["log_area"] = np.log(data["built_area_m2"])
    return data


def fit_hedonic(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """OLS log-price index with neighbourhood-clustered 95% confidence intervals."""
    import statsmodels.formula.api as smf

    data = model_population(frame)
    if data.empty or data["neighbourhood"].nunique() < 2:
        raise ValueError("Amostra insuficiente para o modelo hedônico agrupado por bairro.")
    fit = smf.ols(FORMULA, data=data).fit(
        cov_type="cluster", cov_kwds={"groups": data["neighbourhood"].cat.codes.to_numpy()}
    )
    terms = fit.params.index[fit.params.index.str.startswith("C(quarter_label)[T.")]
    intervals = fit.conf_int(alpha=0.05).loc[terms]
    result = pd.DataFrame(
        {
            "quarter": terms.str.extract(r"T\.(\d{4}Q[1-4])\]")[0].to_numpy(),
            "index": 100 * np.exp(fit.params.loc[terms].to_numpy()),
            "lower": 100 * np.exp(intervals[0].to_numpy()),
            "upper": 100 * np.exp(intervals[1].to_numpy()),
        }
    )
    base = data["quarter_label"].min()
    result = pd.concat(
        [
            pd.DataFrame([{"quarter": base, "index": 100.0, "lower": 100.0, "upper": 100.0}]),
            result,
        ],
        ignore_index=True,
    ).sort_values("quarter")
    raw = data.groupby("quarter_label", observed=True)["price_per_m2_brl_real"].median()
    result["raw_index"] = (100 * raw / raw.loc[base]).reindex(result["quarter"]).to_numpy()
    result["date"] = pd.PeriodIndex(result["quarter"], freq="Q").start_time
    result["n"] = (
        data.groupby("quarter_label", observed=True)
        .size()
        .reindex(result["quarter"])
        .to_numpy()
    )
    if not np.isfinite(result[["index", "lower", "upper", "raw_index"]]).all().all():
        raise ValueError("O modelo produziu estimativas ou intervalos não finitos.")
    metadata = {
        "n": int(fit.nobs),
        "r_squared": float(fit.rsquared),
        "area_elasticity": float(fit.params["log_area"]),
        "neighbourhoods": int(data["neighbourhood"].nunique()),
        "base_quarter": base,
        "formula": FORMULA,
        "covariance": "cluster (neighbourhood)",
        "confidence_level": 0.95,
        "start_date": "2016-01-01",
        "end_date": "2025-12-31",
        "property_types": ["apartment", "house"],
    }
    return result, metadata
