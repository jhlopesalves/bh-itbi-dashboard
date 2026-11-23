"""Compute audit-only sensitivities for the trajectory patterns."""

from typing import TypedDict

import numpy as np
import pandas as pd

from bh_itbi.config import CLUSTER_N_INIT, PATTERN_ORDER
from bh_itbi.patterns import (
    PatternMetadata,
    fit_pattern_kmeans,
    named_pattern_order,
    pattern_sample,
    trajectory_patterns,
)
from bh_itbi.resampling import block_face_pattern_medians


class PatternAlternative(TypedDict):
    """The lower-restart solution on the same complete-case trajectories."""

    n_init: int
    inertia: float
    sizes: dict[str, int]
    stable_rising_switches: list[str]
    other_switches: list[str]


class BlockFaceStability(TypedDict):
    """Agreement when approximate block faces are the resampling units."""

    firm: dict[str, int]
    ari_median: float
    ari_p10: float
    ari_p90: float


class AuditPatterns(TypedDict):
    """Pattern estimates and the audit-only block-face and optimisation checks."""

    metadata: PatternMetadata
    centres: pd.DataFrame
    membership: pd.DataFrame
    block_face: BlockFaceStability
    alternative: PatternAlternative


def _lower_restart_partition(
    frame: pd.DataFrame, membership: pd.DataFrame
) -> PatternAlternative:
    """Compare the deterministic labels with the near-tie from the earlier restart count."""
    sample = pattern_sample(frame)
    fitted = fit_pattern_kmeans(sample.shapes, n_init=CLUSTER_N_INIT)
    order = named_pattern_order(fitted.cluster_centers_)
    labels, inertia = fitted.labels_, fitted.inertia_
    assert labels is not None and inertia is not None
    alternative = pd.Series(
        np.asarray(PATTERN_ORDER)[np.argsort(order)[labels]], index=sample.counts.index
    )
    chosen = membership.set_index("neighbourhood")["pattern"].reindex(alternative.index)
    changed = chosen.ne(alternative)
    stable_rising = chosen.ne("falling") & alternative.ne("falling")
    return {
        "n_init": CLUSTER_N_INIT,
        "inertia": float(inertia),
        "sizes": {name: int(alternative.eq(name).sum()) for name in PATTERN_ORDER},
        "stable_rising_switches": sorted(map(str, alternative.index[changed & stable_rising])),
        "other_switches": sorted(map(str, alternative.index[changed & ~stable_rising])),
    }


def audit_trajectory_patterns(frame: pd.DataFrame) -> AuditPatterns:
    """Measure independent and block-face stability on the same fitted partition."""
    members, centres, metadata = trajectory_patterns(frame)
    columns = ["neighbourhood", "pattern", "membership_share", "firm"]
    membership = members.drop_duplicates("neighbourhood")[columns]
    _, _, block_face = trajectory_patterns(frame, resample_cell=block_face_pattern_medians)
    return {
        "metadata": metadata,
        "centres": centres,
        "membership": membership,
        "block_face": {
            "firm": {name: summary["firm"] for name, summary in block_face["patterns"].items()},
            "ari_median": block_face["ari_median"],
            "ari_p10": block_face["ari_p10"],
            "ari_p90": block_face["ari_p90"],
        },
        "alternative": _lower_restart_partition(frame, membership),
    }
