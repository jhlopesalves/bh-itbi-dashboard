"""Assemble the firm and borderline member lists shown under the pattern plots."""

import pandas as pd


def pattern_member_names(members: pd.DataFrame, pattern: str) -> tuple[list[str], list[str]]:
    """Return alphabetical display names for both membership groups in one pattern."""
    selected = members.loc[members["pattern"].eq(pattern)].drop_duplicates("neighbourhood")
    firm = selected.loc[selected["firm"], "neighbourhood"].str.title().sort_values()
    borderline = selected.loc[~selected["firm"], "neighbourhood"].str.title().sort_values()
    return firm.tolist(), borderline.tolist()
