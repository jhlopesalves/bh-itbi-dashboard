"""Resample transaction medians by approximate block face."""

import numpy as np
import pandas as pd
from numpy.typing import NDArray


def _block_face_codes(rows: pd.DataFrame) -> NDArray[np.intp]:
    geocoded = rows["face_geocoded"].to_numpy(dtype=bool)
    coordinates = rows[["lat", "lon"]].to_numpy(dtype=float)[geocoded].round(7)
    _, faces = np.unique(coordinates, axis=0, return_inverse=True)
    # Negative labels keep records without a matched face in distinct clusters.
    codes = -1 - np.arange(len(rows), dtype=np.intp)
    codes[geocoded] = faces
    return np.unique(codes, return_inverse=True)[1]


def _block_face_medians(
    values: NDArray[np.float64],
    codes: NDArray[np.intp],
    rng: np.random.Generator,
    draws: int,
) -> NDArray[np.float64]:
    n_clusters = int(codes.max()) + 1
    # Multinomial counts encode the multiplicities of the sampled block faces.
    frequencies = rng.multinomial(n_clusters, np.full(n_clusters, 1 / n_clusters), size=draws)
    order = np.argsort(values)
    cumulative = np.cumsum(frequencies[:, codes[order]], axis=1)
    total = cumulative[:, -1:]
    left = (cumulative <= (total - 1) // 2).sum(axis=1)
    right = (cumulative <= total // 2).sum(axis=1)
    return (values[order[left]] + values[order[right]]) / 2


def block_face_pattern_medians(
    cell: pd.DataFrame, rng: np.random.Generator, draws: int
) -> NDArray[np.float64]:
    """Resample adjusted prices by approximate block face within one pattern cell."""
    return _block_face_medians(
        cell["adjusted_log_price"].to_numpy(dtype=float), _block_face_codes(cell), rng, draws
    )
