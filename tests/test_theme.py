"""Consistency checks between the Python theme palette and assets/dashboard.css."""

from __future__ import annotations

import re

import plotly.graph_objects as go

from bh_itbi import theme
from bh_itbi.config import (
    AGE_CONFIDENCE_LEVEL,
    COMPARISON_MINIMUM,
    COMPARISON_RIDGE_LIMIT,
    RIDGE_MINIMUM,
    ROOT,
)

SHARED_CSS_VARIABLES: dict[str, str] = {
    "--paper": theme.PAPER,
    "--surface": theme.SURFACE,
    "--ink": theme.INK,
    "--ink-2": theme.INK_SOFT,
    "--muted": theme.MUTED,
    "--teal": theme.TEAL,
    "--reference-colour": theme.REFERENCE["color"],
    "--reference-dash": theme.REFERENCE["dash"],
    "--reference-width": f"{theme.REFERENCE['width']}px",
}


def parse_css_root_variables() -> dict[str, str]:
    """Extract custom properties from the ``:root`` block of ``assets/dashboard.css``."""
    css = (ROOT / "assets" / "dashboard.css").read_text(encoding="utf-8")
    match = re.search(r":root\s*\{([^}]*)\}", css, flags=re.DOTALL)
    assert match is not None, "Missing :root block in assets/dashboard.css"
    block = match.group(1)
    return {
        name.strip(): value.strip().lower()
        for name, value in re.findall(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;]+);", block)
    }


def test_python_palette_matches_css_custom_properties() -> None:
    css_vars = parse_css_root_variables()
    mismatches: list[str] = []
    for css_name, python_value in SHARED_CSS_VARIABLES.items():
        css_value = css_vars.get(css_name)
        if css_value != python_value.lower():
            mismatches.append(
                f"{css_name}: CSS has {css_value!r}, Python has {python_value.lower()!r}"
            )
    assert not mismatches, "Theme colour mismatch:\n  " + "\n  ".join(mismatches)


def test_single_named_colour_tokens_and_rgb_mixing() -> None:
    assert not hasattr(theme, "TEAL_TINT")
    assert theme.COMPOSITION_HUES == {
        "neighbourhood": theme.CLAY,
        "area": theme.BLUE,
        "age_band": theme.GOLD,
        "property_type": theme.SLATE,
    }
    assert theme.hex_to_rgb(theme.TEAL) == (29, 111, 115)
    assert theme.composition_tint(theme.SURFACE, strength=0.62) == theme.SURFACE


def test_reference_neighbourhoods_keep_their_colours() -> None:
    expected = {
        "SAVASSI": "#4f8f4a",
        "LOURDES": "#c0603a",
        "BURITIS": "#3e6daa",
        "CASTELO": "#a88620",
        "CENTRO": "#8f579f",
    }
    assert theme.neighbourhood_colours([]) == expected
    for name, colour in expected.items():
        assert theme.neighbourhood_colours([name]) == {name: colour}
    assert theme.neighbourhood_colours(["SION", *reversed(expected)]) == expected | {
        "SION": "#a8326a"
    }


def test_extra_neighbourhood_colours_follow_distinct_names_in_alphabetical_order() -> None:
    colours = theme.neighbourhood_colours(["SION", "UNKNOWN", "SION", "ANCHIETA"])
    assert colours == {"ANCHIETA": "#a8326a", "SION": "#2a9bb5", "UNKNOWN": "#7a4a2a"}
    assert not set(colours.values()) & {theme.TEAL, *theme.neighbourhood_colours([]).values()}


def test_four_extra_neighbourhoods_switch_the_whole_selection_to_slate() -> None:
    names = ["SION", "ANCHIETA", "FUNCIONARIOS", "UNKNOWN", "SAVASSI", "CENTRO", "SION"]
    assert theme.neighbourhood_colours(names) == dict.fromkeys(names, "#8a929a")


def test_browser_chart_cutoffs_match_configuration() -> None:
    expected = {
        "comparison.js": {
            "comparisonMinimum": COMPARISON_MINIMUM,
            "ridgeMinimum": RIDGE_MINIMUM,
            "ridgeLimit": COMPARISON_RIDGE_LIMIT,
        },
        "age-chart.js": {"confidencePercent": round(100 * AGE_CONFIDENCE_LEVEL)},
    }
    for name, settings in expected.items():
        asset = (ROOT / "assets" / name).read_text(encoding="utf-8")
        values = dict(re.findall(r"\bconst (\w+) = (\d+);", asset))
        assert {key: values.get(key) for key in settings} == {
            key: str(value) for key, value in settings.items()
        }, name


def test_themed_configures_shared_interactive_bottom_legend() -> None:
    fig = theme.themed(go.Figure())
    legend = fig.layout.legend
    assert fig.layout.showlegend is True
    assert (legend.orientation, legend.traceorder) == ("h", "normal")
    assert (legend.xref, legend.xanchor, legend.x) == ("container", "left", 0)
    assert (legend.yref, legend.yanchor, legend.y) == ("container", "bottom", 0)
    assert (legend.groupclick, legend.itemclick, legend.itemdoubleclick) == (
        "togglegroup",
        "toggle",
        "toggleothers",
    )
    assert (legend.font.size, legend.font.color, legend.title.text) == (
        11,
        theme.INK_SOFT,
        "",
    )
    assert theme.empty_figure("Sem dados").layout.showlegend is False
    assert not hasattr(theme, "end_label_text")
    assert not hasattr(theme, "reference_label_text")
