"""Fit and order neighbourhood k-means trajectory groups on fixed annual data."""

from typing import TypedDict

import numpy as np
import pandas as pd

from bh_itbi.config import (
    CLUSTER_K,
    CLUSTER_K_RANGE,
    CLUSTER_MIN_NEIGHBOURHOODS,
    CLUSTER_N_INIT,
    CLUSTER_RANDOM_STATE,
    CLUSTER_YEAR_MINIMUM,
    END_YEAR,
    INDEX_BASE,
    START_YEAR,
    YEARS,
)
from bh_itbi.filters import positive_area_rows


class ClusterMetadata(TypedDict):
    """Hyperparameters, silhouette scores and group sizes for trajectory clustering."""

    n_neighbourhoods: int
    k: int
    n_init: int
    random_state: int
    silhouettes: dict[str, float]
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


def cluster_trajectories(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, ClusterMetadata]:
    """Fixed k=4 on all ten annual real-median indices, with seed 42/n_init 20."""
    # Keep the build-only scikit-learn stack out of the serving process.
    from sklearn.cluster import KMeans  # noqa: PLC0415
    from sklearn.metrics import silhouette_score  # noqa: PLC0415

    trajectories, yearly = _annual_trajectories(frame)
    if len(trajectories) < CLUSTER_MIN_NEIGHBOURHOODS:
        raise ValueError(
            f"Fewer than {CLUSTER_MIN_NEIGHBOURHOODS} neighbourhoods have enough annual "
            f"coverage to evaluate k={CLUSTER_K_RANGE[0]}–{CLUSTER_K_RANGE[-1]}."
        )
    fits = {
        k: KMeans(
            n_clusters=k,
            # Scikit-learn accepts integer restarts; its hint only includes strings.
            n_init=CLUSTER_N_INIT,  # pyright: ignore[reportArgumentType]
            random_state=CLUSTER_RANDOM_STATE,
        ).fit(trajectories)
        for k in CLUSTER_K_RANGE
    }
    silhouettes = {
        str(k): float(silhouette_score(trajectories, fit.labels_)) for k, fit in fits.items()
    }
    fit = fits[CLUSTER_K]
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
