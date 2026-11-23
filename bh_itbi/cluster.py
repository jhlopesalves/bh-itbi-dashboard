"""Fit and order neighbourhood k-means trajectory groups on fixed annual data."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

import numpy as np
import pandas as pd
from numpy.typing import NDArray

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


def _trajectory_apartments(frame: pd.DataFrame) -> pd.DataFrame:
    """Select the apartment rows used to form annual trajectories."""
    data = positive_area_rows(frame)
    return data.loc[
        data["property_type"].eq("apartment")
        & data["year"].between(START_YEAR, END_YEAR)
        & data["price_per_m2_brl_real"].notna()
    ]


def _annual_trajectories(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Index the complete neighbourhood series and retain annual sample counts."""
    yearly = (
        _trajectory_apartments(frame)
        .groupby(["neighbourhood", "year"], observed=True)
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


class _TrajectoryMembership(TypedDict):
    neighbourhood: str
    group: int


class _TrajectorySpread(TypedDict):
    neighbourhood: str
    endpoint_se: float


class _TrajectoryBootstrap(TypedDict):
    draws: int
    ari_median: float
    ari_p10: float
    ari_p90: float
    endpoint_se_median: float
    endpoint_se_p90: float
    neighbourhoods: list[_TrajectorySpread]


class _TrajectoryRepresentation(TypedDict):
    representation: str
    ari: float
    silhouette: float | None


class _CompositionRow(_TrajectoryMembership):
    all_apartments: float
    excluding_new: float | None
    all_n_start: int
    all_n_end: int
    excluding_new_n_start: int
    excluding_new_n_end: int
    all_small_cell: bool
    excluding_new_small_cell: bool


class _GroupComposition(TypedDict):
    group: int
    median_all_apartments: float
    median_excluding_new: float | None


class TrajectoryStability(TypedDict):
    """Sampling and representation dependence of the published partition."""

    published_members: list[_TrajectoryMembership]
    published_sizes: dict[str, int]
    published_silhouettes: dict[str, float | None]
    bootstrap: _TrajectoryBootstrap
    representations: list[_TrajectoryRepresentation]
    composition: list[_CompositionRow]
    group_composition: list[_GroupComposition]


def _bootstrap_apartment_medians(
    cells: dict[tuple[str, int], NDArray[np.float64]],
    names: list[str],
    rng: np.random.Generator,
    draws: int,
) -> NDArray[np.float64]:
    samples = np.empty((draws, len(names), len(YEARS)))
    for j, name in enumerate(names):
        for t, year in enumerate(YEARS):
            values = cells[(name, year)]
            medians = np.median(rng.choice(values, size=(draws, values.size)), axis=1)
            samples[:, j, t] = medians
    return INDEX_BASE * (samples / samples[:, :, :1])


def _stability_bootstrap(
    draws: NDArray[np.float64], names: list[str], groups: NDArray[np.intp]
) -> _TrajectoryBootstrap:
    from sklearn.metrics import adjusted_rand_score  # noqa: PLC0415

    aris: list[float] = []
    for sample in draws:
        fit = _fit_kmeans(pd.DataFrame(sample, index=names, columns=list(YEARS)), CLUSTER_K)
        assert fit.labels_ is not None
        aris.append(float(adjusted_rand_score(groups, fit.labels_)))
    lower, upper = np.quantile(aris, [0.1, 0.9])
    endpoint_se = draws[:, :, -1].std(axis=0)
    return {
        "draws": len(draws),
        "ari_median": float(np.median(aris)),
        "ari_p10": float(lower),
        "ari_p90": float(upper),
        "endpoint_se_median": float(np.median(endpoint_se)),
        "endpoint_se_p90": float(np.quantile(endpoint_se, 0.9)),
        "neighbourhoods": [
            {"neighbourhood": name, "endpoint_se": float(se)}
            for name, se in zip(names, endpoint_se, strict=True)
        ],
    }


def _stability_representations(
    medians: pd.DataFrame, groups: NDArray[np.intp]
) -> list[_TrajectoryRepresentation]:
    from sklearn.metrics import adjusted_rand_score, silhouette_score  # noqa: PLC0415

    log = pd.DataFrame(
        np.log(medians.to_numpy(dtype=float)), index=medians.index, columns=medians.columns
    )
    alternatives = {
        "mean_2016_2017": INDEX_BASE * medians.div(medians.iloc[:, :2].mean(axis=1), axis=0),
        "series_mean": INDEX_BASE * medians.div(medians.mean(axis=1), axis=0),
        "log_centred": log.sub(log.mean(axis=1), axis=0),
    }
    results: list[_TrajectoryRepresentation] = []
    for name, matrix in alternatives.items():
        labels = _fit_kmeans(matrix, CLUSTER_K).labels_
        assert labels is not None
        distinct = np.unique(labels).size
        silhouette = (
            float(silhouette_score(matrix, labels)) if 1 < distinct < len(matrix) else None
        )
        results.append(
            {
                "representation": name,
                "ari": float(adjusted_rand_score(groups, labels)),
                "silhouette": silhouette,
            }
        )
    return results


def _endpoint_composition(rows: pd.DataFrame) -> tuple[float | None, int, int]:
    by_year = rows.groupby("year")["price_per_m2_brl_real"].agg(["median", "size"])
    by_year = by_year.reindex([START_YEAR, END_YEAR])
    n_start, n_end = by_year["size"].fillna(0).astype(int).tolist()
    if not n_start or not n_end:
        return None, n_start, n_end
    start, end = by_year["median"].tolist()
    return float(INDEX_BASE * end / start), n_start, n_end


def _trajectory_composition(
    apartments: pd.DataFrame, members: list[_TrajectoryMembership]
) -> tuple[list[_CompositionRow], list[_GroupComposition]]:
    results: list[_CompositionRow] = []
    for member in members:
        rows = apartments.loc[apartments["neighbourhood"].eq(member["neighbourhood"])]
        all_ages, n_start, n_end = _endpoint_composition(rows)
        older, older_start, older_end = _endpoint_composition(
            rows.loc[rows["building_age_band"].ne("new")]
        )
        assert all_ages is not None
        results.append(
            {
                **member,
                "all_apartments": all_ages,
                "excluding_new": older,
                "all_n_start": n_start,
                "all_n_end": n_end,
                "excluding_new_n_start": older_start,
                "excluding_new_n_end": older_end,
                "all_small_cell": min(n_start, n_end) < CLUSTER_YEAR_MINIMUM,
                "excluding_new_small_cell": min(older_start, older_end) < CLUSTER_YEAR_MINIMUM,
            }
        )
    summaries: list[_GroupComposition] = []
    for group in sorted({row["group"] for row in results}):
        selected = [row for row in results if row["group"] == group]
        older_values = [
            value for row in selected if (value := row["excluding_new"]) is not None
        ]
        summaries.append(
            {
                "group": group,
                "median_all_apartments": float(
                    np.median([row["all_apartments"] for row in selected])
                ),
                "median_excluding_new": float(np.median(older_values))
                if older_values
                else None,
            }
        )
    return results, summaries


def trajectory_stability(
    frame: pd.DataFrame,
    members: pd.DataFrame,
    metadata: ClusterMetadata,
    *,
    rng: np.random.Generator,
    draws: int,
) -> TrajectoryStability:
    """Measure stability against the persisted labels without changing their fit."""
    if draws < 1:
        raise ClusteringError("Trajectory stability requires at least one bootstrap draw.")
    published = members.pivot(
        index="neighbourhood", columns="year", values="index"
    ).sort_index()
    names = list(published.index.astype(str))
    groups = np.asarray(
        members.drop_duplicates("neighbourhood")
        .set_index("neighbourhood")["group"]
        .reindex(names),
        dtype=np.intp,
    )
    apartments = _trajectory_apartments(frame)
    apartments = apartments.loc[apartments["neighbourhood"].isin(names)]
    cells = {
        (str(name), int(str(year))): rows["price_per_m2_brl_real"].to_numpy(dtype=float)
        for (name, year), rows in apartments.groupby(["neighbourhood", "year"], observed=True)
    }
    medians = pd.DataFrame(
        {year: [np.median(cells[(name, year)]) for name in names] for year in YEARS},
        index=names,
    )
    rebuilt = INDEX_BASE * medians.div(medians[START_YEAR], axis=0)
    if not np.array_equal(rebuilt.to_numpy(), published.to_numpy()):
        raise ClusteringError(
            "Annual apartment medians do not reproduce the published trajectories."
        )
    membership: list[_TrajectoryMembership] = [
        {"neighbourhood": name, "group": int(group)}
        for name, group in zip(names, groups, strict=True)
    ]
    composition, group_composition = _trajectory_composition(apartments, membership)
    return {
        "published_members": membership,
        "published_sizes": metadata["members_per_group"],
        "published_silhouettes": metadata["silhouettes"],
        "bootstrap": _stability_bootstrap(
            _bootstrap_apartment_medians(cells, names, rng, draws), names, groups
        ),
        "representations": _stability_representations(medians, groups),
        "composition": composition,
        "group_composition": group_composition,
    }
