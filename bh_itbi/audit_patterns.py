"""Compute audit-only sensitivities for the trajectory patterns."""

from typing import TypedDict

import numpy as np
import pandas as pd

from bh_itbi.config import CLUSTER_N_INIT, PATTERN_ORDER
from bh_itbi.patterns import (
    PatternMetadata,
    PatternSample,
    _independent_pattern_medians,
    fit_pattern_kmeans,
    named_pattern_order,
    pattern_sample,
    trajectory_patterns,
)
from bh_itbi.resampling import _block_face_codes


class PatternAlternative(TypedDict):
    """The lower-restart solution on the same complete-case trajectories."""

    n_init: int
    inertia: float
    sizes: dict[str, int]
    stable_rising_switches: list[str]
    other_switches: list[str]


class IndependentRecordStability(TypedDict):
    """Agreement when transactions are resampled independently."""

    firm: dict[str, int]
    ari_median: float
    ari_p10: float
    ari_p90: float


class AuditPatterns(TypedDict):
    """Pattern estimates and audit-only comparisons and cell diagnostics."""

    metadata: PatternMetadata
    centres: pd.DataFrame
    membership: pd.DataFrame
    independent_records: IndependentRecordStability
    alternative: PatternAlternative
    fewest_block_faces: pd.DataFrame


def _lower_restart_partition(
    sample: PatternSample, membership: pd.DataFrame
) -> PatternAlternative:
    """Compare the deterministic labels with the near-tie from the earlier restart count."""
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


def _fewest_pattern_block_faces(sample: PatternSample) -> pd.DataFrame:
    """List the cells with the fewest resampling units, breaking ties by record count."""
    cells = []
    for cell in sample.cells:
        sizes = np.bincount(_block_face_codes(cell))
        cells.append(
            {
                "neighbourhood": str(cell["neighbourhood"].iat[0]),
                "period": str(cell["period"].iat[0]),
                "records": len(cell),
                "block_faces": len(sizes),
                "largest_face_share": float(sizes.max() / len(cell)),
            }
        )
    return (
        pd.DataFrame(cells)
        .sort_values(
            ["block_faces", "records", "neighbourhood", "period"],
            ascending=[True, False, True, True],
        )
        .head(5)
    )


def audit_trajectory_patterns(frame: pd.DataFrame) -> AuditPatterns:
    """Measure independent and block-face stability on the same fitted partition."""
    members, centres, metadata = trajectory_patterns(frame)
    columns = ["neighbourhood", "pattern", "membership_share", "firm"]
    membership = members.drop_duplicates("neighbourhood")[columns]
    _, _, independent = trajectory_patterns(frame, resample_cell=_independent_pattern_medians)
    sample = pattern_sample(frame)
    return {
        "metadata": metadata,
        "centres": centres,
        "membership": membership,
        "independent_records": {
            "firm": {
                name: summary["firm"] for name, summary in independent["patterns"].items()
            },
            "ari_median": independent["ari_median"],
            "ari_p10": independent["ari_p10"],
            "ari_p90": independent["ari_p90"],
        },
        "alternative": _lower_restart_partition(sample, membership),
        "fewest_block_faces": _fewest_pattern_block_faces(sample),
    }
