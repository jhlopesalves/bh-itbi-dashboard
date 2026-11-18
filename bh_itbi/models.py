"""Offline estimation and persistence for the hedonic index and trajectory clusters."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

import numpy as np
import pandas as pd

from bh_itbi.cluster import ClusterMetadata, cluster_trajectories
from bh_itbi.config import (
    CLUSTER_K,
    CLUSTER_K_RANGE,
    END_YEAR,
    HEDONIC_ALPHA,
    HEDONIC_CONFIDENCE_LEVEL,
    HEDONIC_MIN_NEIGHBOURHOODS,
    HEDONIC_NEIGHBOURHOOD_MINIMUM,
    IDENTITY_TOLERANCE,
    INDEX_BASE,
    MODEL_DIR,
    MODEL_VERSION,
    RESIDENTIAL_TYPES,
    REVISION,
    SOURCE_SHA256,
    START_YEAR,
)
from bh_itbi.data import (
    atomic_json,
    atomic_parquet,
    file_sha256,
)
from bh_itbi.filters import positive_area_rows

if TYPE_CHECKING:
    from statsmodels.regression.linear_model import RegressionResultsWrapper

logger = logging.getLogger(__name__)

__all__ = [
    "COMPOSITION_TERMS",
    "FORMULA",
    "QUARTER_TERM",
    "HedonicMetadata",
    "ModelMetadata",
    "PreparedModels",
    "fit_hedonic",
    "hedonic_complete_cases",
    "hedonic_composition",
    "load_models",
    "model_population",
    "prepare_models",
]
FORMULA = (
    "log_price ~ log_area + C(building_age_band) + C(property_type)"
    " + C(neighbourhood) + C(quarter_label)"
)
COMPOSITION_TERMS: dict[str, str] = {
    "neighbourhood": "C(neighbourhood)",
    "area": "log_area",
    "age_band": "C(building_age_band)",
    "property_type": "C(property_type)",
}
QUARTER_TERM = "C(quarter_label)"


class HedonicMetadata(TypedDict):
    """Summary statistics and specification metadata for the fitted hedonic OLS model."""

    n: int
    r_squared: float
    area_elasticity: float
    neighbourhoods: int
    base_quarter: str
    formula: str
    covariance: str
    confidence_level: float
    start_date: str
    end_date: str
    property_types: list[str]


class ModelMetadata(TypedDict):
    """Persisted manifest binding model tables to the pinned source contract."""

    revision: str
    source_sha256: str
    model_version: str
    hedonic: HedonicMetadata
    clusters: ClusterMetadata
    tables_sha256: dict[str, str]


@dataclass(frozen=True)
class PreparedModels:
    """Validated offline hedonic index and k-means neighbourhood trajectory tables."""

    metadata: ModelMetadata
    hedonic: pd.DataFrame
    members: pd.DataFrame
    centres: pd.DataFrame


def hedonic_complete_cases(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply the common hedonic eligibility rules to prepared transactions."""
    data = positive_area_rows(frame)
    data = data.loc[
        data["price_per_m2_brl_real"].notna()
        & data["building_age_band"].notna()
        & data["neighbourhood"].notna()
    ]
    if not data["price_per_m2_brl_real"].gt(0).all():
        raise ValueError("The model cannot take logarithms of non-positive real prices.")
    return data


def model_population(frame: pd.DataFrame) -> pd.DataFrame:
    """Complete-case residential sample, neighbourhoods with >= 100 records."""
    data = hedonic_complete_cases(frame.loc[frame["year"].between(START_YEAR, END_YEAR)])
    sizes = data["neighbourhood"].value_counts()
    data = data.loc[
        data["neighbourhood"].isin(sizes.index[sizes >= HEDONIC_NEIGHBOURHOOD_MINIMUM])
    ].copy()
    # Remove unused levels so the formula matches the notebook's string columns.
    for column in ["neighbourhood", "building_age_band", "property_type"]:
        data[column] = data[column].astype("category").cat.remove_unused_categories()
    data["quarter_label"] = data["transaction_date"].dt.to_period("Q").astype(str)
    data["log_price"] = np.log(data["price_per_m2_brl_real"])
    data["log_area"] = np.log(data["built_area_m2"])
    return data


def hedonic_composition(fit: RegressionResultsWrapper, quarters: pd.Series) -> pd.DataFrame:
    """Decompose the fitted sample's quarterly log means relative to the base."""
    slices = fit.model.data.model_spec.term_name_slices
    terms = {**COMPOSITION_TERMS, "adjusted": QUARTER_TERM}
    if extra := set(slices) - {"Intercept", *terms.values()}:
        raise ValueError(f"Model terms outside the decomposition: {', '.join(sorted(extra))}")

    design = fit.model.exog
    coefficients = fit.params.to_numpy()
    components = {
        label: design[:, slices[term]] @ coefficients[slices[term]]
        for label, term in terms.items()
    }
    components["raw"] = fit.model.endog
    by_quarter = pd.DataFrame(components).groupby(quarters.to_numpy()).mean()
    changes = by_quarter - by_quarter.iloc[0]
    changes["identity_error"] = (
        changes["raw"] - changes["adjusted"] - changes[list(COMPOSITION_TERMS)].sum(axis=1)
    )
    # OLS with quarter indicators gives zero mean residual within each quarter.
    if not changes["identity_error"].abs().lt(IDENTITY_TOLERANCE).all():
        raise ValueError("The hedonic decomposition fails the accounting identity.")
    return changes


def _hedonic_result_table(
    fit: RegressionResultsWrapper, data: pd.DataFrame
) -> tuple[pd.DataFrame, str]:
    """Assemble and validate the quarterly index, bounds and composition."""
    terms = fit.params.index[fit.params.index.str.startswith("C(quarter_label)[T.")]
    intervals = fit.conf_int(alpha=HEDONIC_ALPHA).loc[terms]
    result = pd.DataFrame(
        {
            "quarter": terms.str.extract(r"T\.(\d{4}Q[1-4])\]")[0].to_numpy(),
            "hedonic_index": INDEX_BASE * np.exp(fit.params.loc[terms].to_numpy()),
            "lower": INDEX_BASE * np.exp(intervals[0].to_numpy()),
            "upper": INDEX_BASE * np.exp(intervals[1].to_numpy()),
        }
    )
    base = data["quarter_label"].min()
    baseline = float(INDEX_BASE)
    result = pd.concat(
        [
            pd.DataFrame(
                [
                    {
                        "quarter": base,
                        "hedonic_index": baseline,
                        "lower": baseline,
                        "upper": baseline,
                    }
                ]
            ),
            result,
        ],
        ignore_index=True,
    ).sort_values("quarter")
    composition = hedonic_composition(fit, data["quarter_label"]).reindex(result["quarter"])
    result["raw_geometric_mean"] = INDEX_BASE * np.exp(composition["raw"].to_numpy())
    composition_columns = [*COMPOSITION_TERMS, "identity_error"]
    result[composition_columns] = composition[composition_columns].to_numpy()
    result["date"] = pd.PeriodIndex(result["quarter"], freq="Q").start_time
    result["n"] = (
        data.groupby("quarter_label", observed=True)
        .size()
        .reindex(result["quarter"])
        .to_numpy()
    )
    columns = [
        "hedonic_index",
        "lower",
        "upper",
        "raw_geometric_mean",
        *composition_columns,
    ]
    if not np.isfinite(result[columns]).all().all():
        raise ValueError("The model produced non-finite estimates or intervals.")
    return result, base


def fit_hedonic(frame: pd.DataFrame) -> tuple[pd.DataFrame, HedonicMetadata]:
    """Fit the OLS index, clustered 95% intervals and same-sample composition."""
    # Estimation runs in the build process. Serving must not import statsmodels.
    import statsmodels.formula.api as smf  # noqa: PLC0415

    data = model_population(frame)
    if data.empty or data["neighbourhood"].nunique() < HEDONIC_MIN_NEIGHBOURHOODS:
        raise ValueError("Insufficient data for the hedonic model clustered by neighbourhood.")
    # The quarter labels and clustering codes must align with every fitted row.
    fit = smf.ols(FORMULA, data=data, missing="raise").fit(
        cov_type="cluster", cov_kwds={"groups": data["neighbourhood"].cat.codes.to_numpy()}
    )
    result, base = _hedonic_result_table(fit, data)
    metadata: HedonicMetadata = {
        "n": int(fit.nobs),
        "r_squared": float(fit.rsquared),
        "area_elasticity": float(fit.params["log_area"]),
        "neighbourhoods": int(data["neighbourhood"].nunique()),
        "base_quarter": base,
        "formula": FORMULA,
        "covariance": "cluster (neighbourhood)",
        "confidence_level": HEDONIC_CONFIDENCE_LEVEL,
        "start_date": f"{START_YEAR}-01-01",
        "end_date": f"{END_YEAR}-12-31",
        "property_types": list(RESIDENTIAL_TYPES),
    }
    return result, metadata


def prepare_models(frame: pd.DataFrame, *, force: bool = False) -> ModelMetadata:
    """Run explicitly before serving; publish metadata after every table exists."""
    if not force and (existing := load_models()) is not None:
        return existing.metadata
    print(
        f"Estimating the hedonic index with a {HEDONIC_CONFIDENCE_LEVEL:.0%} "
        "confidence interval clustered by neighbourhood…",
        flush=True,
    )
    hedonic, hedonic_metadata = fit_hedonic(frame)
    print(
        f"Clustering neighbourhood trajectories "
        f"(k={CLUSTER_K_RANGE[0]}–{CLUSTER_K_RANGE[-1]}, displaying k={CLUSTER_K})…",
        flush=True,
    )
    members, centres, cluster_metadata = cluster_trajectories(frame)
    atomic_parquet(hedonic, MODEL_DIR / "hedonic.parquet")
    atomic_parquet(members, MODEL_DIR / "members.parquet")
    atomic_parquet(centres, MODEL_DIR / "centres.parquet")
    metadata: ModelMetadata = {
        "revision": REVISION,
        "source_sha256": SOURCE_SHA256,
        "model_version": MODEL_VERSION,
        "hedonic": hedonic_metadata,
        "clusters": cluster_metadata,
        "tables_sha256": {
            name: file_sha256(MODEL_DIR / f"{name}.parquet")
            for name in ("hedonic", "members", "centres")
        },
    }
    atomic_json(metadata, MODEL_DIR / "metadata.json")
    return metadata


def load_models(directory: Path | None = None) -> PreparedModels | None:
    """Read only tables for this exact source/model contract; never fit here.

    Unlike ``data.py``, which raises ``DataError`` when the transaction cache is
    incompatible, ``load_models`` logs the specific failed check and returns ``None``
    so local exploration can still serve the overview and diagnostics tabs while
    production startup (``create_app(require_prepared=True)``) rejects ``None``.
    """
    directory = MODEL_DIR if directory is None else directory
    metadata_path = directory / "metadata.json"
    files = {name: directory / f"{name}.parquet" for name in ("hedonic", "members", "centres")}
    if not metadata_path.exists() or not all(path.exists() for path in files.values()):
        logger.warning("Model tables are missing from %s.", directory)
        return None
    metadata: ModelMetadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    identity = {
        "revision": REVISION,
        "source_sha256": SOURCE_SHA256,
        "model_version": MODEL_VERSION,
    }
    for key, expected in identity.items():
        if metadata.get(key) != expected:
            logger.warning(
                "Model manifest in %s is incompatible (%s mismatch).", directory, key
            )
            return None
    tables_sha = metadata.get("tables_sha256", {})
    for name, path in files.items():
        if tables_sha.get(name) != file_sha256(path):
            logger.warning("SHA-256 mismatch for model table %s.", path)
            return None
    return PreparedModels(
        metadata=metadata,
        hedonic=pd.read_parquet(files["hedonic"], use_threads=False),
        members=pd.read_parquet(files["members"], use_threads=False),
        centres=pd.read_parquet(files["centres"], use_threads=False),
    )
