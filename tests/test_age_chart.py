"""Signed bar geometry on the same additive axis as the observed markers."""

import pytest

from bh_itbi.age_chart import age_segments


@pytest.mark.parametrize(
    ("contributions", "order"),
    [
        ({"Bairro": 0.1, "Área": 0.2, "Trimestre": 0.3}, ["Trimestre", "Área", "Bairro"]),
        ({"Bairro": -0.1, "Área": -0.2, "Trimestre": -0.3}, ["Trimestre", "Área", "Bairro"]),
        ({"Bairro": -0.1, "Área": 0.2, "Trimestre": -0.003}, ["Área", "Bairro", "Trimestre"]),
    ],
)
def test_segments_stack_in_sign_order_and_end_exactly_at_observed(
    contributions: dict[str, float], order: list[str]
) -> None:
    adjusted = 0.25
    observed = adjusted + sum(contributions.values()) + 1e-16
    segments = age_segments(adjusted, contributions, observed)
    assert segments[0]["start"] == 0
    assert segments[0]["end"] == adjusted
    assert [segment["group"] for segment in segments[1:]] == order
    assert segments[-1]["end"] == observed
    for prior, segment in zip(segments, segments[1:], strict=False):
        key = segment["group"]
        assert segment["start"] == prior["end"]
        assert segment["end"] - segment["start"] == pytest.approx(contributions[key])
        assert segment["subtracts"] == (contributions[key] < 0)
        assert segment["hidden"] == (key == "Trimestre" and abs(contributions[key]) < 0.005)
