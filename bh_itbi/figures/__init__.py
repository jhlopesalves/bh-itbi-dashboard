"""Plotly figure builders and custom SVG payload constructors grouped by dashboard tab."""

from bh_itbi.figures.diagnostics import (
    AgeChart,
    AgeChartRow,
    AgeSegment,
    age_chart_data,
    age_segments,
    distance_figure,
    heaping_figure,
    tax_base_figure,
)
from bh_itbi.figures.distribution import distribution_figure
from bh_itbi.figures.models import (
    band_traces,
    hedonic_figure,
    pattern_figures,
    ribbon_grid,
)
from bh_itbi.figures.overview import (
    ComparisonPlot,
    ComparisonRow,
    map_figure,
    neighbourhood_comparison_data,
    neighbourhood_trajectories_figure,
    temporal_figure,
)
from bh_itbi.text.overview import (
    DISTRIBUTION_LABELS,
)

__all__ = [
    "DISTRIBUTION_LABELS",
    "AgeChart",
    "AgeChartRow",
    "AgeSegment",
    "ComparisonPlot",
    "ComparisonRow",
    "age_chart_data",
    "age_segments",
    "band_traces",
    "distance_figure",
    "distribution_figure",
    "heaping_figure",
    "hedonic_figure",
    "map_figure",
    "neighbourhood_comparison_data",
    "neighbourhood_trajectories_figure",
    "pattern_figures",
    "ribbon_grid",
    "tax_base_figure",
    "temporal_figure",
]
