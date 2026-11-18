"""Explicit, offline model preparation. Nothing in this module fits on a click.

The fixed population, formulas, covariance estimator and clustering parameters
are those of notebook cells 23 and 26. Tables, rather than pickled fitted models,
are persisted with the source revision and a versioned analytical contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from bh_itbi.analysis import diagnostic_rows
from bh_itbi.data import (
    CACHE_DIR,
    REVISION,
    SOURCE_SHA256,
    atomic_json,
    atomic_parquet,
    file_sha256,
)

if TYPE_CHECKING:
    from statsmodels.regression.linear_model import RegressionResultsWrapper

MODEL_VERSION = "v2"
MODEL_DIR = CACHE_DIR / f"models-{MODEL_VERSION}"
FORMULA = (
    "log_price ~ log_area + C(building_age_band) + C(property_type)"
    " + C(neighbourhood) + C(quarter_label)"
)
COMPOSITION_TERMS = {
    "Bairro": "C(neighbourhood)",
    "Área": "log_area",
    "Faixa de idade": "C(building_age_band)",
    "Tipo": "C(property_type)",
}
QUARTER_TERM = "C(quarter_label)"


def hedonic_complete_cases(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply the common hedonic eligibility rules to prepared transactions."""
    data = diagnostic_rows(frame)
    data = data.loc[
        data["price_per_m2_brl_real"].notna()
        & data["building_age_band"].notna()
        & data["neighbourhood"].notna()
    ]
    if not data["price_per_m2_brl_real"].gt(0).all():
        raise ValueError("Valores reais não positivos impedem o logaritmo do modelo.")
    return data


def model_population(frame: pd.DataFrame) -> pd.DataFrame:
    """Complete-case residential sample, neighbourhoods with >= 100 records."""
    data = hedonic_complete_cases(frame.loc[frame["year"].between(2016, 2025)])
    sizes = data["neighbourhood"].value_counts()
    data = data.loc[data["neighbourhood"].isin(sizes.index[sizes >= 100])].copy()
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
        raise ValueError(f"Termos do modelo fora da decomposição: {', '.join(sorted(extra))}")

    design = fit.model.exog
    coefficients = fit.params.to_numpy()
    components = {
        label: design[:, slices[term]] @ coefficients[slices[term]]
        for label, term in terms.items()
    }
    components["raw"] = fit.model.endog
    by_quarter = pd.DataFrame(components).groupby(quarters.to_numpy()).mean()
    changes = by_quarter - by_quarter.iloc[0]
    changes["erro_identidade"] = (
        changes["raw"] - changes["adjusted"] - changes[list(COMPOSITION_TERMS)].sum(axis=1)
    )
    # OLS with quarter indicators gives zero mean residual within each quarter.
    if not changes["erro_identidade"].abs().lt(1e-8).all():
        raise ValueError("A decomposição hedônica não satisfaz a identidade contábil.")
    return changes


def fit_hedonic(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Fit the OLS index, clustered 95% intervals and same-sample composition."""
    import statsmodels.formula.api as smf

    data = model_population(frame)
    if data.empty or data["neighbourhood"].nunique() < 2:
        raise ValueError("Amostra insuficiente para o modelo hedônico agrupado por bairro.")
    # The quarter labels and clustering codes must align with every fitted row.
    fit = smf.ols(FORMULA, data=data, missing="raise").fit(
        cov_type="cluster", cov_kwds={"groups": data["neighbourhood"].cat.codes.to_numpy()}
    )
    terms = fit.params.index[fit.params.index.str.startswith("C(quarter_label)[T.")]
    intervals = fit.conf_int(alpha=0.05).loc[terms]
    result = pd.DataFrame(
        {
            "quarter": terms.str.extract(r"T\.(\d{4}Q[1-4])\]")[0].to_numpy(),
            "indice_hedonico": 100 * np.exp(fit.params.loc[terms].to_numpy()),
            "lower": 100 * np.exp(intervals[0].to_numpy()),
            "upper": 100 * np.exp(intervals[1].to_numpy()),
        }
    )
    base = data["quarter_label"].min()
    result = pd.concat(
        [
            pd.DataFrame(
                [{"quarter": base, "indice_hedonico": 100.0, "lower": 100.0, "upper": 100.0}]
            ),
            result,
        ],
        ignore_index=True,
    ).sort_values("quarter")
    composition = hedonic_composition(fit, data["quarter_label"]).reindex(result["quarter"])
    result["media_geometrica_bruta"] = 100 * np.exp(composition["raw"].to_numpy())
    composition_columns = [*COMPOSITION_TERMS, "erro_identidade"]
    result[composition_columns] = composition[composition_columns].to_numpy()
    result["date"] = pd.PeriodIndex(result["quarter"], freq="Q").start_time
    result["n"] = (
        data.groupby("quarter_label", observed=True)
        .size()
        .reindex(result["quarter"])
        .to_numpy()
    )
    columns = [
        "indice_hedonico",
        "lower",
        "upper",
        "media_geometrica_bruta",
        *composition_columns,
    ]
    if not np.isfinite(result[columns]).all().all():
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


def cluster_trajectories(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Fixed k=4 on all ten annual real-median indices, with seed 42/n_init 20."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    data = diagnostic_rows(frame)
    data = data.loc[
        data["property_type"].eq("apartment")
        & data["year"].between(2016, 2025)
        & data["price_per_m2_brl_real"].notna()
    ]
    yearly = (
        data.groupby(["neighbourhood", "year"], observed=True)
        .agg(median=("price_per_m2_brl_real", "median"), n=("price_per_m2_brl_real", "size"))
        .reset_index()
    )
    yearly = yearly.loc[yearly["n"] >= 30]
    trajectories = yearly.pivot(index="neighbourhood", columns="year", values="median")
    trajectories = trajectories.reindex(columns=range(2016, 2026)).dropna()
    trajectories = 100 * trajectories.div(trajectories[2016], axis=0)
    if len(trajectories) < 7:
        raise ValueError(
            "Menos de sete bairros com cobertura anual suficiente para avaliar k=2…6."
        )
    fits = {
        k: KMeans(n_clusters=k, n_init=20, random_state=42).fit(trajectories)
        for k in range(2, 7)
    }
    silhouettes = {
        k: float(silhouette_score(trajectories, fit.labels_)) for k, fit in fits.items()
    }
    fit = fits[4]
    order = np.argsort(-fit.cluster_centers_[:, -1])
    display_group = {cluster: rank for rank, cluster in enumerate(order, start=1)}
    groups = pd.Series(
        [display_group[label] for label in fit.labels_], index=trajectories.index, name="group"
    )
    members = (
        trajectories.rename_axis("neighbourhood")
        .reset_index()
        .melt(id_vars="neighbourhood", var_name="year", value_name="index")
    )
    members["group"] = members["neighbourhood"].map(groups)
    members = members.merge(yearly[["neighbourhood", "year", "n"]], validate="one_to_one")
    centres = pd.DataFrame(fit.cluster_centers_[order], columns=trajectories.columns)
    centres["group"] = range(1, 5)
    centres = centres.melt(id_vars="group", var_name="year", value_name="index")
    metadata = {
        "n_neighbourhoods": len(trajectories),
        "k": 4,
        "n_init": 20,
        "random_state": 42,
        "silhouettes": silhouettes,
        "members_per_group": {int(k): int(v) for k, v in groups.value_counts().items()},
    }
    return members, centres, metadata


def prepare_models(frame: pd.DataFrame, *, force: bool = False) -> dict:
    """Run explicitly before serving; publish metadata after every table exists."""
    if not force and (existing := load_models()) is not None:
        return existing["metadata"]
    print("Estimando índice hedônico com IC de 95% agrupado por bairro…", flush=True)
    hedonic, hedonic_metadata = fit_hedonic(frame)
    print("Agrupando trajetórias de bairros (k=2…6; exibição k=4)…", flush=True)
    members, centres, cluster_metadata = cluster_trajectories(frame)
    atomic_parquet(hedonic, MODEL_DIR / "hedonic.parquet")
    atomic_parquet(members, MODEL_DIR / "members.parquet")
    atomic_parquet(centres, MODEL_DIR / "centres.parquet")
    metadata = {
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


def load_models(directory: Path | None = None) -> dict | None:
    """Read only tables for this exact source/model contract; never fit here."""
    directory = MODEL_DIR if directory is None else directory
    metadata_path = directory / "metadata.json"
    files = [directory / f"{name}.parquet" for name in ("hedonic", "members", "centres")]
    if not metadata_path.exists() or not all(path.exists() for path in files):
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if (
        metadata.get("revision") != REVISION
        or metadata.get("source_sha256") != SOURCE_SHA256
        or metadata.get("model_version") != MODEL_VERSION
        or any(
            metadata.get("tables_sha256", {}).get(path.stem) != file_sha256(path)
            for path in files
        )
    ):
        return None
    return {"metadata": metadata} | {
        path.stem: pd.read_parquet(path, use_threads=False) for path in files
    }
