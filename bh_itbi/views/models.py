"""Pure view-model assembly for the models tab."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from bh_itbi.models import PreparedModels
from bh_itbi.text.models import (
    cluster_group_heading,
)


@dataclass(frozen=True)
class ClusterGroupView:
    """Formatted heading and comma-separated member list for one trajectory cluster."""

    heading: str
    members_text: str


@dataclass(frozen=True)
class ModelsView:
    """Selected group identifier and member lists for the models tab."""

    group_id: int | None
    groups: tuple[ClusterGroupView, ...]


def build_models_view(models: PreparedModels, group: str) -> ModelsView:
    """Filter and format trajectory cluster members for the selected group option."""
    group_id = None if group == "all" else int(group)
    members = models.members.drop_duplicates(["neighbourhood", "group"])
    if group_id:
        members = members.loc[members["group"].eq(group_id)]
    groups = tuple(
        ClusterGroupView(
            heading=cluster_group_heading(int(cast(int, identifier)), len(rows)),
            members_text=", ".join(sorted(rows["neighbourhood"].astype(str).str.title())),
        )
        for identifier, rows in members.groupby("group", sort=True)
    )
    return ModelsView(group_id=group_id, groups=groups)
