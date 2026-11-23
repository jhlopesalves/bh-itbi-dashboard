"""Check pattern recovery, centring, label alignment and the pinned complete-case fit."""

import os

import numpy as np
import pandas as pd
import pytest

from bh_itbi import patterns
from bh_itbi.config import PATTERN_K, PATTERN_ORDER, PATTERN_PERIODS, START_YEAR
from bh_itbi.data import load_transactions

BORDERLINE_NEIGHBOURHOODS = {
    "COPACABANA",
    "GUARANI",
    "MANACAS",
    "SANTA AMELIA",
    "SANTA MONICA",
}


def test_planted_patterns_and_firm_threshold(monkeypatch):
    planted = {
        "falling": [0.12, 0.01, -0.03, -0.06, -0.04],
        "stable": [0.0, -0.01, 0.0, -0.01, 0.02],
        "rising": [-0.04, -0.04, -0.04, -0.04, 0.16],
    }
    rows = pd.DataFrame(
        [
            {
                "neighbourhood": f"{pattern}-{j}",
                "year": START_YEAR + 2 * t,
                "property_type": "apartment",
                "built_area_m2": area,
                "price_per_m2_brl_real": np.exp(8 + j + change * (1 + 0.04 * j)),
                "building_age_band": band,
            }
            for pattern, shape in planted.items()
            for j in range(2)
            for t, change in enumerate(shape)
            for area, band in [(60.0, "old"), (110.0, "new")] * 30
        ]
    )
    shares = np.array([0.795, 0.8, 0.805, 1, 0.1, 0.81])
    stability = patterns.PatternStability(
        shares, np.zeros((PATTERN_K, len(PATTERN_PERIODS))), 0.8, 0.7, 0.9
    )
    monkeypatch.setattr(patterns, "_pattern_bootstrap", lambda *_: stability)

    members, centres, metadata = patterns.trajectory_patterns(rows)
    names = members.drop_duplicates("neighbourhood")
    assert names["pattern"].tolist() == names["neighbourhood"].str.split("-").str[0].tolist()
    assert names["firm"].tolist() == [False, True, True, True, False, True]
    assert centres["pattern"].drop_duplicates().tolist() == list(PATTERN_ORDER)
    assert set(members["n"]) == {60}
    assert metadata["n_neighbourhoods"] == 6


def test_pattern_centring_removes_neighbourhood_level():
    medians = np.array([[1.0, 1.1, 1.2, 1.3, 1.4], [1.6, 1.5, 1.4, 1.3, 1.2]])
    shifted = medians.copy()
    shifted[1] += 2.5
    np.testing.assert_allclose(
        patterns.centre_pattern_rows(shifted), patterns.centre_pattern_rows(medians), atol=1e-14
    )


def test_pattern_alignment_inverts_permuted_labels():
    full = np.array([[0.12, 0.02, -0.04], [0.0, 0.0, 0.0], [-0.1, 0.02, 0.17]])
    draw = full[[2, 0, 1]] + 0.01
    permutation = patterns.align_pattern_labels(full, draw)
    assert permutation == (1, 2, 0)
    np.testing.assert_array_equal(np.argsort(permutation)[[1, 2, 0, 1]], [0, 1, 2, 0])


def assert_pinned_patterns(metadata, members, centres):
    """Check the complete-case partition approved after increasing the restart count."""
    assert metadata["n_neighbourhoods"] == 103
    assert metadata["n_init"] == 200
    assert metadata["age_reference"] == "11_25"
    assert metadata["inertia"] <= 0.647652
    summaries = [metadata["patterns"][key] for key in PATTERN_ORDER]
    assert [row["size"] for row in summaries] == [35, 51, 17]
    np.testing.assert_allclose(
        centres.pivot(index="pattern", columns="period", values="index")
        .reindex(index=PATTERN_ORDER, columns=PATTERN_PERIODS)
        .to_numpy(),
        [
            [108.539, 100.934, 97.219, 93.938, 99.949],
            [99.777, 98.640, 99.945, 97.891, 103.851],
            [97.849, 97.022, 94.346, 96.897, 115.222],
        ],
        atol=0.3,
        rtol=0,
    )
    scores = metadata["silhouettes"]
    assert [scores[str(k)] for k in range(2, 7)] == pytest.approx(
        [0.26650, 0.26559, 0.24531, 0.22776, 0.22745], abs=0.01, rel=0
    )
    assert [row["firm"] for row in summaries] == pytest.approx([29, 32, 11], abs=3, rel=0)
    assert metadata["ari_median"] == pytest.approx(0.60075, abs=0.07, rel=0)
    assert [row["max_centre_se"] for row in summaries[:2]] == pytest.approx(
        [0.99477, 0.88150], abs=0.4, rel=0
    )
    rising_se = summaries[2]["max_centre_se"]
    assert np.isfinite(rising_se)
    assert 1.0 <= rising_se <= 5.0
    membership = members.drop_duplicates("neighbourhood").set_index("neighbourhood")
    borderline = membership.loc[sorted(BORDERLINE_NEIGHBOURHOODS)]
    assert borderline["membership_share"].lt(0.80).all()
    assert not borderline["firm"].any()


@pytest.mark.skipif(
    os.environ.get("BH_ITBI_REAL_DATA") != "1", reason="Requires the pinned transaction cache"
)
def test_real_trajectory_patterns():
    members, centres, metadata = patterns.trajectory_patterns(
        load_transactions(allow_prepare=False)
    )
    assert_pinned_patterns(metadata, members, centres)
