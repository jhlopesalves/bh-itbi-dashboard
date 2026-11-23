"""Measure neighbourhood colour separation and contrast on the chart surface."""

from itertools import combinations, product
from math import dist

from bh_itbi.theme import (
    BLUE,
    CLAY,
    EXTRA_NEIGHBOURHOOD_COLOUR,
    FIXED_NEIGHBOURHOOD_COLOURS,
    GOLD,
    SLATE,
    SURFACE,
    TEAL,
    hex_to_rgb,
)


def linear_srgb(colour: str) -> tuple[float, float, float]:
    channels = (value / 255 for value in hex_to_rgb(colour))
    red, green, blue = (
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    )
    return red, green, blue


def cielab_d65(colour: str) -> tuple[float, float, float]:
    r, g, b = linear_srgb(colour)
    xyz = (
        (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047,
        0.2126729 * r + 0.7151522 * g + 0.0721750 * b,
        (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883,
    )
    delta = 6 / 29
    x, y, z = (v ** (1 / 3) if v > delta**3 else v / (3 * delta**2) + 4 / 29 for v in xyz)
    return 116 * y - 16, 500 * (x - y), 200 * (y - z)


def relative_luminance(colour: str) -> float:
    r, g, b = linear_srgb(colour)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_fixed_neighbourhood_colours_have_distinct_hues() -> None:
    colours = FIXED_NEIGHBOURHOOD_COLOURS.values()
    for first, second in combinations(colours, 2):
        separation = dist(cielab_d65(first), cielab_d65(second))
        assert separation >= 40, (first, second, separation)
    for first, second in product(colours, (TEAL, CLAY, BLUE, GOLD)):
        separation = dist(cielab_d65(first), cielab_d65(second))
        assert separation >= 20, (first, second, separation)


def test_neighbourhood_palette_has_adequate_contrast() -> None:
    colours = (*FIXED_NEIGHBOURHOOD_COLOURS.values(), EXTRA_NEIGHBOURHOOD_COLOUR, SLATE)
    for colour in colours:
        dark, light = sorted((relative_luminance(colour), relative_luminance(SURFACE)))
        ratio = (light + 0.05) / (dark + 0.05)
        assert ratio >= 3, (colour, ratio)
