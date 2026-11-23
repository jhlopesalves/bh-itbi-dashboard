"""Verify the fixed specification order, subset boundaries and OLS reproduction."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from threadpoolctl import threadpool_limits

from bh_itbi.config import ROOT, YEARS
from bh_itbi.data import DataError, file_sha256
from bh_itbi.models import fit_hedonic, model_population
from bh_itbi.sensitivity import (
    PROTOCOL,
    QUARTERS,
    SensitivityError,
    _estimate_specification,
    _quarter_estimates,
    exclusion_counts,
    sensitivity_design,
    specification_design,
    specification_mask,
)

IDS = (
    "baseline",
    "price_floor_0500",
    "price_floor_0750",
    "price_floor_1000",
    "price_floor_1250",
    "price_floor_1500",
    "price_ceiling_30000",
    "ratio_floor_030",
    "ratio_floor_040",
    "ratio_floor_050",
    "ratio_floor_060",
    "ratio_floor_070",
    "area_20_1000",
    "combined_reference_v2",
    "apartments_only",
    "houses_only",
    "huber_global",
    "huber_year",
)


def test_protocol_ids_are_unique_and_ordered() -> None:
    assert tuple(spec.spec_id for spec in PROTOCOL.specifications) == IDS
    assert len(set(IDS)) == len(IDS)
    assert PROTOCOL.canonical_json() == replace(PROTOCOL).canonical_json()


def test_protocol_hash_matches_published_bytes() -> None:
    path = ROOT / "docs" / "robustness" / "protocol.json"
    if not path.exists():
        pytest.skip("The audit evidence has not been generated.")
    assert PROTOCOL.sha256 == file_sha256(path)


@pytest.mark.parametrize(
    ("spec_id", "column", "values", "expected"),
    [
        *[
            (
                f"price_floor_{floor:04d}",
                "price_per_m2_brl_real",
                [floor - 0.01, floor, floor + 0.01],
                [False, True, True],
            )
            for floor in (500, 750, 1000, 1250, 1500)
        ],
        (
            "price_ceiling_30000",
            "price_per_m2_brl_real",
            [29999, 30000, 30001],
            [True, True, False],
        ),
        *[
            (
                f"ratio_floor_{floor:03d}",
                "value_declared_brl",
                [floor - 0.01, floor, floor + 0.01],
                [False, True, True],
            )
            for floor in (30, 40, 50, 60, 70)
        ],
        ("area_20_1000", "built_area_m2", [19.99, 20, 1000], [False, True, True]),
        ("combined_reference_v2", "built_area_m2", [20, 1000, 1000.01], [True, True, False]),
        (
            "combined_reference_v2",
            "price_per_m2_brl_real",
            [999, 1000, 30000],
            [False, True, True],
        ),
        (
            "apartments_only",
            "property_type",
            ["house", "apartment", "house"],
            [False, True, False],
        ),
        ("houses_only", "property_type", ["house", "apartment", "house"], [True, False, True]),
    ],
)
def test_screens_retain_boundaries(spec_id, column, values, expected) -> None:
    population = pd.DataFrame(
        {
            "value_tax_base_brl": [100.0] * 3,
            "value_declared_brl": [95.0] * 3,
            "built_area_m2": [100.0] * 3,
            "price_per_m2_brl_real": [3500.0] * 3,
            "property_type": ["apartment"] * 3,
        }
    )
    population[column] = values
    spec = PROTOCOL.specifications[IDS.index(spec_id)]
    np.testing.assert_array_equal(specification_mask(population, spec), expected)


def test_invalid_tax_base_fails_even_without_a_screen() -> None:
    population = pd.DataFrame({"value_tax_base_brl": [20.0, 0.0]})
    with pytest.raises(DataError, match="positive tax base"):
        specification_mask(population, PROTOCOL.specifications[0])


def test_subset_preserves_small_neighbourhood_and_drops_empty_levels(snapshot_frame) -> None:
    population = model_population(snapshot_frame)
    design = sensitivity_design(population)
    small = population["neighbourhood"].eq("SAVASSI").to_numpy()
    empty = population["neighbourhood"].eq("LOURDES").to_numpy()
    mask = ~small & ~empty
    mask[np.flatnonzero(small)[0]] = True
    subset = specification_design(design, mask, spec_id="subset")
    assert tuple(np.unique(subset.quarters)) == QUARTERS
    assert int((subset.groups == design.groups[small][0]).sum()) == 1
    assert "C(neighbourhood)[T.LOURDES]" in set(design.columns) - set(subset.columns)
    np.testing.assert_array_equal(subset.y, design.y[mask])
    counts = exclusion_counts(design, mask, "subset")
    assert len(counts) == 2 * len(YEARS)
    assert counts["n_population"].sum() == len(mask)
    assert counts["n_removed"].sum() == (~mask).sum()


def test_subset_rebases_the_factor_when_its_reference_disappears(snapshot_frame) -> None:
    design = sensitivity_design(model_population(snapshot_frame))
    # The snapshot has few houses after Q1 in later years, so express the
    # constant dummy case by retaining apartments and changing the dummy to one.
    x = design.x.copy()
    house = np.flatnonzero(design.terms == "C(property_type)")[0]
    apartments = design.property_types == "apartment"
    x[apartments, house] = 1
    subset = specification_design(replace(design, x=x), apartments, spec_id="subset")
    assert design.columns[house] not in subset.columns
    assert np.count_nonzero(subset.terms == "C(property_type)") == 0


def test_subset_rejects_losing_any_quarter(snapshot_frame) -> None:
    design = sensitivity_design(model_population(snapshot_frame))
    keep = design.quarters != "2016Q1"
    with pytest.raises(SensitivityError, match="2016Q1"):
        specification_design(design, keep, spec_id="subset")


def test_baseline_reproduces_the_published_fit(snapshot_frame, snapshot_models) -> None:
    design = sensitivity_design(model_population(snapshot_frame))
    with threadpool_limits(limits=2):
        fit = _estimate_specification(design, PROTOCOL.specifications[0])
        expected, metadata = fit_hedonic(snapshot_frame)
    table, _ = _quarter_estimates(design, fit, "baseline")
    assert table["n"].sum() == metadata["n"]
    assert fit.r_squared == pytest.approx(metadata["r_squared"], rel=1e-9)
    for published in (expected, snapshot_models.hedonic):
        np.testing.assert_allclose(
            table[["index", "lower", "upper"]],
            published[["hedonic_index", "lower", "upper"]],
            rtol=1e-9,
            atol=0,
        )
