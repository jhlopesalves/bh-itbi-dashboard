"""Eligibility, estimator populations, geographical intersections and time gaps."""

from dataclasses import replace
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from bh_itbi.analysis import (
    Filters,
    city_quarterly_table,
    distribution_quartiles,
    filter_transactions,
    heaping_summary,
    heaping_table,
    map_points,
    quantile_table,
    summary,
    tax_base_table,
    temporal_table,
)
from bh_itbi.callbacks import clicked_neighbourhood
from bh_itbi.data import DataError, atomic_parquet, prepare_transactions
from bh_itbi.figures import distribution_figure, number, temporal_figure
from bh_itbi.models import model_population


def test_notebook_eligibility_keeps_inclusive_bounds_and_real_tail(source_factory):
    source = source_factory(8)
    source.loc[0, "value_flag"] = "symbolic"
    source.loc[1, "property_type"] = "parking"
    source.loc[2, "price_per_m2_brl"] = Decimal("99.99")
    source.loc[3, "price_per_m2_brl"] = Decimal("200000.01")
    source.loc[4, "price_per_m2_brl"] = Decimal("100")
    source.loc[5, "price_per_m2_brl"] = Decimal("200000")
    source.loc[6, "price_per_m2_brl_real"] = Decimal("463865.91")
    result = prepare_transactions(source)
    assert result["transaction_id"].tolist() == ["test-4", "test-5", "test-6", "test-7"]
    assert (
        result.loc[result["transaction_id"].eq("test-6"), "price_per_m2_brl_real"].iat[0]
        == 463865.91
    )


@pytest.mark.parametrize("failure", ["missing", "duplicate", "city", "date", "year"])
def test_invalid_source_fails_explicitly(source_factory, failure):
    source = source_factory(2)
    if failure == "missing":
        source = source.drop(columns="geo_precision")
    elif failure == "duplicate":
        source.loc[1, "transaction_id"] = source.loc[0, "transaction_id"]
    elif failure == "city":
        source.loc[0, "city"] = "sao_paulo"
    elif failure == "date":
        source.loc[0, "transaction_date"] = "invalid"
    else:
        source.loc[0, "year"] = 2020
    with pytest.raises(DataError):
        prepare_transactions(source)


def test_map_respects_recorded_precision_and_invalid_coordinates(source_factory):
    source = source_factory(5)
    source.loc[0, "geo_precision"] = "postcode_centroid"
    source.loc[1, "geo_precision"] = "neighbourhood_centroid"
    source.loc[2, "lat"] = np.inf
    source.loc[3, "lon"] = 181
    result = prepare_transactions(source)
    assert result["face_geocoded"].tolist() == [False, False, False, False, True]
    assert result.loc[4, "distance_km"] == pytest.approx(0)


def test_neighbourhood_membership_is_not_inferred_from_identical_coordinates(source_factory):
    source = source_factory()
    source.loc[0, "neighbourhood"] = " lourdes "
    frame = prepare_transactions(source)
    assert frame[["lat", "lon"]].drop_duplicates().shape[0] == 1
    selected = filter_transactions(frame, Filters(neighbourhoods=("LOURDES",)))
    assert len(selected) == 20
    assert selected["neighbourhood"].eq("LOURDES").all()
    assert filter_transactions(frame, Filters(neighbourhoods=("UNKNOWN",))).empty


def test_city_reference_removes_neighbourhood_filter(source_factory):
    frame = prepare_transactions(source_factory())
    filters = Filters("apartment", 2016, 2016, ("SAVASSI",))
    assert len(filter_transactions(frame, filters)) == 20
    assert len(filter_transactions(frame, filters.city_reference())) == 40
    assert filters.city_reference().property_type == "apartment"
    assert filters.city_reference().end_year == 2016


def test_map_screen_and_seeded_sample_do_not_change_summary_population(source_factory):
    frame = prepare_transactions(source_factory(9000))
    points, stats = map_points(frame)
    assert stats["candidates"] == 9000
    assert stats["shown"] == 8000
    assert len(points) == 8000
    assert points["price_per_m2_brl"].between(stats["lower"], stats["upper"]).all()
    pd.testing.assert_frame_equal(points, map_points(frame)[0])
    assert summary(frame)["n"] == 9000


def test_quantiles_count_non_missing_values_before_suppression():
    frame = pd.DataFrame(
        {
            "group": ["a"] * 5 + ["b"] * 5,
            "price_per_m2_brl_real": [1, 2, 3, 4, np.nan, 10, 20, 30, 40, 50],
        }
    )
    result = quantile_table(frame, ["group"], minimum=5).set_index("group")
    assert result.loc["a", "n"] == 4
    assert pd.isna(result.loc["a", "median"])
    assert result.loc["b", ["p25", "median", "p75"]].tolist() == [20, 30, 40]


def test_months_and_ribbons_do_not_bridge_absent_or_suppressed_periods(source_factory):
    source = source_factory(90)
    source.loc[30:59, "transaction_date"] = "2016-03-01"
    source.loc[60:, "transaction_date"] = "2016-04-01"
    frame = prepare_transactions(source)
    # Exercise the apartment series explicitly; the dashboard now defaults to both types.
    filters = Filters(property_type="apartment", start_year=2016, end_year=2016)
    rows = temporal_table(frame, filters)
    assert len(rows) == 12
    assert pd.isna(rows.loc[rows["month"].eq("2016-02-01"), "median"].iat[0])
    fig = temporal_figure(frame, frame, filters)
    fills = [trace for trace in fig.data if trace.fill == "tonexty"]
    assert len(fills) == 1  # Only March–April; January is an isolated point.
    assert pd.Timestamp(fills[0].x[0]).month == 3
    median = next(t for t in fig.data if t.name == "Apartamentos")
    assert not median.connectgaps


def test_price_summary_does_not_drop_records_missing_real_values(source_factory):
    frame = prepare_transactions(source_factory(5))
    frame.loc[0, "price_per_m2_brl_real"] = np.nan
    result = summary(frame)
    assert result["n"] == 5 and result["real_n"] == 4
    assert np.isfinite(result["nominal"])
    assert pd.isna(result["real"])


def test_tax_share_denominator_and_quarter_minimum(source_factory):
    frame = prepare_transactions(source_factory(120))
    frame["value_declared_brl"] = 200_000.0
    frame["value_tax_base_brl"] = 100_000.0
    frame.loc[:19, "value_tax_base_brl"] = 0
    frame.loc[20:44, "value_declared_brl"] = 50_000
    table = tax_base_table(frame)
    assert table.iloc[0]["n"] == 100
    assert table.iloc[0]["share"] == pytest.approx(0.25)
    assert pd.isna(tax_base_table(frame.iloc[:-1]).iloc[0]["share"])


def test_heaping_counts_near_round_values_not_only_exact_multiples(source_factory):
    frame = prepare_transactions(source_factory(4))
    frame["year"] = 2023
    frame["value_declared_brl"] = [50_000, 52_000, 52_500, 74_000]
    raw_table = heaping_table(frame)
    table = raw_table.set_index("value")
    assert table.loc[50_000, "n"] == 3  # Includes half-to-even tie at 52,500.
    assert table.loc[75_000, "n"] == 1
    assert table.loc[50_000, "is_round_bin"]
    assert not table.loc[75_000, "is_round_bin"]
    total, share = heaping_summary(raw_table)
    assert total == 4 and share == pytest.approx(0.75)


def test_distribution_quartiles_and_city_quarterly_reference(source_factory):
    frame = prepare_transactions(source_factory(40))
    quartiles = distribution_quartiles(frame, "price_per_m2_brl_real")
    assert quartiles is not None and list(quartiles.index) == [0.25, 0.5, 0.75]
    assert distribution_quartiles(frame.iloc[:4], "price_per_m2_brl_real") is None
    quarterly = city_quarterly_table(frame, Filters(start_year=2016, end_year=2016))
    assert len(quarterly) == 4
    assert np.isfinite(quarterly.loc[0, "median"])
    assert pd.isna(quarterly.loc[1:, "median"]).all()


def test_distribution_retains_all_values_including_extreme_tail(source_factory):
    frame = prepare_transactions(source_factory())
    frame.loc[0, "price_per_m2_brl_real"] = 463865.91
    fig = distribution_figure(frame, "price_per_m2_brl_real")
    assert sum(sum(trace.y) for trace in fig.data) == len(frame)
    assert fig.layout.xaxis.type == "log"


def test_model_population_has_its_own_fixed_dates_and_neighbourhood_minimum(source_factory):
    frame = prepare_transactions(source_factory(220))
    frame["neighbourhood"] = ["SAVASSI"] * 120 + ["LOURDES"] * 99 + ["CENTRO"]
    frame.loc[0, "year"] = 2026
    frame.loc[1, "built_area_m2"] = 0
    result = model_population(frame)
    assert len(result) == 118
    assert result["neighbourhood"].eq("SAVASSI").all()
    assert np.isfinite(result["log_price"]).all()


def test_click_payload_validation_uses_only_the_recorded_neighbourhood():
    assert (
        clicked_neighbourhood(
            {"points": [{"customdata": ["SAVASSI", "Savassi", "Apartamentos"]}]}, {"SAVASSI"}
        )
        == "SAVASSI"
    )
    for payload in [
        None,
        {},
        {"points": None},
        {"points": [{}]},
        {"points": ["x"]},
        {"points": [{"customdata": ["obsolete"]}]},
    ]:
        assert clicked_neighbourhood(payload, {"SAVASSI"}) is None


def test_atomic_cache_and_brazilian_formatting(tmp_path):
    path = tmp_path / "cache" / "table.parquet"
    atomic_parquet(pd.DataFrame({"a": [1, 2]}), path)
    pd.testing.assert_frame_equal(pd.read_parquet(path), pd.DataFrame({"a": [1, 2]}))
    assert list(path.parent.iterdir()) == [path]
    assert number(12345.67, 2) == "12.345,67"
    assert number(np.nan) == "—"


def test_control_validation_and_no_silent_period_reordering():
    assert Filters.from_controls(
        "all", [2016, 2025], ["SAVASSI", "SAVASSI"]
    ).neighbourhoods == ("SAVASSI",)
    with pytest.raises(ValueError):
        Filters.from_controls("all", [2025, 2016], [])
    assert replace(Filters(), end_year=2016).start_year == 2016
