"""Check pattern recovery, centring, label alignment and the pinned complete-case fit."""

import os
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from bh_itbi import patterns
from bh_itbi.config import PATTERN_K, PATTERN_ORDER, PATTERN_PERIODS, START_YEAR
from bh_itbi.data import load_transactions
from bh_itbi.text.models import patterns_footnote

BORDERLINE_NEIGHBOURHOODS = {
    "COPACABANA",
    "GUARANI",
    "MANACAS",
    "SANTA AMELIA",
    "SANTA MONICA",
}


@pytest.fixture
def planted_patterns(monkeypatch):
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
        shares=shares,
        centre_ranges=np.broadcast_to(
            np.array([95.0, 110.0])[:, None, None], (2, PATTERN_K, len(PATTERN_PERIODS))
        ),
        ari_median=0.8,
        ari_p10=0.7,
        ari_p90=0.9,
        separation_share=0.8,
        rising_size=[1.0, 2.0],
    )
    monkeypatch.setattr(patterns, "_pattern_bootstrap", lambda *_: stability)
    return patterns.trajectory_patterns(rows)


def test_planted_patterns_and_firm_threshold(planted_patterns):
    members, centres, metadata = planted_patterns
    names = members.drop_duplicates("neighbourhood")
    assert names["pattern"].tolist() == names["neighbourhood"].str.split("-").str[0].tolist()
    assert names["firm"].tolist() == [False, True, True, True, False, True]
    assert centres["pattern"].drop_duplicates().tolist() == list(PATTERN_ORDER)
    assert set(members["n"]) == {60}
    assert metadata["n_neighbourhoods"] == 6


def test_centres_store_ordered_ranges_without_standard_errors(planted_patterns):
    _, centres, metadata = planted_patterns
    assert centres.columns.tolist() == ["pattern", "period", "index", "p10", "p90"]
    assert centres["p10"].le(centres["p90"]).all()
    for name in PATTERN_ORDER:
        rows = centres.loc[centres["pattern"].eq(name)]
        for quantile in ("p10", "p90"):
            assert rows[quantile].tolist() == metadata["patterns"][name][quantile]


def test_separation_share_treats_a_singleton_naming_failure_as_unidentified(monkeypatch):
    centres = np.array(
        [
            [0.12, 0.07, 0.0, -0.07, -0.12],
            [-0.01, 0.02, 0.0, -0.02, 0.01],
            [-0.12, -0.07, 0.0, 0.07, 0.12],
        ]
    )
    reference = SimpleNamespace(cluster_centers_=centres, labels_=np.array([0, 0, 1, 1, 2, 2]))
    singleton_centres = centres.copy()
    singleton_centres[1] = [0.21, -0.14, -0.14, -0.14, 0.21]
    singleton = SimpleNamespace(
        cluster_centers_=singleton_centres, labels_=np.array([0, 0, 1, 2, 2, 2])
    )
    with pytest.raises(patterns.ClusteringError):
        patterns.named_pattern_order(singleton_centres)
    fits = iter((reference, singleton))
    monkeypatch.setattr(patterns, "PATTERN_DRAWS", 2)
    monkeypatch.setattr(patterns, "fit_pattern_kmeans", lambda _: next(fits))
    matrix = np.zeros((len(reference.labels_), len(PATTERN_PERIODS)))
    sample = patterns.PatternSample(
        [pd.DataFrame()] * matrix.size, pd.DataFrame(), matrix, {}, "old"
    )
    stability = patterns._pattern_bootstrap(
        sample,
        reference,
        patterns.named_pattern_order(centres),
        lambda _cell, _rng, draws: np.zeros(draws),
    )
    assert stability.separation_share == 0.5
    assert np.less_equal(*stability.centre_ranges).all()


def test_patterns_footnote_matches_the_reference_block_face_copy():
    actual = patterns_footnote(
        (200, 0.80), 0.93, ([107.2, 111.4], [109.4, 118.3]), 0.321, 69 / 103
    )
    assert actual == (
        "Agrupamento por k-médias em três padrões, aplicado à forma das trajetórias (cada "
        "bairro centrado na própria média). Linha forte: centro do padrão; linhas finas: "
        "bairros que ficam no mesmo padrão em pelo menos 80% de 200 reamostragens; "
        "tracejado cinza: bairros de fronteira. Cada reamostragem sorteia faces de quadra "
        "inteiras, porque vendas do mesmo prédio ou quarteirão não são independentes. Os "
        "três padrões reaparecem em 9 de cada 10 reamostragens. Em 8 de cada 10, o "
        "primeiro biênio da queda fica entre 107 e 111, e o último biênio da alta "
        "recente, entre 109 e 118; os bairros que compõem a alta recente, porém, variam. "
        "Cerca de dois terços dos bairros ficam entre padrões (concordância mediana entre "
        "reamostragens: 0,32). O ajuste considera apenas área e faixa de idade; outras "
        "diferenças de composição permanecem. A classificação anterior, em quatro grupos "
        "e sem ajuste, foi substituída após a auditoria de robustez."
    )
    assert "erro-padrão" not in actual and "EP" not in actual


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
    assert metadata["resampling"] == "block_face"
    assert [row["firm"] for row in summaries] == pytest.approx([19, 10, 5], abs=3, rel=0)
    assert metadata["ari_median"] == pytest.approx(0.321, abs=0.07, rel=0)
    assert metadata["separation_share"] == pytest.approx(0.93, abs=0.05, rel=0)
    assert metadata["falling_first"] == pytest.approx([107.2, 111.4], abs=1.5, rel=0)
    assert metadata["rising_last"] == pytest.approx([109.4, 118.3], abs=2.5, rel=0)
    assert [round(size) for size in metadata["rising_size"]] == [9, 39]
    assert centres["p10"].le(centres["p90"]).all()
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
