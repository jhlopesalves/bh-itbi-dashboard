"""Fit and order neighbourhood k-means trajectory groups on fixed annual data."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

import numpy as np
import pandas as pd

from bh_itbi.config import (
    CLUSTER_K,
    CLUSTER_K_RANGE,
    CLUSTER_N_INIT,
    CLUSTER_RANDOM_STATE,
    CLUSTER_YEAR_MINIMUM,
    END_YEAR,
    INDEX_BASE,
    START_YEAR,
    YEARS,
)
from bh_itbi.filters import positive_area_rows

if TYPE_CHECKING:
    from sklearn.cluster import KMeans


class ClusteringError(ValueError):
    """The trajectory data or fit cannot support the configured cluster count."""


class ClusterMetadata(TypedDict):
    """Hyperparameters, silhouette scores and group sizes for trajectory clustering."""

    n_neighbourhoods: int
    k: int
    n_init: int
    random_state: int
    silhouettes: dict[str, float | None]
    members_per_group: dict[str, int]


def _annual_trajectories(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Index the complete neighbourhood series and retain annual sample counts."""
    data = positive_area_rows(frame)
    data = data.loc[
        data["property_type"].eq("apartment")
        & data["year"].between(START_YEAR, END_YEAR)
        & data["price_per_m2_brl_real"].notna()
    ]
    yearly = (
        data.groupby(["neighbourhood", "year"], observed=True)
        .agg(median=("price_per_m2_brl_real", "median"), n=("price_per_m2_brl_real", "size"))
        .reset_index()
    )
    yearly = yearly.loc[yearly["n"] >= CLUSTER_YEAR_MINIMUM]
    trajectories = yearly.pivot(index="neighbourhood", columns="year", values="median")
    trajectories = trajectories.reindex(columns=YEARS).dropna()
    trajectories = INDEX_BASE * trajectories.div(trajectories[START_YEAR], axis=0)
    return trajectories, yearly


def _fit_kmeans(trajectories: pd.DataFrame, k: int) -> KMeans:
    """Fit every candidate with the same configured initialisation."""
    # Keep the build-only scikit-learn stack out of the serving process.
    from sklearn.cluster import KMeans  # noqa: PLC0415

    return KMeans(
        n_clusters=k,
        # Scikit-learn accepts integer restarts; its hint only includes strings.
        n_init=CLUSTER_N_INIT,  # pyright: ignore[reportArgumentType]
        random_state=CLUSTER_RANDOM_STATE,
    ).fit(trajectories)


def _fit_clusters(
    trajectories: pd.DataFrame,
) -> tuple[KMeans, dict[str, float | None]]:
    """Fit the required partition and report available candidate silhouettes."""
    from sklearn.metrics import silhouette_score  # noqa: PLC0415

    if not np.isfinite(trajectories.to_numpy(dtype=float)).all():
        raise ClusteringError("Trajectory clustering requires finite normalised values.")
    n_neighbourhoods = len(trajectories)
    # Count distinct rows for feasibility while retaining all neighbourhoods in the fit.
    n_distinct = len(trajectories.drop_duplicates())
    if n_distinct < CLUSTER_K:
        raise ClusteringError(
            f"Cannot fit {CLUSTER_K} trajectory clusters with {n_neighbourhoods} "
            f"eligible neighbourhoods and {n_distinct} distinct normalised trajectories."
        )

    fit = _fit_kmeans(trajectories, CLUSTER_K)
    fitted_labels = fit.labels_
    n_labels = 0 if fitted_labels is None else np.unique(fitted_labels).size
    if n_labels != CLUSTER_K:
        raise ClusteringError(
            f"The trajectory fit produced {n_labels} distinct labels for "
            f"{CLUSTER_K} requested clusters."
        )

    silhouettes: dict[str, float | None] = {str(k): None for k in CLUSTER_K_RANGE}
    for k in CLUSTER_K_RANGE:
        # A silhouette for k requires k nonempty groups and at least one non-singleton.
        if k > n_distinct or not 1 < k < n_neighbourhoods:
            continue
        candidate = fit if k == CLUSTER_K else _fit_kmeans(trajectories, k)
        candidate_labels = candidate.labels_
        if candidate_labels is not None and np.unique(candidate_labels).size == k:
            silhouettes[str(k)] = float(silhouette_score(trajectories, candidate_labels))
    return fit, silhouettes


def cluster_trajectories(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, ClusterMetadata]:
    """Fit the fixed k=4 on complete annual trajectories and report candidate scores.

    Raise ClusteringError if four nonempty groups cannot be fitted. Unavailable
    silhouette scores are None, including for a valid fit with four singleton groups.
    """
    trajectories, yearly = _annual_trajectories(frame)
    fit, silhouettes = _fit_clusters(trajectories)
    labels = fit.labels_
    assert labels is not None
    order = np.argsort(-fit.cluster_centers_[:, -1])
    display_group = {cluster: rank for rank, cluster in enumerate(order, start=1)}
    groups = pd.Series(
        [display_group[label] for label in labels], index=trajectories.index, name="group"
    )
    members = (
        trajectories.rename_axis("neighbourhood")
        .reset_index()
        .melt(id_vars="neighbourhood", var_name="year", value_name="index")
    )
    members["group"] = members["neighbourhood"].map(groups)
    members = members.merge(yearly[["neighbourhood", "year", "n"]], validate="one_to_one")
    centres = pd.DataFrame(fit.cluster_centers_[order], columns=trajectories.columns)
    centres["group"] = range(1, CLUSTER_K + 1)
    centres = centres.melt(id_vars="group", var_name="year", value_name="index")
    metadata: ClusterMetadata = {
        "n_neighbourhoods": len(trajectories),
        "k": CLUSTER_K,
        "n_init": CLUSTER_N_INIT,
        "random_state": CLUSTER_RANDOM_STATE,
        "silhouettes": silhouettes,
        "members_per_group": {
            str(group): int(count) for group, count in groups.value_counts().items()
        },
    }
    return members, centres, metadata
