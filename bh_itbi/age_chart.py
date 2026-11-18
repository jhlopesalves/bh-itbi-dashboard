"""Geometry and Portuguese display values for the age-premium chart."""

from collections.abc import Mapping
from typing import TypedDict

from bh_itbi.age import AGE_GROUPS, AgePremiums
from bh_itbi.config import (
    AGE_REFERENCE,
    QUARTER_VISIBILITY,
)
from bh_itbi.filters import Filters
from bh_itbi.formatting import age_percent
from bh_itbi.text import (
    AGE_EMPTY_MESSAGE,
    AGE_LABELS,
    AGE_REFERENCE_LABEL,
    age_row_tooltip,
)
from bh_itbi.text import (
    age_note as format_age_note,
)
from bh_itbi.text import (
    age_subtitle as format_age_subtitle,
)
from bh_itbi.theme import AGE_FILLS, TEAL


class AgeSegment(TypedDict):
    group: str
    start: float
    end: float
    subtracts: bool
    hidden: bool


class AgeChartRow(TypedDict):
    label: str
    reference: bool
    observed: float
    observed_label: str
    adjusted_label: str
    segments: list[AgeSegment]
    interval: tuple[float, float] | None
    tooltip: list[str]


class AgeChart(TypedDict):
    rows: list[AgeChartRow]
    fills: dict[str, str]
    teal: str
    empty: str


def age_segments(
    adjusted: float, contributions: Mapping[str, float], observed: float
) -> list[AgeSegment]:
    """Stack additions then subtractions. Retain the endpoints of hidden terms."""
    segments: list[AgeSegment] = [
        {
            "group": "Ajustado",
            "start": 0.0,
            "end": adjusted,
            "subtracts": False,
            "hidden": False,
        }
    ]
    ordered = sorted(contributions.items(), key=lambda item: (item[1] < 0, -abs(item[1])))
    end = adjusted
    for group, value in ordered:
        if value == 0:
            continue
        start, end = end, end + value
        segments.append(
            {
                "group": group,
                "start": start,
                "end": end,
                "subtracts": value < 0,
                "hidden": group == "Trimestre" and abs(value) < QUARTER_VISIBILITY,
            }
        )
    # The estimator checks the identity independently. Snap only the residual
    # floating-point error so the final endpoint and marker share a coordinate.
    segments[-1]["end"] = observed
    return segments


def age_chart_data(result: AgePremiums) -> AgeChart:
    """Keep axis coordinates in log points and send preformatted tooltip strings."""
    rows: list[AgeChartRow] = []
    visible: set[str] = set()
    for key, row in result.table.iterrows():
        label = AGE_LABELS[str(key)]
        observed = float(row["observed"])
        reference = key == AGE_REFERENCE
        observed_percent = age_percent(observed)
        adjusted_label = ""
        segments: list[AgeSegment] = []
        interval: tuple[float, float] | None = None
        adjusted_details: tuple[float, float, float, dict[str, float]] | None = None
        if not reference and "adjusted" in row:
            adjusted = float(row["adjusted"])
            adjusted_percent = age_percent(adjusted)
            contributions = {group: float(row[group]) for group in AGE_GROUPS}
            segments = age_segments(adjusted, contributions, observed)
            visible.update(segment["group"] for segment in segments if not segment["hidden"])
            lower, upper = float(row["lower"]), float(row["upper"])
            interval = (lower, upper)
            adjusted_label = f"ajustado {adjusted_percent}"
            adjusted_details = (adjusted, lower, upper, contributions)
        tooltip = age_row_tooltip(
            label,
            float(row["n"]),
            float(row["geometric_mean"]),
            observed,
            adjusted_details,
        )
        rows.append(
            {
                "label": label,
                "reference": reference,
                "observed": observed,
                "observed_label": AGE_REFERENCE_LABEL
                if reference
                else f"observado {observed_percent}",
                "adjusted_label": adjusted_label,
                "segments": segments,
                "interval": interval,
                "tooltip": tooltip,
            }
        )
    return {
        "rows": rows,
        "fills": {group: fill for group, fill in AGE_FILLS.items() if group in visible},
        "teal": TEAL,
        "empty": result.unavailable or AGE_EMPTY_MESSAGE,
    }


def age_subtitle(filters: Filters, *, adjusted: bool) -> str:
    """Describe the intersection with the fixed apartment cohort in plain words."""
    return format_age_subtitle(
        filters.property_type,
        filters.start_year,
        filters.end_year,
        has_neighbourhoods=bool(filters.neighbourhoods),
        adjusted=adjusted,
    )


def age_note(result: AgePremiums) -> str:
    """Explain the adjustment and add any selection-specific qualifications."""
    adjusted = "adjusted" in result.table
    quarter_values = (
        {str(key): float(value) for key, value in result.table["Trimestre"].items()}
        if adjusted
        else {}
    )
    return format_age_note(
        adjusted=adjusted,
        quarter_values=quarter_values,
        unavailable=result.unavailable,
        excluded=result.excluded,
    )
