"""Visual palette, typography, colour mixing and base Plotly figure styling."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict

import plotly.graph_objects as go

from bh_itbi.config import DEFAULT_NEIGHBOURHOODS, DISTANCE_PERIODS

# Surface and ink tokens mirrored in assets/dashboard.css :root.
PAPER = "#fafaf8"
SURFACE = "#fdfdfc"
INK = "#22313a"
INK_SOFT = "#24343d"
MUTED = "#667784"
TEAL = "#1d6f73"

# Categorical and chart tokens.
CLAY = "#c0603a"
BLUE = "#3e6daa"
GOLD = "#a88620"
PLUM = "#8f579f"
SLATE = "#8a929a"

GRID = "#e6eae6"
AXIS = "#c9d1cb"
NEUTRAL_BAR = "#d6d0c5"
HOVER_BG = "#ffffff"
MODEBAR_ICON = "#b3ada3"
TRANSPARENT = "rgba(0,0,0,0)"

DISTANCE_AMBER = "#e8a33d"
DISTANCE_ROSE = "#c94f7c"
DISTANCE_PLUM = "#5e2a6e"

FONT = 'Inter, "Segoe UI", "Ubuntu Sans", "Noto Sans", "Helvetica Neue", Arial, sans-serif'


class LineStyle(TypedDict):
    """Stroke attributes used by Plotly lines and shapes."""

    color: str
    dash: str
    width: float


class PropertyStyle(TypedDict):
    """A property type's line and matching marker shape."""

    line: LineStyle
    symbol: str


TYPE_STYLES: dict[str, PropertyStyle] = {
    "apartment": {
        "line": {"color": TEAL, "dash": "solid", "width": 2},
        "symbol": "circle",
    },
    "house": {
        "line": {"color": CLAY, "dash": "solid", "width": 2},
        "symbol": "diamond",
    },
}

FIXED_NEIGHBOURHOOD_COLOURS: dict[str, str] = {
    "SAVASSI": "#4f8f4a",
    "LOURDES": CLAY,
    "BURITIS": BLUE,
    "CASTELO": GOLD,
    "CENTRO": PLUM,
}
EXTRA_NEIGHBOURHOOD_COLOURS = ("#a8326a", "#2a9bb5", "#7a4a2a")

# In draw order, from the earliest period at the back to the latest in front.
DISTANCE_PERIOD_STYLES: dict[str, tuple[str, float, float]] = dict(
    zip(
        DISTANCE_PERIODS,
        (
            (DISTANCE_AMBER, 1.6, 3.0),
            (DISTANCE_ROSE, 2.0, 3.5),
            (DISTANCE_PLUM, 2.8, 4.0),
        ),
        strict=True,
    )
)
# Distinct hues for the four observed hedonic composition terms.
COMPOSITION_HUES: dict[str, str] = {
    "neighbourhood": CLAY,
    "area": BLUE,
    "age_band": GOLD,
    "property_type": SLATE,
}


def hex_to_rgb(colour: str) -> tuple[int, int, int]:
    """Convert a ``#rrggbb`` hex token into its integer RGB channels."""
    red, green, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return red, green, blue


def rgba(colour: str, opacity: float) -> str:
    """Apply opacity to a hex colour for Plotly and CSS."""
    red, green, blue = hex_to_rgb(colour)
    return f"rgba({red},{green},{blue},{opacity})"


REFERENCE: LineStyle = {"color": rgba(INK, 0.45), "dash": "4px,3px", "width": 0.9}


def neighbourhood_colours(names: Sequence[str]) -> dict[str, str]:
    """Assign hues to distinct source names, using slate when the extra hues run out."""
    selected = dict.fromkeys(names or DEFAULT_NEIGHBOURHOODS)
    extras = sorted(selected.keys() - FIXED_NEIGHBOURHOOD_COLOURS.keys())
    if len(extras) > len(EXTRA_NEIGHBOURHOOD_COLOURS):
        return dict.fromkeys(selected, SLATE)
    extra_colours = dict(zip(extras, EXTRA_NEIGHBOURHOOD_COLOURS[: len(extras)], strict=True))
    colours = FIXED_NEIGHBOURHOOD_COLOURS | extra_colours
    return {name: colours[name] for name in selected}


def composition_tint(hue: str, *, strength: float = 0.62) -> str:
    """Blend a chart hue with the card surface colour in RGB space."""
    channels = (
        round(strength * fg + (1 - strength) * bg)
        for fg, bg in zip(hex_to_rgb(hue), hex_to_rgb(SURFACE), strict=True)
    )
    return "#" + "".join(f"{value:02x}" for value in channels)


AGE_FILLS: dict[str, str] = {
    group: composition_tint(hue, strength=0.75)
    for group, hue in {
        "neighbourhood": COMPOSITION_HUES["neighbourhood"],
        "area": COMPOSITION_HUES["area"],
        "quarter": SLATE,
    }.items()
}


def themed(fig: go.Figure, *, height: int = 360) -> go.Figure:
    """Apply the publication theme; HTML owns chart titles and explanatory copy."""
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=TRANSPARENT,
        plot_bgcolor=TRANSPARENT,
        font={"family": FONT, "size": 12, "color": INK},
        separators=",.",
        colorway=[INK],
        height=height,
        margin={"l": 65, "r": 22, "t": 18, "b": 8},
        showlegend=True,
        legend={
            "orientation": "h",
            "xref": "container",
            "yref": "container",
            "x": 0,
            "xanchor": "left",
            "y": 0,
            "yanchor": "bottom",
            "traceorder": "normal",
            "groupclick": "togglegroup",
            "itemclick": "toggle",
            "itemdoubleclick": "toggleothers",
            "font": {"size": 11, "color": INK_SOFT},
            "title": {"text": ""},
        },
        hoverlabel={
            "bgcolor": HOVER_BG,
            "bordercolor": AXIS,
            "font": {"family": FONT, "color": INK, "size": 12},
            "align": "left",
        },
        hovermode="closest",
        modebar={
            "orientation": "h",
            "bgcolor": TRANSPARENT,
            "color": MODEBAR_ICON,
            "activecolor": TEAL,
        },
    )
    axis = {
        "zeroline": False,
        "automargin": True,
        "tickfont": {"size": 11, "color": MUTED},
        "title_font": {"size": 11, "color": INK_SOFT},
    }
    fig.update_xaxes(
        showgrid=False,
        showline=True,
        linecolor=AXIS,
        linewidth=1,
        ticks="outside",
        ticklen=4,
        tickcolor=AXIS,
        **axis,
    )
    fig.update_yaxes(gridcolor=GRID, gridwidth=1, tickformat=",.0f", **axis)
    return fig


def empty_figure(message: str, height: int = 360) -> go.Figure:
    """Return a themed blank figure displaying a centred empty-state message."""
    fig = themed(go.Figure(), height=height)
    fig.update_layout(showlegend=False)
    fig.add_annotation(
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        text=message,
        showarrow=False,
        font={"size": 13, "color": MUTED},
        align="center",
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig
