"""Brazilian Portuguese number, currency, log-point and calendar display formatters."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from bh_itbi.config import SMALL_COMPOSITION_LOG_POINTS

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
_THOUSAND = 1_000
_MILLION = 1_000_000
_SMALL_COUNTS = {
    4: "quatro",
    5: "cinco",
    7: "sete",
    10: "dez",
}


def number(value: float, decimals: int = 0) -> str:
    """Format only the display value; calculations retain unrounded precision."""
    if pd.isna(value) or not np.isfinite(value):
        return "—"
    return f"{value:,.{decimals}f}".translate(_PT_BR_SEPARATORS)


def composition_number(value: float) -> str:
    """Display signed log × 100, keeping small non-zero values legible."""
    scaled = value * 100
    precise = 0 < abs(scaled) < SMALL_COMPOSITION_LOG_POINTS
    decimals = 4 if precise else 1
    magnitude = number(abs(scaled), decimals)
    if precise:
        magnitude = magnitude.rstrip("0").rstrip(",")
    sign = "−" if scaled < 0 else "+" if scaled > 0 else ""
    return sign + magnitude


def currency(value: float) -> str:
    """Format a nominal or real BRL amount, using an em dash for missing values."""
    return "—" if pd.isna(value) else f"R$ {number(value)}"


def compact_number(value: float) -> str:
    """Abbreviate large values in thousands or millions for axis ticks."""
    if value >= _MILLION:
        return f"{number(value / _MILLION)} mi"
    if value >= _THOUSAND:
        return f"{number(value / _THOUSAND)} mil"
    return number(value)


def number_word(value: int) -> str:
    """Spell out the small fixed counts used in prose."""
    return _SMALL_COUNTS.get(value, number(value))


def scaled_currency(value: int) -> str:
    """Render whole thousands and millions in prose without abbreviating units."""
    if value == _MILLION:
        return "R$ 1 milhão"
    if value >= _MILLION and value % _MILLION == 0:
        return f"R$ {number(value // _MILLION)} milhões"
    if value >= _THOUSAND and value % _THOUSAND == 0:
        return f"R$ {number(value // _THOUSAND)} mil"
    return currency(value)


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
