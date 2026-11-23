"""Aggregate observed neighbourhood trajectories for the models tab."""

import pandas as pd


def trajectory_median(members: pd.DataFrame) -> pd.DataFrame:
    """Compute the pointwise median index across the neighbourhoods present."""
    return members.groupby("year", as_index=False, sort=True)[["index"]].median()
