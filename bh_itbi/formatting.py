"""Brazilian Portuguese number, currency, log-point and calendar display formatters."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

MONTHS = (
    "jan",
    "fev",
    "mar",
    "abr",
    "mai",
    "jun",
    "jul",
    "ago",
    "set",
    "out",
    "nov",
    "dez",
)
_PT_BR_SEPARATORS = str.maketrans(",.", ".,")


def number(value: float, decimals: int = 0) -> str:
    """Format only the display value; calculations retain unrounded precision."""
    if pd.isna(value) or not np.isfinite(value):
        return "—"
    return f"{value:,.{decimals}f}".translate(_PT_BR_SEPARATORS)


def composition_number(value: float) -> str:
    """Display signed log × 100, keeping small non-zero values legible."""
    scaled = value * 100
    decimals = 4 if 0 < abs(scaled) < 0.05 else 1
    magnitude = number(abs(scaled), decimals)
    if decimals == 4:
        magnitude = magnitude.rstrip("0").rstrip(",")
    sign = "−" if scaled < 0 else "+" if scaled > 0 else ""
    return sign + magnitude


def currency(value: float) -> str:
    """Format a nominal or real BRL amount with a non-breaking en-dash fallback."""
    return "—" if pd.isna(value) else f"R$ {number(value)}"


def month_label(value: pd.Timestamp | date | str) -> str:
    """Format a timestamp as ``mmm/YYYY`` in lowercase Portuguese."""
    timestamp = pd.Timestamp(value)
    return f"{MONTHS[timestamp.month - 1]}/{timestamp.year}"


def quarter_label(value: pd.Timestamp | date | str) -> str:
    """Format a timestamp as ``Qº tri. YYYY`` in Portuguese."""
    timestamp = pd.Timestamp(value)
    return f"{timestamp.quarter}º tri. {timestamp.year}"


def age_percent(points: float, decimals: int = 0) -> str:
    """Display a log difference as a signed relative change in geometric means."""
    percent = float(np.expm1(points) * 100)
    sign = ""
    if round(percent, decimals):
        sign = "−" if percent < 0 else "+"
    return f"{sign}{number(abs(percent), decimals)}%"
