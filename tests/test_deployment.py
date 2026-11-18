"""Build artefact integrity, strict startup and optional real-data smoke tests."""

import json
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import pytest
from test_app import post_callback

from bh_itbi import data, models
from bh_itbi.app import create_app


@pytest.fixture
def prepared_cache(tmp_path, monkeypatch, source_factory):
    """Exercise real source validation and publication without a network request."""
    import huggingface_hub

    source = tmp_path / "source.parquet"
    source_factory().to_parquet(source, index=False)
    monkeypatch.setattr(data, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(models, "MODEL_DIR", data.CACHE_DIR / f"models-{models.MODEL_VERSION}")
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
    with pytest.raises(data.DataError, match="Modelos preparados"):
        create_app(require_prepared=True)


@pytest.mark.parametrize("failure", [None, "missing", "corrupt", "model_version"])
def test_model_manifest_checks_every_required_table(tmp_path, failure):
    metadata = {
        "revision": data.REVISION,
        "source_sha256": data.SOURCE_SHA256,
        "model_version": models.MODEL_VERSION,
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
    for identifier in ("tax-figure", "heaping-figure", "age-figure", "distance-figure"):
        assert result[identifier]["figure"]["data"]
    cluster_colours = {"1": "#6c4fae", "2": "#3d7f4a", "3": "#d77a9a", "4": "#e09a3e"}
    for group in ("all", *cluster_colours):
        result = post_callback(app, "hedonic-figure.figure", [group])
        hedonic_figure = result["hedonic-figure"]["figure"]
        assert hedonic_figure["layout"]["yaxis"]["type"] == "log"
        assert hedonic_figure["data"][-1]["name"] == "Índice hedônico · IC 95%"
        traces = result["clusters-figure"]["figure"]["data"]
        expected = cluster_colours if group == "all" else {group: cluster_colours[group]}
        assert {trace["legendgroup"] for trace in traces} == set(expected)
        for trace in traces:
            assert trace["line"]["color"] == expected[trace["legendgroup"]]
            if not trace.get("showlegend", True):
                assert trace["opacity"] == 0.25
        assert result["cluster-members"]["children"]
    fitted = models.load_models()
    assert fitted["metadata"]["hedonic"]["n"] == 202204
    assert fitted["metadata"]["clusters"]["n_neighbourhoods"] == 94
    assert fitted["hedonic"]["n"].sum() == 202204
    hedonic = fitted["hedonic"]
    indices = ["indice_hedonico", "lower", "upper", "media_geometrica_bruta"]
    assert np.isfinite(hedonic[indices]).all().all()
    assert hedonic["erro_identidade"].abs().max() < 1e-8
    contributions = hedonic[list(models.COMPOSITION_TERMS)]
    gap = np.log(hedonic["media_geometrica_bruta"] / hedonic["indice_hedonico"])
    np.testing.assert_allclose(gap, contributions.sum(axis=1), atol=1e-8, rtol=0)
    assert hedonic.iloc[0]["quarter"] == "2016Q1"
    assert hedonic.iloc[0][indices].eq(100).all()
    assert contributions.iloc[0].eq(0).all()
