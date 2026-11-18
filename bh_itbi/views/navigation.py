"""Pure view-model assembly for dashboard tab navigation."""

from dataclasses import dataclass

from bh_itbi.text.shared import FILTER_NOTE_ACTIVE, FILTER_NOTE_MODELS, TAB_LABELS


@dataclass(frozen=True)
class TabView:
    """Panel visibility, filter-disable state and ARIA attributes for tab switching."""

    panel_classes: dict[str, str]
    filter_note: str
    filters_disabled: bool
    tab_classes: dict[str, str]
    tab_selected: dict[str, str]
    tab_indexes: dict[str, int]


def build_tab_view(tab: str) -> TabView:
    """Compute CSS classes, ARIA attributes and filter state for the active tab."""
    names = tuple(name for name, _ in TAB_LABELS)
    fixed = tab == "models"
    return TabView(
        panel_classes={
            name: "view-panel" if tab == name else "view-panel is-hidden" for name in names
        },
        filter_note=FILTER_NOTE_MODELS if fixed else FILTER_NOTE_ACTIVE,
        filters_disabled=fixed,
        tab_classes={
            name: "view-tab view-tab-selected" if tab == name else "view-tab" for name in names
        },
        tab_selected={name: "true" if tab == name else "false" for name in names},
        tab_indexes={name: 0 if tab == name else -1 for name in names},
    )
