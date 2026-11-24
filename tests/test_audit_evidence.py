"""Regress the pinned audit against the external reference and regenerate it on demand."""

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pandas.api.types import is_numeric_dtype
from test_patterns import BORDERLINE_NEIGHBOURHOODS, assert_pinned_patterns

from bh_itbi.audit import AuditSettings, run_audit
from bh_itbi.config import (
    IDENTITY_TOLERANCE,
    MODEL_VERSION,
    PATTERN_ORDER,
    REVISION,
    ROOT,
    SOURCE_SHA256,
)
from bh_itbi.data import file_sha256
from bh_itbi.patterns import pattern_settings
from bh_itbi.robust import FIXED_POINT_TOLERANCE, SCORE_TOLERANCE
from bh_itbi.sensitivity import PROTOCOL, QUARTERS

COMMITTED = ROOT / "docs" / "robustness"
REFERENCE_SPECIFICATIONS = {
    "baseline": {
        "n": (202_204, 0),
        "r_squared": (0.237, 0.0005),
        "residual_sd": (0.437, 0.0005),
        "index_2016Q3": (88.3, 0.05),
        "index_2025Q4": (110.0, 0.05),
        "lag1_autocorr_changes": (-0.31, 0.005),
    },
    "price_floor_1000": {
        "n": (197_618, 0),
        "residual_sd": (0.329, 0.0005),
        "index_2016Q3": (93.7, 0.05),
        "index_2025Q4": (106.6, 0.05),
    },
    "price_ceiling_30000": {"n": (202_184, 0), "index_2025Q4": (110.1, 0.05)},
    "area_20_1000": {
        "n": (201_737, 0),
        "index_2016Q3": (90.7, 0.05),
        "index_2025Q4": (109.9, 0.05),
    },
    "combined_reference_v2": {
        "n": (197_280, 0),
        "residual_sd": (0.327, 0.0005),
        "index_2016Q3": (93.9, 0.05),
        "index_2025Q4": (106.6, 0.05),
    },
    "huber_global": {
        "index_2016Q3": (94.7, 0.05),
        "index_2025Q4": (105.0, 0.05),
        "share_downweighted": (0.239, 0.001),
    },
}


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def evidence_dir() -> Path:
    path = Path(os.environ.get("BH_ITBI_AUDIT_DIR", COMMITTED))
    if not path.exists():
        pytest.skip("Pinned audit evidence has not been generated.")
    return path


@pytest.fixture(scope="module")
def diagnostics(evidence_dir):
    return _load_json(evidence_dir / "diagnostics.json")


@pytest.fixture(scope="module")
def specifications(evidence_dir):
    return pd.read_csv(evidence_dir / "specifications.csv").set_index("spec_id")


def test_manifest_matches_the_pinned_default_protocol(evidence_dir) -> None:
    manifest = _load_json(evidence_dir / "manifest.json")
    assert manifest["revision"] == REVISION == "5908d77ed56fc9adb6dbafaf2cb38f34245bcd76"
    assert manifest["source_sha256"] == SOURCE_SHA256
    assert SOURCE_SHA256 == "386a922d539e78538cd31dd21f7f3ed32db7505ecc70d16a683f69aadf7dbe86"
    assert manifest["cached_table_verified"] is True
    assert manifest["protocol_id"] == PROTOCOL.protocol_id
    assert manifest["protocol_sha256"] == PROTOCOL.sha256
    assert manifest["protocol_sha256"] == file_sha256(evidence_dir / "protocol.json")
    assert manifest["protocol_settings"] is True
    settings = AuditSettings()
    assert (manifest["seed"], manifest["cluster_draws"], manifest["median_draws"]) == (
        settings.seed,
        settings.cluster_draws,
        settings.median_draws,
    )
    assert manifest["model_version"] == MODEL_VERSION
    assert manifest["patterns_id"] == "trajectory-patterns-v1"
    assert manifest["pattern_settings"] == pattern_settings()


def test_reference_trajectory_patterns(evidence_dir) -> None:
    evidence = _load_json(evidence_dir / "trajectory_patterns.json")
    metadata = evidence["metadata"]
    members = pd.DataFrame(evidence["membership"])
    centres = pd.DataFrame(evidence["centres"])
    assert set(centres) == {"pattern", "period", "index", "p10", "p90"}
    assert_pinned_patterns(metadata, members, centres)
    assert len(members) == members["neighbourhood"].nunique() == metadata["n_neighbourhoods"]
    assert members["membership_share"].between(0, 1).all()
    assert members["firm"].eq(members["membership_share"].ge(metadata["firm_share"])).all()
    alternative = evidence["alternative"]
    assert alternative["sizes"] == {"falling": 34, "stable": 47, "rising": 22}
    assert alternative["inertia"] == pytest.approx(0.6478202965, abs=1e-8, rel=0)
    assert alternative["inertia"] > metadata["inertia"]
    assert set(alternative["stable_rising_switches"]) == BORDERLINE_NEIGHBOURHOODS
    assert alternative["other_switches"] == ["LUXEMBURGO"]


def test_independent_record_pattern_stability_structure(evidence_dir) -> None:
    evidence = _load_json(evidence_dir / "trajectory_patterns.json")
    independent = evidence["independent_records"]
    assert set(independent) == {"firm", "ari_p10", "ari_median", "ari_p90"}
    assert (
        -1 <= independent["ari_p10"] <= independent["ari_median"] <= independent["ari_p90"] <= 1
    )
    assert independent["firm"].keys() == set(PATTERN_ORDER)
    for name, count in independent["firm"].items():
        assert isinstance(count, int)
        assert 0 <= count <= evidence["metadata"]["patterns"][name]["size"]


def test_pattern_cells_with_fewest_block_faces(evidence_dir) -> None:
    cells = _load_json(evidence_dir / "trajectory_patterns.json")["fewest_block_faces"]
    assert len(cells) == 5
    assert [row["block_faces"] for row in cells] == [8, 9, 9, 10, 13]
    assert [(row["neighbourhood"], row["period"]) for row in cells[:3]] == [
        ("MANTIQUEIRA", "2016–2017"),
        ("SANTA HELENA", "2018–2019"),
        ("SANTA HELENA", "2016–2017"),
    ]
    assert cells[1]["records"] == 160
    assert cells[1]["largest_face_share"] == pytest.approx(83 / 160)


@pytest.mark.parametrize("spec_id", REFERENCE_SPECIFICATIONS)
def test_reference_specification_estimates(specifications, spec_id) -> None:
    actual = specifications.loc[spec_id]
    for metric, (reference, tolerance) in REFERENCE_SPECIFICATIONS[spec_id].items():
        assert actual[metric] == pytest.approx(reference, rel=0, abs=tolerance), metric


def test_reference_residual_dispersion_and_adjacent_quarter_noise(diagnostics) -> None:
    observed = pd.DataFrame(diagnostics["residual_dispersion"]).set_index("year")
    years = [2016, 2021, 2025]
    np.testing.assert_allclose(
        observed.loc[years, "all_records"], [0.285, 0.228, 0.251], rtol=0, atol=0.0005
    )
    np.testing.assert_allclose(
        observed.loc[years, "excluding_low_tail"], [0.265, 0.223, 0.244], rtol=0, atol=0.0005
    )
    adjacent = diagnostics["adjacent_quarter_noise"]
    assert adjacent["n_changes"] == 39
    assert adjacent["descriptive_ratio"] == pytest.approx(0.22, rel=0, abs=0.005)
    assert adjacent["lag1_autocorrelation"] == pytest.approx(-0.31, rel=0, abs=0.005)


def test_reference_global_huber_weights(evidence_dir) -> None:
    weights = pd.read_csv(evidence_dir / "huber_weights.csv")
    global_weights = weights.loc[weights["spec_id"].eq("huber_global")]
    by_year = (
        global_weights.assign(
            downweighted=global_weights["n"] * global_weights["share_downweighted"]
        )
        .groupby("year")[["n", "downweighted"]]
        .sum()
    )
    shares = by_year["downweighted"] / by_year["n"]
    np.testing.assert_allclose(shares.loc[[2016, 2021]], [0.298, 0.207], rtol=0, atol=0.001)
    assert global_weights["low_tail_share_of_total_deficit"].sum() == pytest.approx(
        0.20, rel=0, abs=0.005
    )


def test_reference_low_tail_profile_and_fraction_windows(diagnostics) -> None:
    assert diagnostics["tails"]["eligible_n"] == 205_436
    low_tail = next(
        row for row in diagnostics["low_tail_profile"] if row["price_group"] == "below_1000"
    )
    assert low_tail["n"] == 4_996
    assert low_tail["median_declared"] == 50_000
    assert low_tail["median_declared_base"] == pytest.approx(0.180, rel=0, abs=0.0005)
    assert low_tail["share_ratio_below_half"] == pytest.approx(0.946, rel=0, abs=0.0005)
    assert low_tail["share_houses"] == pytest.approx(0.400, rel=0, abs=0.0005)
    assert {
        row["fraction"]: (row["at_fraction"], row["mean_beside"])
        for row in diagnostics["fraction_test"]
    } == {
        "1/2": (9, 3.0),
        "1/3": (26, 23.5),
        "1/4": (63, 76.0),
        "1/5": (123, 109.5),
        "1/6": (134, 150.0),
        "1/8": (120, 108.0),
        "1/10": (100, 118.0),
    }


def test_reference_ratio_screen_reach_and_tax_base(diagnostics) -> None:
    reach = pd.DataFrame(diagnostics["ratio_screen_reach"]).set_index("year")
    np.testing.assert_allclose(
        reach.loc[[2016, 2024], "share_ratio_below_half"], [0.122, 0.033], rtol=0, atol=0.0005
    )
    assert reach.loc[2016, "share_flags_at_or_above_1000"] == pytest.approx(
        0.685, rel=0, abs=0.0005
    )
    base = diagnostics["tax_base"]
    assert base["declared_above_base"] == 4
    by_year = pd.DataFrame(base["annual"]).set_index("year")
    by_quarter = pd.DataFrame(base["quarterly"]).set_index("quarter")
    np.testing.assert_allclose(
        by_year.loc[[2016, 2025], "share_below"], [0.690, 0.421], rtol=0, atol=0.0005
    )
    np.testing.assert_allclose(
        by_quarter.loc[["2024Q1", "2025Q3"], "share_below"], [0.149, 0.472], rtol=0, atol=0.0005
    )


def test_reference_round_numbers(diagnostics) -> None:
    numbers = diagnostics["round_numbers"]
    assert numbers["n"] == 58_054
    assert numbers["exact_10000_share"] == pytest.approx(0.586, rel=0, abs=0.0005)
    assert numbers["exact_50000_share"] == pytest.approx(0.222, rel=0, abs=0.0005)
    assert numbers["ratio_to_one_fifth_share"] == pytest.approx(1.90, rel=0, abs=0.005)
    bins = pd.DataFrame(numbers["bin_widths"]).set_index("width_brl")
    np.testing.assert_allclose(
        bins.loc[[2500, 5000, 10000], "share"], [0.234, 0.253, 0.302], rtol=0, atol=0.0005
    )


def test_reference_trajectory_stability_and_composition(diagnostics) -> None:
    clusters = diagnostics["clustering"]
    assert clusters["published_sizes"] == {"1": 3, "2": 24, "3": 35, "4": 32}
    assert clusters["published_silhouettes"]["2"] == pytest.approx(0.35, rel=0, abs=0.005)
    assert clusters["published_silhouettes"]["4"] == pytest.approx(0.25, rel=0, abs=0.005)
    representations = {row["representation"]: row["ari"] for row in clusters["representations"]}
    for name, ari in (("mean_2016_2017", 0.39), ("series_mean", 0.22), ("log_centred", 0.20)):
        assert representations[name] == pytest.approx(ari, rel=0, abs=0.01)
    composition = pd.DataFrame(clusters["composition"]).set_index("neighbourhood")
    for name, endpoints in {
        "ESTORIL": (114.5, 105.1),
        "PALMARES": (136.9, 90.0),
        "SANTA TEREZINHA": (133.1, 101.2),
    }.items():
        np.testing.assert_allclose(
            composition.loc[name, ["all_apartments", "excluding_new"]].to_numpy(dtype=float),
            endpoints,
            rtol=0,
            atol=0.05,
            err_msg=name,
        )
    boot = clusters["bootstrap"]
    assert boot["ari_median"] == pytest.approx(0.43, rel=0, abs=0.07)
    assert boot["endpoint_se_median"] == pytest.approx(4.4, rel=0, abs=0.6)


def test_reference_neighbourhood_interval_widths(diagnostics) -> None:
    uncertainty = diagnostics["neighbourhood_quarterly_uncertainty"]
    widths = pd.DataFrame(uncertainty["neighbourhoods"]).set_index("neighbourhood")
    references = {
        "SAVASSI": 0.16,
        "LOURDES": 0.18,
        "CASTELO": 0.09,
        "BURITIS": 0.08,
        "CENTRO": 0.19,
    }
    for name, width in references.items():
        assert widths.loc[name, "median_record_relative_width"] == pytest.approx(
            width, rel=0, abs=0.02
        )
    quarters = pd.DataFrame(uncertainty["quarters"])
    assert quarters["n_clusters"].gt(0).all()
    assert quarters["n_clusters"].le(quarters["n"]).all()
    assert quarters["block_p025"].le(quarters["block_p975"]).all()


def test_all_specifications_have_consistent_counts_intervals_and_identities(
    evidence_dir, specifications
) -> None:
    ids = tuple(spec.spec_id for spec in PROTOCOL.specifications)
    assert tuple(specifications.index) == ids
    for grid in ("price_floor_", "ratio_floor_"):
        counts = specifications.loc[specifications.index.str.startswith(grid), "n"]
        assert (np.diff(counts) < 0).all()
    exclusions = pd.read_csv(evidence_dir / "exclusions.csv")
    totals = exclusions.groupby("spec_id")[["n_population", "n_removed"]].sum().reindex(ids)
    np.testing.assert_array_equal(totals["n_removed"], specifications["n_removed"])
    np.testing.assert_array_equal(
        totals["n_population"] - totals["n_removed"], specifications["n"]
    )
    index = pd.read_csv(evidence_dir / "index_trajectories.csv")
    for _, group in index.groupby("spec_id"):
        assert tuple(group["quarter"]) == QUARTERS
    assert np.isfinite(index[["index", "lower", "upper", "se"]]).all().all()
    assert index["lower"].le(index["index"]).all() and index["index"].le(index["upper"]).all()
    huber = specifications.loc[["huber_global", "huber_year"]]
    assert huber["iterations"].between(1, PROTOCOL.max_iterations).all()
    assert huber["score_max"].lt(SCORE_TOLERANCE).all()
    assert huber["fixed_point_gap"].lt(FIXED_POINT_TOLERANCE).all()
    decomposition = pd.read_csv(evidence_dir / "decomposition.csv")
    assert decomposition["identity_error"].abs().lt(IDENTITY_TOLERANCE).all()


def _compare_json(actual, expected) -> None:
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key, value in expected.items():
            _compare_json(actual[key], value)
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for value, reference in zip(actual, expected, strict=True):
            _compare_json(value, reference)
    elif isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=1e-6)
    else:
        assert actual == expected


def _compare_csv(fresh: Path, reference: Path) -> None:
    actual, expected = pd.read_csv(fresh), pd.read_csv(reference)
    assert list(actual.columns) == list(expected.columns)
    assert len(actual) == len(expected)
    for column in expected:
        if is_numeric_dtype(expected[column]):
            np.testing.assert_allclose(
                actual[column], expected[column], rtol=1e-6, atol=1e-12, err_msg=column
            )
        else:
            pd.testing.assert_series_equal(actual[column], expected[column])


@pytest.mark.skipif(
    os.environ.get("BH_ITBI_REAL_DATA") != "1",
    reason="Requires the prepared pinned transaction and model cache.",
)
def test_audit_reproduces_committed_evidence(tmp_path) -> None:
    """Regenerate the pinned evidence from the cache, which takes several minutes."""
    if not COMMITTED.exists():
        pytest.skip("Pinned audit evidence has not been committed.")
    run_audit(tmp_path)
    names = {path.name for path in COMMITTED.iterdir()}
    assert names == {path.name for path in tmp_path.iterdir()}
    for name in sorted(names):
        fresh, reference = tmp_path / name, COMMITTED / name
        if name == "manifest.json":
            fields = {
                "revision",
                "source_sha256",
                "protocol_id",
                "protocol_sha256",
                "protocol_settings",
                "seed",
                "cluster_draws",
                "median_draws",
                "thread_limit",
                "model_version",
                "patterns_id",
                "pattern_settings",
            }
            actual, expected = _load_json(fresh), _load_json(reference)
            assert {key: actual[key] for key in fields} == {
                key: expected[key] for key in fields
            }
        elif fresh.suffix == ".csv":
            _compare_csv(fresh, reference)
        elif name == "diagnostics.json":
            _compare_json(_load_json(fresh), _load_json(reference))
        else:
            assert fresh.read_bytes() == reference.read_bytes(), name
