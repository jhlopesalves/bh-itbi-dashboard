"""Feasibility, fitted label counts and silhouette metadata for trajectory models."""

import json
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from numpy.typing import NDArray
from sklearn import metrics
from sklearn.cluster import KMeans
from threadpoolctl import threadpool_limits

from bh_itbi import models
from bh_itbi.app import create_app
from bh_itbi.cluster import ClusteringError, cluster_trajectories
from bh_itbi.config import CLUSTER_K, CLUSTER_YEAR_MINIMUM, START_YEAR, YEARS


def _transactions(growth_rates: Sequence[int]) -> pd.DataFrame:
    """Vary price levels independently of the normalised trajectory."""
    return pd.DataFrame(
        [
            (
                f"B{neighbourhood}",
                year,
                "apartment",
                100.0,
                float((1000 + growth * (year - START_YEAR)) * 2**neighbourhood),
            )
            for neighbourhood, growth in enumerate(growth_rates)
            for year in YEARS
            for _ in range(CLUSTER_YEAR_MINIMUM)
        ],
        columns=[
            "neighbourhood",
            "year",
            "property_type",
            "built_area_m2",
            "price_per_m2_brl_real",
        ],
    )


@pytest.mark.parametrize(
    ("growth_rates", "distinct"),
    [
        pytest.param((), 0, id="no-eligible-neighbourhoods"),
        pytest.param((1,), 1, id="one-eligible-neighbourhood"),
        pytest.param((1,) * 7, 1, id="identical-normalised-profiles"),
        pytest.param((1, 2, 3, 1, 2, 3, 1), 3, id="fewer-than-four-distinct-profiles"),
    ],
)
def test_rejects_infeasible_configured_count_before_fitting(
    monkeypatch: pytest.MonkeyPatch, growth_rates: tuple[int, ...], distinct: int
) -> None:
    fit = Mock(side_effect=AssertionError("An infeasible configuration reached K-means"))
    monkeypatch.setattr(KMeans, "fit", fit)

    with pytest.raises(
        ClusteringError,
        match=(
            rf"Cannot fit 4 trajectory clusters with {len(growth_rates)} "
            rf"eligible neighbourhoods and {distinct} distinct normalised trajectories\."
        ),
    ):
        cluster_trajectories(_transactions(growth_rates))
    fit.assert_not_called()


def test_rejects_non_finite_normalised_values_before_fitting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fit = Mock(side_effect=AssertionError("Non-finite trajectories reached K-means"))
    monkeypatch.setattr(KMeans, "fit", fit)
    frame = _transactions((1, 2, 3, 4))
    base_year = frame["neighbourhood"].eq("B0") & frame["year"].eq(START_YEAR)
    frame.loc[base_year, "price_per_m2_brl_real"] = 0.0

    with pytest.raises(ClusteringError, match="requires finite normalised values"):
        cluster_trajectories(frame)
    fit.assert_not_called()


@pytest.mark.parametrize(
    ("growth_rates", "feasible"),
    [
        pytest.param((0, 0, 1, 1, 2, 2, 3), (2, 3, 4), id="distinctness-limit"),
        pytest.param((0, 1, 2, 3, 4, 5), (2, 3, 4, 5), id="silhouette-observation-limit"),
    ],
)
def test_skips_infeasible_candidate_fits_and_retains_all_observations(
    monkeypatch: pytest.MonkeyPatch, growth_rates: tuple[int, ...], feasible: tuple[int, ...]
) -> None:
    fitted: list[tuple[int, int]] = []
    original_fit = KMeans.fit

    def record_fit(estimator: KMeans, trajectories: pd.DataFrame) -> KMeans:
        fitted.append((estimator.n_clusters, len(trajectories)))
        return original_fit(estimator, trajectories)

    monkeypatch.setattr(KMeans, "fit", record_fit)
    with threadpool_limits(limits=1):
        members, _, metadata = cluster_trajectories(_transactions(growth_rates))

    assert sorted(fitted) == [(k, len(growth_rates)) for k in feasible]
    assert (
        members["neighbourhood"].nunique() == metadata["n_neighbourhoods"] == len(growth_rates)
    )
    assert metadata["k"] == CLUSTER_K
    scores = metadata["silhouettes"]
    assert list(scores) == ["2", "3", "4", "5", "6"]
    assert {int(k) for k, score in scores.items() if score is not None} == set(feasible)


def test_rejects_collapsed_configured_fit_before_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def collapsed_fit(estimator: KMeans, trajectories: pd.DataFrame) -> KMeans:
        assert estimator.n_clusters == CLUSTER_K
        estimator.labels_ = np.arange(len(trajectories), dtype=np.int32) % (CLUSTER_K - 1)
        return estimator

    score = Mock(
        side_effect=AssertionError("A collapsed required fit reached silhouette scoring")
    )
    monkeypatch.setattr(KMeans, "fit", collapsed_fit)
    monkeypatch.setattr(metrics, "silhouette_score", score)

    with pytest.raises(ClusteringError, match="produced 3 distinct labels for 4 requested"):
        cluster_trajectories(_transactions((0, 1, 10, 11, 20, 21, 30, 31)))
    score.assert_not_called()


@pytest.mark.parametrize("last_label_count", [1, 2, 6])
def test_scores_only_requested_label_counts_and_keeps_the_selected_fit(
    monkeypatch: pytest.MonkeyPatch, last_label_count: int
) -> None:
    original_fit = KMeans.fit
    original_score = metrics.silhouette_score
    labels_by_candidate: dict[int, NDArray[np.int32]] = {}
    evaluated: dict[str, float] = {}

    def fit_candidate(estimator: KMeans, trajectories: pd.DataFrame) -> KMeans:
        result = original_fit(estimator, trajectories)
        labels = result.labels_
        assert labels is not None
        if result.n_clusters == 6 and last_label_count < 6:
            labels = labels % last_label_count
            result.labels_ = labels
        labels_by_candidate[result.n_clusters] = labels
        return result

    def record_score(trajectories: pd.DataFrame, labels: NDArray[np.int32]) -> float:
        k = next(
            k for k, fitted_labels in labels_by_candidate.items() if fitted_labels is labels
        )
        assert np.unique(labels).size == k
        score = float(original_score(trajectories, labels))
        evaluated[str(k)] = score
        return score

    monkeypatch.setattr(KMeans, "fit", fit_candidate)
    monkeypatch.setattr(metrics, "silhouette_score", record_score)
    with threadpool_limits(limits=1):
        members, centres, metadata = cluster_trajectories(
            _transactions((0, 1, 10, 11, 20, 21, 30, 31))
        )

    assert set(labels_by_candidate) == {2, 3, 4, 5, 6}
    assert set(evaluated) == (
        {"2", "3", "4", "5", "6"} if last_label_count == 6 else {"2", "3", "4", "5"}
    )
    assert metadata["silhouettes"] == {str(k): evaluated.get(str(k)) for k in range(2, 7)}
    assert metadata["members_per_group"] == {"1": 2, "2": 2, "3": 2, "4": 2}
    assert members.groupby("neighbourhood")["group"].first().tolist() == [
        4,
        4,
        3,
        3,
        2,
        2,
        1,
        1,
    ]
    terminal = centres.loc[centres["year"].eq(YEARS[-1]), "index"]
    np.testing.assert_allclose(terminal, [127.45, 118.45, 109.45, 100.45])


def test_prepares_and_displays_a_four_group_fit_with_undefined_silhouette(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, snapshot_frame: pd.DataFrame
) -> None:
    neighbourhoods = ["SAVASSI", "LOURDES", "BURITIS", "CASTELO"]
    frame = snapshot_frame.loc[snapshot_frame["neighbourhood"].isin(neighbourhoods)]
    monkeypatch.setattr(models, "MODEL_DIR", tmp_path)

    with threadpool_limits(limits=1):
        metadata = models.prepare_models(frame, force=True)

    clusters = metadata["clusters"]
    assert clusters["n_neighbourhoods"] == clusters["k"] == CLUSTER_K
    assert clusters["members_per_group"] == {"1": 1, "2": 1, "3": 1, "4": 1}
    assert clusters["silhouettes"]["2"] is not None
    assert clusters["silhouettes"]["3"] is not None
    assert all(clusters["silhouettes"][key] is None for key in ("4", "5", "6"))
    prepared = models.load_models()
    assert prepared is not None
    assert prepared.metadata == metadata

    app = create_app(frame=frame, models=prepared)
    response = app.server.test_client().get("/_dash-layout")
    assert response.status_code == 200
    assert "A silhueta é indefinida com um bairro por grupo." in json.dumps(
        response.get_json(), ensure_ascii=False
    )
