"""Build artefact integrity, strict startup and optional real-data smoke tests."""

import json
import os
from concurrent.futures import ThreadPoolExecutor

import huggingface_hub
import numpy as np
import pandas as pd
import pytest
from test_app import post_callback

from bh_itbi import data, models
from bh_itbi.app import create_app
from bh_itbi.config import MODEL_VERSION
from bh_itbi.figures import map_figure
from bh_itbi.filters import Filters, filter_transactions, positive_area
from bh_itbi.overview import map_points, map_reference_scales


@pytest.fixture
def prepared_cache(tmp_path, monkeypatch, source_factory):
    """Exercise real source validation and publication without a network request."""
    source = tmp_path / "source.parquet"
    source_factory().to_parquet(source, index=False)
    monkeypatch.setattr(data, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(models, "MODEL_DIR", data.CACHE_DIR / f"models-{MODEL_VERSION}")
    monkeypatch.setattr(data, "SOURCE_SHA256", data.file_sha256(source))
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", lambda **kwargs: source)
    data.prepare_cache()
    return source


def test_compact_cache_preserves_transactions_and_measurement_precision(prepared_cache):
    expected = data.prepare_transactions(pd.read_parquet(prepared_cache))
    actual = data.load_transactions(allow_prepare=False)
    assert set(actual.columns) == set(data.TRANSACTION_COLUMNS)
    # Parquet normalises string-category NA metadata; compare every value exactly
    # and check the numerical storage contract separately below.
    pd.testing.assert_frame_equal(
        actual,
        expected[data.TRANSACTION_COLUMNS],
        check_dtype=False,
        check_categorical=False,
        check_exact=True,
    )
    assert actual["year"].dtype == np.int16
    assert all(
        actual[column].dtype == np.float64
        for column in [
            "lat",
            "lon",
            "value_declared_brl",
            "value_tax_base_brl",
            "built_area_m2",
            "price_per_m2_brl",
            "price_per_m2_brl_real",
            "distance_km",
        ]
    )
    assert data.load_transactions() is actual


def test_build_rejects_a_source_with_the_wrong_sha256(prepared_cache, monkeypatch):
    monkeypatch.setattr(data, "SOURCE_SHA256", "0" * 64)
    with pytest.raises(data.DataError, match="SHA-256"):
        data.prepare_cache()


@pytest.mark.parametrize("failure", ["missing", "corrupt", "revision", "source_sha256"])
def test_production_rejects_invalid_data_without_preparing(
    prepared_cache, monkeypatch, failure
):
    def unexpected_prepare():
        pytest.fail("Production must never download or reconstruct data")

    monkeypatch.setattr(data, "prepare_cache", unexpected_prepare)
    table = data.CACHE_DIR / "transactions.parquet"
    if failure == "missing":
        table.unlink()
    elif failure == "corrupt":
        table.write_bytes(b"partial parquet")
    else:
        path = data.CACHE_DIR / "source.json"
        metadata = json.loads(path.read_text())
        metadata[failure] = "obsolete"
        path.write_text(json.dumps(metadata))
    with pytest.raises(data.DataError):
        create_app(require_prepared=True)


def test_production_rejects_missing_models_instead_of_omitting_panels(prepared_cache):
    with pytest.raises(data.DataError, match="Prepared models are missing or incompatible"):
        create_app(require_prepared=True)


@pytest.mark.parametrize("failure", [None, "missing", "corrupt", "model_version"])
def test_model_manifest_checks_every_required_table(tmp_path, failure):
    metadata = {
        "revision": data.REVISION,
        "source_sha256": data.SOURCE_SHA256,
        "model_version": MODEL_VERSION,
        "tables_sha256": {},
    }
    for name in ("hedonic", "members", "centres"):
        path = tmp_path / f"{name}.parquet"
        data.atomic_parquet(pd.DataFrame({"index": [100.0]}), path)
        metadata["tables_sha256"][name] = data.file_sha256(path)
    if failure == "missing":
        (tmp_path / "members.parquet").unlink()
    elif failure == "corrupt":
        (tmp_path / "centres.parquet").write_bytes(b"partial parquet")
    elif failure:
        metadata[failure] = "obsolete"
    data.atomic_json(metadata, tmp_path / "metadata.json")
    result = models.load_models(tmp_path)
    assert (result is None) == (failure is not None)


def test_concurrent_selections_preserve_shared_transactions(source_factory):
    frame = data.prepare_transactions(source_factory())
    original = frame.copy(deep=True)
    app = create_app(frame=frame)
    assert app.server.test_client().get("/healthz").status_code == 200

    def select(names):
        result = post_callback(
            app,
            "geo-map.figure",
            ["apartment", [2016, 2016], names, "price_per_m2_brl_real", "white-bg"],
        )
        return result["kpi-count"]["children"]

    with ThreadPoolExecutor(max_workers=6) as pool:
        counts = list(pool.map(select, [[], ["SAVASSI"], ["LOURDES"]] * 2))
    assert counts == ["40", "20", "20"] * 2
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.skipif(
    os.environ.get("BH_ITBI_REAL_DATA") != "1",
    reason="Run after main.py prepare with BH_ITBI_REAL_DATA=1 (no downloads or fitting)",
)
def test_all_production_sections_with_real_prepared_data(monkeypatch):
    def unexpected_prepare(*args, **kwargs):
        pytest.fail("Serving must use only the build artefacts")

    monkeypatch.setattr(data, "prepare_cache", unexpected_prepare)
    monkeypatch.setattr(models, "fit_hedonic", unexpected_prepare)
    monkeypatch.setattr(models, "cluster_trajectories", unexpected_prepare)
    app = create_app(require_prepared=True)
    client = app.server.test_client()
    for path in ("/", "/healthz", "/_dash-layout", "/_dash-dependencies"):
        assert client.get(path).status_code == 200
    result = post_callback(
        app,
        "geo-map.figure",
        [
            "all",
            [2016, 2025],
            [],
            "price_per_m2_brl_real",
            "white-bg",
        ],
    )
    frame = data.load_transactions(allow_prepare=False)
    population = frame.loc[frame["year"].between(2016, 2025)]
    assert result["kpi-count"]["children"] == f"{len(population):,}".replace(",", ".")
    assert result["geo-map"]["figure"]["data"][0]["type"] == "scattermap"
    comparison = result["comparison-data"]["data"]
    price = "price_per_m2_brl_real"
    assert comparison["city_median"] == population[price].median()
    assert len(comparison["rows"]) == 5
    for row in comparison["rows"]:
        selected = population.loc[population["neighbourhood"].eq(row["name"].upper()), price]
        assert row["quantiles"][2] == selected.median()
        assert row["n"] == selected.count()
    result = post_callback(
        app,
        "tax-figure.figure",
        [
            "all",
            [2016, 2025],
            [],
            "diagnostics",
        ],
    )
    for identifier in ("tax-figure", "heaping-figure", "distance-figure"):
        assert result[identifier]["figure"]["data"]
    age = result["age-data"]["data"]
    assert len(age["rows"]) == 4
    assert all(row["segments"][-1]["end"] == row["observed"] for row in age["rows"][:-1])
    assert age["rows"][-1]["reference"]
    assert age["rows"][-1]["observed"] == 0.0

    assert_real_models(app)


@pytest.mark.skipif(
    os.environ.get("BH_ITBI_REAL_DATA") != "1",
    reason="Run after main.py prepare with BH_ITBI_REAL_DATA=1 (no downloads or fitting)",
)
def test_savassi_map_retains_at_least_95_percent_of_candidates() -> None:
    filters = Filters(neighbourhoods=("SAVASSI",))
    frame = data.load_transactions(allow_prepare=False)
    selected = filter_transactions(frame, filters)
    candidates = int((selected["face_geocoded"] & positive_area(selected)).sum())
    app = create_app(require_prepared=True)
    result = post_callback(
        app,
        "geo-map.figure",
        [
            filters.property_type,
            [filters.start_year, filters.end_year],
            list(filters.neighbourhoods),
            "price_per_m2_brl_real",
            "white-bg",
        ],
    )
    drawn = len(result["geo-map"]["figure"]["data"][0]["customdata"])
    assert candidates > 0
    assert drawn / candidates >= 0.95


@pytest.mark.skipif(
    os.environ.get("BH_ITBI_REAL_DATA") != "1",
    reason="Run after main.py prepare with BH_ITBI_REAL_DATA=1",
)
def test_default_map_marker_diameters() -> None:
    frame = data.load_transactions(allow_prepare=False)
    points, _ = map_points(filter_transactions(frame, Filters()))
    scales = map_reference_scales(frame)
    figure = map_figure(points, "open-street-map", scales)
    marker = figure.data[0].marker
    sizes = np.asarray(marker.size)
    # P98 refers to the full-period area reference, which caps the sampled sizes.
    assert sizes.max() == scales["area_reference"]
    radii = np.maximum(np.sqrt(sizes / (2 * marker.sizeref)), marker.sizemin)
    diameters = 2 * radii
    np.testing.assert_allclose(
        [diameters.min(), np.median(diameters), diameters.max()],
        [3.7, 6.1, 11.3],
        atol=0.15,
        rtol=0,
    )


def assert_real_models(app):
    result = post_callback(app, "hedonic-figure.figure", ["models"])
    hedonic_figure = result["hedonic-figure"]["figure"]
    assert hedonic_figure["layout"]["yaxis"]["type"] == "log"
    assert hedonic_figure["data"][-1]["name"] == "Índice hedônico · IC 95%"
    traces = result["trajectories-figure"]["figure"]["data"]
    assert len(traces) == 95
    assert [trace["name"] for trace in traces if trace.get("showlegend", True)] == [
        "Bairros",
        "Mediana entre os bairros",
    ]
    assert all(trace["legendgroup"] == "neighbourhoods" for trace in traces[:-1])
    fitted = models.load_models()
    assert fitted is not None
    assert fitted.metadata["hedonic"]["n"] == 202204
    assert fitted.metadata["clusters"]["n_neighbourhoods"] == 94
    assert fitted.hedonic["n"].sum() == 202204
    hedonic = fitted.hedonic
    indices = ["hedonic_index", "lower", "upper", "raw_geometric_mean"]
    assert np.isfinite(hedonic[indices]).all().all()
    assert hedonic["identity_error"].abs().max() < 1e-8
    contributions = hedonic[list(models.COMPOSITION_TERMS)]
    gap = np.log(hedonic["raw_geometric_mean"] / hedonic["hedonic_index"])
    np.testing.assert_allclose(gap, contributions.sum(axis=1), atol=1e-8, rtol=0)
    assert hedonic.iloc[0]["quarter"] == "2016Q1"
    assert hedonic.iloc[0][indices].eq(100).all()
    assert contributions.iloc[0].eq(0).all()
