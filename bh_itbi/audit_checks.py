"""Compute the audit's descriptive diagnostics and quarterly median bootstraps."""

from __future__ import annotations

from typing import TypedDict

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from bh_itbi.config import (
    AUDIT_LOW_PRICE,
    DEFAULT_NEIGHBOURHOODS,
    END_YEAR,
    HEAPING_BIN_WIDTH,
    HEAPING_MAX_VALUE,
    HEAPING_MIN_VALUE,
    HEAPING_ROUND_MULTIPLE,
    HEAPING_YEARS,
    NEIGHBOURHOOD_QUARTER_MINIMUM,
    START_YEAR,
)
from bh_itbi.diagnostics import heaping_summary, heaping_table
from bh_itbi.filters import positive_area_rows
from bh_itbi.robust import RobustFit, mad_scale

PRICE_QUANTILES = (0.001, 0.01, 0.02, 0.5, 0.98, 0.99, 0.999)
FRACTION_DENOMINATORS = (2, 3, 4, 5, 6, 8, 10)
FRACTION_HALF_WIDTH = 0.003
FRACTION_OFFSET = 0.012
TAX_RATIO_FLOOR = 0.5
RATIO_NEAR_ONE = 0.999
UPPER_TAIL_PRICE = 30_000
MEDIAN_QUANTILES = (0.025, 0.975)


class PriceTails(TypedDict):
    """Real price quantiles and annual shares of eligible records in each tail."""

    eligible_n: int
    quantiles: pd.DataFrame
    by_year: pd.DataFrame


class AdjacentQuarterNoise(TypedDict):
    """Descriptive comparison of clustered sampling variance with observed variance."""

    n_changes: int
    mean_sampling_variance: float
    observed_variance: float
    descriptive_ratio: float | None
    lag1_autocorrelation: float
    white_noise_reference: float


class TaxBaseDiagnostics(TypedDict):
    """Declared and tax-base value comparisons where the tax base is positive."""

    n: int
    declared_above_base: int
    annual: pd.DataFrame
    quarterly: pd.DataFrame


class RoundNumbers(TypedDict):
    """Concentration at and near round declared values."""

    n: int
    exact_10000_share: float
    exact_50000_share: float
    ratio_to_one_fifth_share: float | None
    bin_widths: pd.DataFrame


class QuarterlyUncertainty(TypedDict):
    """Bootstrap intervals and housing mix at neighbourhood and quarter granularity."""

    quarters: pd.DataFrame
    neighbourhoods: pd.DataFrame


def audit_window(frame: pd.DataFrame) -> pd.DataFrame:
    """Select eligible records with positive area in the fixed audit window."""
    return positive_area_rows(frame.loc[frame["year"].between(START_YEAR, END_YEAR)])


def price_tails(window: pd.DataFrame) -> PriceTails:
    """Describe the real-price quantiles and annual tail shares."""
    price = window["price_per_m2_brl_real"]
    flags = pd.DataFrame(
        {
            "year": window["year"],
            "share_below_1000": price.lt(AUDIT_LOW_PRICE),
            "share_above_30000": price.gt(UPPER_TAIL_PRICE),
        }
    )
    quantiles = price.quantile(list(PRICE_QUANTILES))
    return {
        "eligible_n": len(window),
        "quantiles": quantiles.rename_axis("probability").reset_index(name="price_real"),
        "by_year": flags.groupby("year", as_index=False).mean(),
    }


def _declared_base_ratio(window: pd.DataFrame) -> pd.Series:
    """Compute the declared/base ratio where a positive denominator is observed."""
    return window["value_declared_brl"] / window["value_tax_base_brl"].where(
        window["value_tax_base_brl"].gt(0)
    )


def low_tail_profile(window: pd.DataFrame) -> pd.DataFrame:
    """Describe each side of the real-price split without changing eligibility."""
    price = window["price_per_m2_brl_real"]
    ratio = _declared_base_ratio(window)
    metrics = pd.DataFrame(
        {
            "price_group": np.where(
                price.lt(AUDIT_LOW_PRICE), "below_1000", "at_or_above_1000"
            ),
            "house": window["property_type"].eq("house"),
            "area": window["built_area_m2"],
            "declared": window["value_declared_brl"],
            "ratio": ratio,
            "ratio_below_half": ratio.lt(TAX_RATIO_FLOOR).where(ratio.notna()),
            "real_base_per_m2": (
                window["value_tax_base_brl"]
                / window["built_area_m2"]
                * (price / window["price_per_m2_brl"])
            ),
        }
    )
    return metrics.groupby("price_group", as_index=False).agg(
        n=("house", "size"),
        share_houses=("house", "mean"),
        median_area=("area", "median"),
        median_declared=("declared", "median"),
        median_declared_base=("ratio", "median"),
        share_ratio_below_half=("ratio_below_half", "mean"),
        median_real_base_per_m2=("real_base_per_m2", "median"),
    )


def low_tail_fractions(window: pd.DataFrame) -> pd.DataFrame:
    """Compare counts at simple fractions with equal-width neighbouring windows."""
    low = window["price_per_m2_brl_real"].lt(AUDIT_LOW_PRICE)
    ratios = _declared_base_ratio(window.loc[low])
    rows: list[dict[str, object]] = []
    for denominator in FRACTION_DENOMINATORS:
        centre = 1 / denominator
        counts = [
            int(ratios.sub(centre + offset).abs().le(FRACTION_HALF_WIDTH).sum())
            for offset in (-FRACTION_OFFSET, 0.0, FRACTION_OFFSET)
        ]
        rows.append(
            {
                "fraction": f"1/{denominator}",
                "at_fraction": counts[1],
                "mean_beside": (counts[0] + counts[2]) / 2,
            }
        )
    return pd.DataFrame(rows)


def ratio_screen_reach(window: pd.DataFrame) -> pd.DataFrame:
    """Describe the time-varying reach and price composition of the ratio screen."""
    ratio = _declared_base_ratio(window)
    low = window["price_per_m2_brl_real"].lt(AUDIT_LOW_PRICE)
    flagged = ratio.lt(TAX_RATIO_FLOOR)
    low_ratios = ratio.where(low)
    return (
        pd.DataFrame(
            {
                "year": window["year"],
                "low_ratio": low_ratios,
                "low_ratio_near_one": low_ratios.ge(RATIO_NEAR_ONE).where(low_ratios.notna()),
                "flagged": flagged.where(ratio.notna()),
                "at_or_above_1000_if_flagged": (~low).where(flagged),
            }
        )
        .groupby("year", as_index=False)
        .agg(
            low_tail_median_ratio=("low_ratio", "median"),
            low_tail_share_ratio_ge_0999=("low_ratio_near_one", "mean"),
            share_ratio_below_half=("flagged", "mean"),
            share_flags_at_or_above_1000=("at_or_above_1000_if_flagged", "mean"),
        )
    )


def residual_dispersion(
    population: pd.DataFrame, residuals: NDArray[np.float64]
) -> pd.DataFrame:
    """Compare baseline residual MAD scales with and without low-tail records."""
    records = pd.DataFrame(
        {
            "year": population["year"].to_numpy(),
            "all_records": residuals,
            "excluding_low_tail": np.where(
                population["price_per_m2_brl_real"].ge(AUDIT_LOW_PRICE), residuals, np.nan
            ),
        }
    )
    return records.groupby("year", as_index=False).agg(
        lambda values: mad_scale(values.dropna().to_numpy(dtype=float))
    )


def adjacent_quarter_noise(
    tau: NDArray[np.float64], covariance: NDArray[np.float64]
) -> AdjacentQuarterNoise:
    """Compare adjacent log changes with their marginal sampling variances."""
    changes = np.diff(tau)
    variances = covariance.diagonal()
    sampling = float(np.mean(variances[1:] + variances[:-1] - 2 * covariance.diagonal(1)))
    observed = float(changes.var(ddof=1))
    return {
        "n_changes": len(changes),
        "mean_sampling_variance": sampling,
        "observed_variance": observed,
        "descriptive_ratio": sampling / observed if observed > 0 else None,
        "lag1_autocorrelation": float(pd.Series(changes).autocorr(lag=1)),
        "white_noise_reference": float(1 / np.sqrt(len(changes))),
    }


def huber_weight_profiles(population: pd.DataFrame, fits: dict[str, RobustFit]) -> pd.DataFrame:
    """Summarise Huber weights and contributions to the deficit in year-type cells."""
    years = population["year"].to_numpy(dtype=int)
    low = population["price_per_m2_brl_real"].lt(AUDIT_LOW_PRICE)
    tables: list[pd.DataFrame] = []
    for spec_id, fit in fits.items():
        deficit = 1 - fit.weights
        total = float(deficit.sum())
        scale = (
            pd.Series(years).map(dict(zip(np.unique(years), fit.scales, strict=True)))
            if spec_id == "huber_year"
            else float(fit.scales[0])
        )
        cells = pd.DataFrame(
            {
                "year": years,
                "property_type": population["property_type"].to_numpy(dtype=str),
                "scale": scale,
                "weight": fit.weights,
                "downweighted": fit.weights < 1,
                "deficit_share": deficit / total if total else 0.0,
                "low_tail_deficit_share": deficit * low.to_numpy() / total if total else 0.0,
            }
        )
        grouped = cells.groupby(["year", "property_type"], as_index=False).agg(
            n=("weight", "size"),
            share_downweighted=("downweighted", "mean"),
            mean_weight=("weight", "mean"),
            share_of_total_deficit=("deficit_share", "sum"),
            low_tail_share_of_total_deficit=("low_tail_deficit_share", "sum"),
            scale=("scale", "first"),
        )
        grouped.insert(0, "spec_id", spec_id)
        tables.append(grouped)
    return pd.concat(tables, ignore_index=True)


def tax_base_diagnostics(window: pd.DataFrame) -> TaxBaseDiagnostics:
    """Describe the declared amount relative to the recorded positive tax base."""
    rows = window.loc[window["value_tax_base_brl"].gt(0)]
    declared, base = rows["value_declared_brl"], rows["value_tax_base_brl"]
    comparisons = pd.DataFrame(
        {
            "year": rows["year"],
            "quarter": rows["quarter"].dt.to_period("Q").astype(str),
            "below": declared.lt(base),
            "ratio": declared / base,
        }
    )
    return {
        "n": len(rows),
        "declared_above_base": int(declared.gt(base).sum()),
        "annual": comparisons.groupby("year", as_index=False).agg(
            share_below=("below", "mean"), median_declared_base=("ratio", "median")
        ),
        "quarterly": comparisons.groupby("quarter", as_index=False).agg(
            share_below=("below", "mean")
        ),
    }


def round_number_diagnostics(window: pd.DataFrame) -> RoundNumbers:
    """Measure exact multiples and half-to-even bins on the dashboard population."""
    multiple = 10_000
    values = window.loc[
        window["year"].between(*HEAPING_YEARS)
        & window["value_declared_brl"].between(HEAPING_MIN_VALUE, HEAPING_MAX_VALUE),
        "value_declared_brl",
    ]
    exact_10k = float(values.mod(multiple).eq(0).mean())
    exact_50k = float(values.mod(HEAPING_ROUND_MULTIPLE).eq(0).mean())
    n, dashboard_share = heaping_summary(heaping_table(window))
    bin_rows = []
    for width in (HEAPING_BIN_WIDTH // 2, HEAPING_BIN_WIDTH, HEAPING_BIN_WIDTH * 2):
        centres = values.div(width).round().mul(width)
        share = (
            dashboard_share
            if width == HEAPING_BIN_WIDTH
            else float(centres.mod(HEAPING_ROUND_MULTIPLE).eq(0).mean())
        )
        bin_rows.append(
            {
                "width_brl": width,
                "share": share,
                "uniform_baseline": width / HEAPING_ROUND_MULTIPLE,
            }
        )
    return {
        "n": n,
        "exact_10000_share": exact_10k,
        "exact_50000_share": exact_50k,
        "ratio_to_one_fifth_share": exact_50k * (HEAPING_ROUND_MULTIPLE / multiple) / exact_10k
        if exact_10k > 0
        else None,
        "bin_widths": pd.DataFrame(bin_rows),
    }


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


def _median_intervals(
    rows: pd.DataFrame,
    records_rng: np.random.Generator,
    block_rng: np.random.Generator,
    draws: int,
) -> dict[str, float | int]:
    values = rows["price_per_m2_brl_real"].to_numpy(dtype=float)
    codes = _block_face_codes(rows)
    median = float(np.median(values))
    record_medians = np.median(records_rng.choice(values, size=(draws, values.size)), axis=1)
    block_medians = _block_face_medians(values, codes, block_rng, draws)
    rec_lo, rec_hi = np.quantile(record_medians, MEDIAN_QUANTILES)
    blk_lo, blk_hi = np.quantile(block_medians, MEDIAN_QUANTILES)
    return {
        "n": len(values),
        "n_clusters": int(codes.max()) + 1,
        "median": median,
        "share_houses": float(rows["property_type"].eq("house").mean()),
        "record_p025": float(rec_lo),
        "record_p975": float(rec_hi),
        "record_relative_width": float((rec_hi - rec_lo) / median),
        "block_p025": float(blk_lo),
        "block_p975": float(blk_hi),
        "block_relative_width": float((blk_hi - blk_lo) / median),
    }


def neighbourhood_quarter_uncertainty(
    window: pd.DataFrame,
    *,
    records_rng: np.random.Generator,
    block_rng: np.random.Generator,
    draws: int,
) -> QuarterlyUncertainty:
    """Bootstrap quarterly medians independently and by approximate block face."""
    rows = window.loc[
        window["neighbourhood"].isin(DEFAULT_NEIGHBOURHOODS)
        & window["price_per_m2_brl_real"].notna()
    ].assign(quarter_label=lambda data: data["quarter"].dt.to_period("Q").astype(str))
    records = [
        {
            "neighbourhood": str(name),
            "quarter": str(quarter),
            **_median_intervals(group, records_rng, block_rng, draws),
        }
        for (name, quarter), group in rows.groupby(
            ["neighbourhood", "quarter_label"], observed=True, sort=True
        )
        if len(group) >= NEIGHBOURHOOD_QUARTER_MINIMUM
    ]
    quarters = pd.DataFrame(records)
    if quarters.empty:
        return {"quarters": quarters, "neighbourhoods": pd.DataFrame()}
    neighbourhoods = quarters.groupby("neighbourhood", as_index=False).agg(
        n_quarters=("n", "size"),
        median_record_relative_width=("record_relative_width", "median"),
        median_block_relative_width=("block_relative_width", "median"),
        min_share_houses=("share_houses", "min"),
        max_share_houses=("share_houses", "max"),
    )
    return {"quarters": quarters, "neighbourhoods": neighbourhoods}
