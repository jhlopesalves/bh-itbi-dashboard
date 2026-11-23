"""Pure analytical view-model builders that assemble data and copy for callbacks."""

from bh_itbi.views.diagnostics import (
    DiagnosticsView,
    build_diagnostics_view,
)
from bh_itbi.views.models import pattern_member_names
from bh_itbi.views.navigation import TabView, build_tab_view
from bh_itbi.views.overview import (
    OverviewView,
    build_overview_view,
    clicked_neighbourhood,
)

__all__ = [
    "DiagnosticsView",
    "OverviewView",
    "TabView",
    "build_diagnostics_view",
    "build_overview_view",
    "build_tab_view",
    "clicked_neighbourhood",
    "pattern_member_names",
]
