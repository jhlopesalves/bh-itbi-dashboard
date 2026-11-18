"""Visual palette, typography, colour mixing and base Plotly figure styling."""

from __future__ import annotations

import plotly.graph_objects as go

from bh_itbi.config import DEFAULT_NEIGHBOURHOODS, DISTANCE_PERIODS

# Surface and ink tokens mirrored in assets/dashboard.css :root.
PAPER = "#fafaf8"
PAPER_SOFT = "#f0f0ee"
SURFACE = "#fdfdfc"
INK = "#22313a"
INK_SOFT = "#24343d"
MUTED = "#667784"
TEAL = "#1d6f73"
TEAL_SOFT = "#2a7a7b"
RULE = "#d5dbd6"
RULE_COOL = "#d8dcd6"
RULE_FAINT = "#e3e8e4"
RULE_INTERACTIVE = "#9eaba3"

# Categorical and chart tokens.
CLAY = "#c0603a"
BLUE = "#3e6daa"
GOLD = "#a88620"
PLUM = "#8f579f"
GREEN = "#5f8f3a"
ROSE = "#b85079"
INDIGO = "#5b78c0"
SLATE = "#8a929a"

GRID = "#e6eae6"
AXIS = "#c9d1cb"
NEUTRAL_BAR = "#d6d0c5"
HOVER_BG = "#ffffff"
MODEBAR_ICON = "#b3ada3"

CLUSTER_VIOLET = "#6c4fae"
CLUSTER_FOREST = "#3d7f4a"
CLUSTER_ROSE = "#d77a9a"
CLUSTER_AMBER = "#e09a3e"

DISTANCE_AMBER = "#e8a33d"
DISTANCE_ROSE = "#c94f7c"
DISTANCE_PLUM = "#5e2a6e"

PRICE_NAVY = "#00007f"
PRICE_BLUE = "#0000ff"
PRICE_CYAN = "#00ffff"
PRICE_YELLOW = "#ffff00"
PRICE_RED = "#ff0000"
PRICE_MAROON = "#7f0000"

FONT = 'Inter, "Segoe UI", "Ubuntu Sans", "Noto Sans", "Helvetica Neue", Arial, sans-serif'
SERIF_FONT = (
    '"Source Serif 4", "Iowan Old Style", Charter, "Noto Serif", '
    '"Palatino Linotype", Georgia, serif'
)

TYPE_COLORS: dict[str, str] = {"apartment": TEAL, "house": CLAY}
PALETTE: list[str] = [TEAL, CLAY, BLUE, GOLD, PLUM, GREEN, ROSE, INDIGO]
CLUSTER_COLORS: dict[int, str] = {
    1: CLUSTER_VIOLET,
    2: CLUSTER_FOREST,
    3: CLUSTER_ROSE,
    4: CLUSTER_AMBER,
}
# Matplotlib's "jet", as in Géron's California housing map (translucent,
# size-encoded circles coloured by price).
PRICE_SCALE: list[list[float | str]] = [
    [0.0, PRICE_NAVY],
    [0.125, PRICE_BLUE],
    [0.375, PRICE_CYAN],
    [0.625, PRICE_YELLOW],
    [0.875, PRICE_RED],
    [1.0, PRICE_MAROON],
]
NEIGHBOURHOOD_COLORS: dict[str, str] = dict(zip(DEFAULT_NEIGHBOURHOODS, PALETTE, strict=False))
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
    "Bairro": CLAY,
    "Área": BLUE,
    "Faixa de idade": GOLD,
    "Tipo": SLATE,
}


def hex_to_rgb(colour: str) -> tuple[int, int, int]:
    """Convert a ``#rrggbb`` hex token into its integer RGB channels."""
    red, green, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return red, green, blue


def composition_tint(hue: str, *, strength: float = 0.62) -> str:
    """Blend a composition hue with the card surface colour in RGB space."""
    channels = (
        round(strength * fg + (1 - strength) * bg)
        for fg, bg in zip(hex_to_rgb(hue), hex_to_rgb(SURFACE), strict=True)
    )
    return "#" + "".join(f"{value:02x}" for value in channels)


AGE_FILLS: dict[str, str] = {
    group: composition_tint(hue, strength=0.75)
    for group, hue in {
        "Bairro": COMPOSITION_HUES["Bairro"],
        "Área": COMPOSITION_HUES["Área"],
        "Trimestre": SLATE,
    }.items()
}


def themed(fig: go.Figure, *, height: int = 360) -> go.Figure:
    """Apply the publication theme; HTML owns chart titles and explanatory copy."""
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": FONT, "size": 12, "color": INK},
        separators=",.",
        colorway=PALETTE,
        height=height,
        margin={"l": 65, "r": 22, "t": 18, "b": 8},
        legend={
            "orientation": "h",
            "xref": "container",
            "yref": "container",
            "x": 0,
            "y": 0,
            "yanchor": "bottom",
            "traceorder": "normal",
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
            "bgcolor": "rgba(0,0,0,0)",
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


def empty_figure(
    message: str = "Sem transações elegíveis neste recorte.", height: int = 360
) -> go.Figure:
    """Return a themed blank figure displaying a centred empty-state message."""
    fig = themed(go.Figure(), height=height)
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
