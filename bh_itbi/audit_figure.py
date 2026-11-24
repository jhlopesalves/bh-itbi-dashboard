"""Draw the audit's index comparison as a small, dependency-free SVG."""

from collections.abc import Sequence
from dataclasses import dataclass
from html import escape

import numpy as np
import pandas as pd

from bh_itbi.config import INDEX_BASE

WIDTH, HEIGHT = 760, 360
LEFT, RIGHT, TOP, BOTTOM = 40, 196, 14, 34
LABEL_GAP = 14
FONT = "font-family='system-ui, -apple-system, Segoe UI, sans-serif' font-size='12'"


@dataclass(frozen=True)
class IndexSeries:
    """One specification drawn in the comparison figure."""

    spec_id: str
    label: str
    colour: str
    dash: str = ""


@dataclass(frozen=True)
class _Scale:
    quarters: tuple[str, ...]
    low: float
    high: float

    def x(self, position: int) -> float:
        span = WIDTH - LEFT - RIGHT
        return LEFT + span * position / (len(self.quarters) - 1)

    def y(self, value: float) -> float:
        span = HEIGHT - TOP - BOTTOM
        return TOP + span * (self.high - value) / (self.high - self.low)


def _points(scale: _Scale, values: Sequence[float]) -> str:
    return " ".join(f"{scale.x(i):.1f},{scale.y(value):.1f}" for i, value in enumerate(values))


def _axes(scale: _Scale) -> list[str]:
    parts: list[str] = []
    for tick in range(int(np.ceil(scale.low / 10) * 10), int(scale.high) + 1, 10):
        y = scale.y(tick)
        stroke = "#9a9a9a' stroke-dasharray='3 3" if tick == INDEX_BASE else "#e3e3e3"
        parts.append(
            f"<line x1='{LEFT}' x2='{WIDTH - RIGHT}' y1='{y:.1f}' y2='{y:.1f}' "
            f"stroke='{stroke}'/>"
            f"<text x='{LEFT - 6}' y='{y + 4:.1f}' text-anchor='end' fill='#666'>{tick}</text>"
        )
    for i, quarter in enumerate(scale.quarters):
        year = int(quarter[:4])
        if quarter.endswith("Q1") and year % 2 == 0:
            parts.append(
                f"<text x='{scale.x(i):.1f}' y='{HEIGHT - BOTTOM + 18}' text-anchor='middle' "
                f"fill='#666'>{year}</text>"
            )
    return parts


def _label_positions(targets: Sequence[float]) -> list[float]:
    """Spread end labels vertically so that none overlap, keeping their order."""
    order = np.argsort(targets)
    placed = np.asarray(targets, dtype=float)[order]
    for i in range(1, len(placed)):
        placed[i] = max(placed[i], placed[i - 1] + LABEL_GAP)
    positions = np.empty_like(placed)
    positions[order] = placed
    return positions.tolist()


def index_comparison_svg(index: pd.DataFrame, series: Sequence[IndexSeries]) -> str:
    """Plot selected specification indices with the first series' 95% interval."""
    wide = index.pivot(index="quarter", columns="spec_id", values="index")
    base = index.loc[index["spec_id"].eq(series[0].spec_id)].set_index("quarter")
    shown = wide[[item.spec_id for item in series]]
    low = float(min(shown.min().min(), base["lower"].min()))
    high = float(max(shown.max().max(), base["upper"].max()))
    scale = _Scale(tuple(wide.index.astype(str)), np.floor(low / 5) * 5, np.ceil(high / 5) * 5)
    band = (
        _points(scale, base["upper"].tolist())
        + " "
        + " ".join(reversed(_points(scale, base["lower"].tolist()).split()))
    )
    parts = [
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {WIDTH} {HEIGHT}' {FONT}>",
        f"<rect width='{WIDTH}' height='{HEIGHT}' fill='#ffffff'/>",
        *_axes(scale),
        f"<polygon points='{band}' fill='{series[0].colour}' fill-opacity='0.14'/>",
    ]
    ends = [float(shown[item.spec_id].iloc[-1]) for item in series]
    labels = _label_positions([scale.y(end) for end in ends])
    for item, end, label_y in zip(
        reversed(series), reversed(ends), reversed(labels), strict=True
    ):
        width = 2.4 if item is series[0] else 1.6
        dash = f" stroke-dasharray='{item.dash}'" if item.dash else ""
        parts.append(
            f"<polyline points='{_points(scale, shown[item.spec_id].tolist())}' fill='none' "
            f"stroke='{item.colour}' stroke-width='{width}'{dash}/>"
            f"<text x='{WIDTH - RIGHT + 8}' y='{label_y + 4:.1f}' fill='{item.colour}'>"
            f"{escape(item.label)}: {end:.1f}</text>"
        )
    return "\n".join([*parts, "</svg>"]) + "\n"
