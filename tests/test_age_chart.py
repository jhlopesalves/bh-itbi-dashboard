"""Signed bar geometry on the same additive axis as the observed markers."""

from itertools import pairwise

import pytest

from bh_itbi.figures.diagnostics import age_segments


@pytest.mark.parametrize(
    ("contributions", "order"),
    [
        (
            {"neighbourhood": 0.1, "area": 0.2, "quarter": 0.3},
            ["quarter", "area", "neighbourhood"],
        ),
        (
            {"neighbourhood": -0.1, "area": -0.2, "quarter": -0.3},
            ["quarter", "area", "neighbourhood"],
        ),
        (
            {"neighbourhood": -0.1, "area": 0.2, "quarter": -0.003},
            ["area", "neighbourhood", "quarter"],
        ),
    ],
)
def test_segments_stack_in_sign_order_and_end_exactly_at_observed(
    contributions: dict[str, float], order: list[str]
) -> None:
    adjusted = 0.25
    observed = adjusted + sum(contributions.values()) + 1e-16
    segments = age_segments(adjusted, contributions, observed)
    assert segments[0]["group"] == "adjusted"
    assert segments[0]["start"] == 0
    assert segments[0]["end"] == adjusted
    assert [segment["group"] for segment in segments[1:]] == order
    assert segments[-1]["end"] == observed
    for prior, segment in pairwise(segments):
        key = segment["group"]
        assert segment["start"] == prior["end"]
        assert segment["end"] - segment["start"] == pytest.approx(contributions[key])
        assert segment["subtracts"] == (contributions[key] < 0)
        assert segment["hidden"] == (key == "quarter" and abs(contributions[key]) < 0.005)
