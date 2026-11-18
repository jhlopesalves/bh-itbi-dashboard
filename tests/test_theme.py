"""Consistency checks between the Python theme palette and assets/dashboard.css."""

from __future__ import annotations

import re

from bh_itbi import theme
from bh_itbi.config import ROOT

SHARED_CSS_VARIABLES: dict[str, str] = {
    "--paper": theme.PAPER,
    "--paper-2": theme.PAPER_SOFT,
    "--surface": theme.SURFACE,
    "--ink": theme.INK,
    "--ink-2": theme.INK_SOFT,
    "--muted": theme.MUTED,
    "--teal": theme.TEAL,
    "--teal-2": theme.TEAL_SOFT,
    "--rule": theme.RULE,
    "--rule-cool": theme.RULE_COOL,
    "--rule-faint": theme.RULE_FAINT,
    "--rule-interactive": theme.RULE_INTERACTIVE,
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
        "Bairro": theme.CLAY,
        "Área": theme.BLUE,
        "Faixa de idade": theme.GOLD,
        "Tipo": theme.SLATE,
    }
    assert theme.hex_to_rgb(theme.TEAL) == (29, 111, 115)
    assert theme.composition_tint(theme.SURFACE, strength=0.62) == theme.SURFACE
