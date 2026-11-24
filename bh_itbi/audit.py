"""Verify provenance, run the offline robustness audit and write its evidence."""

from __future__ import annotations

import math
import platform
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import TypedDict

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from bh_itbi import data, models
from bh_itbi.audit_checks import (
    AdjacentQuarterNoise,
    PriceTails,
    QuarterlyUncertainty,
    RoundNumbers,
    TaxBaseDiagnostics,
    adjacent_quarter_noise,
    audit_window,
    huber_weight_profiles,
    low_tail_fractions,
    low_tail_profile,
    neighbourhood_quarter_uncertainty,
    price_tails,
    ratio_screen_reach,
    residual_dispersion,
    round_number_diagnostics,
    tax_base_diagnostics,
)
from bh_itbi.audit_figure import IndexSeries, index_comparison_svg
from bh_itbi.audit_patterns import AuditPatterns, audit_trajectory_patterns
from bh_itbi.cluster import (
    ClusterMetadata,
    TrajectoryStability,
    cluster_trajectories,
    trajectory_stability,
)
from bh_itbi.config import (
    AUDIT_LOW_PRICE,
    AUDIT_VERSION,
    END_YEAR,
    INDEX_BASE,
    MODEL_VERSION,
    PATTERN_ORDER,
    PATTERNS_ID,
    REVISION,
    ROOT,
    SOURCE_SHA256,
    START_YEAR,
)
from bh_itbi.patterns import PatternSettings, pattern_settings
from bh_itbi.sensitivity import (
    PROTOCOL,
    SensitivityError,
    SensitivityResults,
    run_specifications,
)

THREAD_LIMIT = 2
BASELINE_RTOL = 1e-9


class AuditError(ValueError):
    """The fixed audit could not reproduce the published artefacts or fit its protocol."""


class AuditProvenance(TypedDict):
    """Identity and verification state of the audit input table."""

    revision: str
    source_sha256: str
    transactions_sha256: str
    cached_table_verified: bool


class AuditManifest(AuditProvenance):
    """Deterministic provenance, software versions and settings for an audit run."""

    audit_version: str
    protocol_id: str
    protocol_sha256: str
    model_version: str
    git_commit: str | None
    dirty: bool | None
    versions: dict[str, str]
    seed: int
    cluster_draws: int
    median_draws: int
    thread_limit: int
    protocol_settings: bool
    patterns_id: str
    pattern_settings: PatternSettings


@dataclass(frozen=True)
class AuditInputs:
    """Inject prepared artefacts and their provenance for offline verification."""

    frame: pd.DataFrame
    provenance: AuditProvenance
    hedonic: pd.DataFrame | None = None
    hedonic_metadata: models.HedonicMetadata | None = None
    trajectories: tuple[pd.DataFrame, ClusterMetadata] | None = None


@dataclass(frozen=True)
class AuditSettings:
    """Set random streams and draw counts, defaulting to the frozen protocol."""

    seed: int = PROTOCOL.seed
    cluster_draws: int = PROTOCOL.cluster_draws
    median_draws: int = PROTOCOL.median_draws

    def __post_init__(self) -> None:
        if self.seed < 0 or self.cluster_draws < 1 or self.median_draws < 1:
            raise AuditError("The audit needs a non-negative seed and positive draw counts.")


class _AuditDiagnostics(TypedDict):
    tails: PriceTails
    low_tail_profile: pd.DataFrame
    fraction_test: pd.DataFrame
    ratio_screen_reach: pd.DataFrame
    residual_dispersion: pd.DataFrame
    adjacent_quarter_noise: AdjacentQuarterNoise
    tax_base: TaxBaseDiagnostics
    round_numbers: RoundNumbers
    neighbourhood_quarterly_uncertainty: QuarterlyUncertainty
    clustering: TrajectoryStability


@dataclass(frozen=True)
class _AuditOutputs:
    sensitivity: SensitivityResults
    weights: pd.DataFrame
    diagnostics: _AuditDiagnostics
    patterns: AuditPatterns


def _verified_audit_inputs() -> AuditInputs:
    """Read the pinned cache and published artefacts, with no preparation fallback."""
    try:
        metadata = data.load_source_metadata(allow_prepare=False)
        if metadata["revision"] != REVISION or metadata["source_sha256"] != SOURCE_SHA256:
            raise data.DataError("The source identity differs from the pinned revision.")
        digest = data.file_sha256(data.CACHE_DIR / "transactions.parquet")
        if digest != metadata["transactions_sha256"]:
            raise data.DataError("The cached transaction table has a SHA-256 mismatch.")
        frame = data.load_transactions(allow_prepare=False)
        published = models.load_models()
        if published is None:
            raise data.DataError("The published model artefacts are missing or incompatible.")
    except (OSError, ValueError, KeyError) as error:
        raise data.DataError(f"{error} Run `uv run python main.py prepare`.") from error
    return AuditInputs(
        frame,
        {
            "revision": metadata["revision"],
            "source_sha256": metadata["source_sha256"],
            "transactions_sha256": digest,
            "cached_table_verified": True,
        },
        hedonic=published.hedonic,
        hedonic_metadata=published.metadata["hedonic"],
    )


def _audit_git(*arguments: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *arguments], cwd=ROOT, capture_output=True, text=True, check=True
        )
    except OSError, subprocess.SubprocessError:
        return None
    return result.stdout.strip()


def _make_audit_manifest(provenance: AuditProvenance, settings: AuditSettings) -> AuditManifest:
    status = _audit_git("status", "--porcelain")
    return {
        **provenance,
        "audit_version": AUDIT_VERSION,
        "protocol_id": PROTOCOL.protocol_id,
        "protocol_sha256": PROTOCOL.sha256,
        "model_version": MODEL_VERSION,
        "git_commit": _audit_git("rev-parse", "HEAD"),
        "dirty": None if status is None else bool(status),
        "versions": {
            "python": platform.python_version(),
            **{
                name: version(name)
                for name in ("numpy", "pandas", "statsmodels", "scikit-learn")
            },
        },
        "seed": settings.seed,
        "cluster_draws": settings.cluster_draws,
        "median_draws": settings.median_draws,
        "thread_limit": THREAD_LIMIT,
        "protocol_settings": settings == AuditSettings(),
        "patterns_id": PATTERNS_ID,
        "pattern_settings": pattern_settings(),
    }


def _verify_baseline_reproduction(inputs: AuditInputs, sensitivity: SensitivityResults) -> None:
    published, metadata = inputs.hedonic, inputs.hedonic_metadata
    if published is None:
        published, metadata = models.fit_hedonic(inputs.frame)
    if metadata is None:
        raise AuditError("The supplied hedonic table requires its published metadata.")
    table = sensitivity.index.loc[sensitivity.index["spec_id"].eq("baseline")]
    summary = sensitivity.specifications.iloc[0]
    published = published.sort_values("quarter")
    old = published[["hedonic_index", "lower", "upper"]].to_numpy()
    new = table[["index", "lower", "upper"]].to_numpy()
    matching = (
        table["quarter"].tolist() == published["quarter"].tolist()
        and np.allclose(new, old, rtol=BASELINE_RTOL, atol=0)
        and int(summary["n"]) == metadata["n"]
        and math.isclose(
            float(summary["r_squared"]), metadata["r_squared"], rel_tol=BASELINE_RTOL
        )
    )
    if not matching:
        raise AuditError(
            "The baseline does not reproduce the published index, intervals or fit metadata."
        )


def _collect_audit_diagnostics(
    inputs: AuditInputs, settings: AuditSettings, sensitivity: SensitivityResults
) -> _AuditDiagnostics:
    streams = np.random.SeedSequence(settings.seed).spawn(3)
    trajectory_rng, records_rng, block_rng = map(np.random.default_rng, streams)
    window = audit_window(inputs.frame)
    tau = sensitivity.index.loc[sensitivity.index["spec_id"].eq("baseline"), "tau"]
    if inputs.trajectories is None:
        members, _, cluster_metadata = cluster_trajectories(inputs.frame)
    else:
        members, cluster_metadata = inputs.trajectories
    return {
        "tails": price_tails(window),
        "low_tail_profile": low_tail_profile(window),
        "fraction_test": low_tail_fractions(window),
        "ratio_screen_reach": ratio_screen_reach(window),
        "residual_dispersion": residual_dispersion(
            sensitivity.population, sensitivity.baseline.residuals
        ),
        "adjacent_quarter_noise": adjacent_quarter_noise(
            tau.to_numpy(dtype=float), sensitivity.baseline.covariance
        ),
        "tax_base": tax_base_diagnostics(window),
        "round_numbers": round_number_diagnostics(window),
        "neighbourhood_quarterly_uncertainty": neighbourhood_quarter_uncertainty(
            window, records_rng=records_rng, block_rng=block_rng, draws=settings.median_draws
        ),
        "clustering": trajectory_stability(
            inputs.frame,
            members,
            cluster_metadata,
            rng=trajectory_rng,
            draws=settings.cluster_draws,
        ),
    }


def _sorted_audit_json(value: object) -> object:
    """Normalise numeric scalars and order keys recursively for the atomic writer."""
    if isinstance(value, pd.DataFrame):
        value = value.to_dict("records")
    if isinstance(value, Mapping):
        return {str(key): _sorted_audit_json(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_sorted_audit_json(item) for item in value]
    if isinstance(value, np.generic):
        return _sorted_audit_json(value.item())
    if isinstance(value, float):
        return float(f"{value:.10g}") if math.isfinite(value) else None
    if value is pd.NA:
        return None
    return value


def _write_audit_json(destination: Path, value: Mapping[str, object]) -> None:
    document = _sorted_audit_json(value)
    assert isinstance(document, dict)
    data.atomic_json(document, destination)


def _write_audit_csv(destination: Path, table: pd.DataFrame) -> None:
    data.atomic_write(
        destination,
        lambda path: table.to_csv(path, index=False, float_format="%.10g", lineterminator="\n"),
    )


def _markdown_rows(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    def line(values: Sequence[object]) -> str:
        return "| " + " | ".join(str(value).replace("|", r"\|") for value in values) + " |"

    return "\n".join(
        [line(headers), line(["---"] * len(headers)), *(line(row) for row in rows)]
    )


def _join_words(items: Sequence[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _rows(frame: pd.DataFrame, key: str) -> dict[str, pd.Series]:
    """Index a small table's rows by one column, keeping each row a typed Series."""
    return {str(row[key]): row for _, row in frame.iterrows()}


def _interval(row: pd.Series) -> str:
    return f"{row['lower_2025Q4']:.1f}–{row['upper_2025Q4']:.1f}"


def _threshold(rule: object) -> str:
    return str(rule).split("≥ ")[-1]


def _exception_text(exceptions: pd.DataFrame) -> str:
    if exceptions.empty:
        return "there are no exceptions"
    families = exceptions["family"].unique()
    if len(families) == 1 and len(exceptions) > 1:
        lowest = _threshold(exceptions["rule"].iloc[0])
        return f"the exceptions are the {families[0]}s from {lowest} up"
    return "the exceptions are " + _join_words(
        [str(rule).lower() for rule in exceptions["rule"]]
    )


def _audit_summary(table: pd.DataFrame) -> str:
    specs = _rows(table, "spec_id")
    base, huber = specs["baseline"], specs["huber_year"]
    low = table.iloc[int(table["index_2025Q4"].to_numpy().argmin())]
    high = table.iloc[int(table["index_2025Q4"].to_numpy().argmax())]
    above = table["lower_2025Q4"].gt(INDEX_BASE)
    return (
        "# How robust is the price index?\n\n"
        f"The published hedonic index puts the fourth quarter of {END_YEAR} at "
        f"{base['index_2025Q4']:.1f} (95% interval {_interval(base)}), with the first quarter "
        f"of {START_YEAR} at {INDEX_BASE}. Re-estimated under {len(specs)} specifications, "
        f"that figure ranges from {low['index_2025Q4']:.1f} ({str(low['rule']).lower()}) to "
        f"{high['index_2025Q4']:.1f} ({str(high['rule']).lower()}). Most of the spread comes "
        "from one group of records: those declared far below the municipal tax base, "
        "concentrated in 2016–2019. Down-weighting outlying records with a Huber regression "
        f"lowers the end of the series to {huber['index_2025Q4']:.1f}, but does not remove the "
        f"rise. The {END_YEAR} interval lies above {INDEX_BASE} in {int(above.sum())} of the "
        f"{len(specs)} specifications; {_exception_text(table.loc[~above])}.\n\n"
        "![Quarterly index under four specifications.](index_comparison.svg)\n\n"
        f"*Quarterly index under four specifications ({START_YEAR}Q1 = {INDEX_BASE}). The "
        "shaded band is the 95% interval of the published index. The other specifications are "
        "in [index_trajectories.csv](index_trajectories.csv).*"
    )


def _low_tail_paragraph(checks: _AuditDiagnostics, deficit: float) -> str:
    profile = _rows(checks["low_tail_profile"], "price_group")
    if "below_1000" not in profile:
        return f"**Very low declared values.** No records fall below R${AUDIT_LOW_PRICE:,}/m²."
    tail, rest = profile["below_1000"], profile["at_or_above_1000"]
    by_year = checks["tails"]["by_year"].set_index("year")["share_below_1000"]
    share = tail["n"] / (tail["n"] + rest["n"])
    return (
        f"**Very low declared values.** {tail['n']:,.0f} records ({share:.1%}) have a real "
        f"declared value below R${AUDIT_LOW_PRICE:,}/m². Their median declared value is "
        f"R${tail['median_declared']:,.0f}, against R${rest['median_declared']:,.0f} for the "
        f"rest, and {tail['median_declared_base']:.0%} of the tax base; "
        f"{tail['share_houses']:.0%} are houses, against {rest['share_houses']:.0%} of the "
        f"other records. They are {by_year.iloc[0]:.1%} of records in {by_year.index[0]} and "
        f"{by_year.iloc[-1]:.1%} in {by_year.index[-1]}, so they pull the early quarters down "
        "and steepen the rise. The source cannot say what they are: it has no field for the "
        "nature of the transfer or the date of the contract. According to the municipal data "
        "dictionary, the published area already reflects the share acquired, so partial "
        "transfers would not explain them, provided the harmonised area column is the one the "
        "dictionary describes (still to be checked against the raw files). The Huber "
        "regression, which down-weights large residuals instead of dropping records, places "
        f"{deficit:.0%} of the weight it removes on these records."
    )


def _cut_off_paragraph(table: pd.DataFrame) -> str:
    floors = table.loc[table["family"].eq("real price floor")]
    huber = _rows(table, "spec_id")["huber_year"]
    values = ", ".join(f"{value:.1f}" for value in floors["index_2025Q4"])
    first, last = _threshold(floors["rule"].iloc[0]), _threshold(floors["rule"].iloc[-1])
    return (
        f"**No natural cut-off.** Raising a price floor from {first}/m² to {last}/m² lowers "
        f"the {END_YEAR}Q4 value step by step ({values}), with no level at which it "
        f"settles. The Huber fit gives {huber['index_2025Q4']:.1f} ({_interval(huber)}); that "
        "is the figure the dashboard's sensitivity note reports."
    )


def _tax_base_paragraphs(
    table: pd.DataFrame, checks: _AuditDiagnostics, exclusions: pd.DataFrame
) -> str:
    annual = checks["tax_base"]["annual"].set_index("year")
    below = annual["share_below"]
    parity = annual.index[annual["median_declared_base"].ge(0.995)]
    parity_text = (
        f"to 1.00 from {int(parity.min())}" if len(parity) else "without reaching 1.00"
    )
    rebound = (
        f", before rising again to {below.iloc[-1]:.0%} in {below.index[-1]}"
        if below.iloc[-1] > below.min() + 0.05
        else ""
    )
    ratios = table.loc[table["family"].eq("declared/base floor")]
    removed = exclusions.loc[exclusions["spec_id"].eq("ratio_floor_050")]
    counts = removed.groupby("year")[["n_removed", "n_population"]].sum()
    shares = counts["n_removed"] / counts["n_population"]
    return (
        "**The tax base moved.** The median ratio of declared value to tax base rises from "
        f"{annual['median_declared_base'].iloc[0]:.2f} in {annual.index[0]} {parity_text}, "
        f"and the share of records declared below the base falls from {below.iloc[0]:.0%} to "
        f"{below.min():.0%} in {below.idxmin()}{rebound}. Whatever the cause, the base is not "
        "a fixed yardstick across the period.\n\n"
        "**Declared/base floors are therefore hard to read.** A floor of 0.50 removes "
        f"{shares.iloc[0]:.1%} of {shares.index[0]} records but {shares.iloc[-1]:.1%} of "
        f"{shares.index[-1]} records, mixing data quality with changes in how the base was "
        "set. These specifications give the lowest values "
        f"({ratios['index_2025Q4'].min():.1f}–{ratios['index_2025Q4'].max():.1f}) and are not "
        "a cleaner version of the index."
    )


def _property_type_paragraph(table: pd.DataFrame) -> str:
    specs = _rows(table, "spec_id")
    apartments, houses = specs["apartments_only"], specs["houses_only"]
    return (
        f"**Property type.** Apartments alone give {apartments['index_2025Q4']:.1f}; houses "
        f"alone give {houses['index_2025Q4']:.1f} with a much wider interval "
        f"({_interval(houses)}), from {houses['n']:,.0f} records. The common trend the "
        "pooled model imposes on both types is not what drives the result."
    )


def _patterns_paragraphs(evidence: AuditPatterns, old_ari: float) -> str:
    metadata, independent = evidence["metadata"], evidence["independent_records"]
    sizes = [metadata["patterns"][name]["size"] for name in PATTERN_ORDER]
    firm = [metadata["patterns"][name]["firm"] for name in PATTERN_ORDER]
    return (
        "## Neighbourhood trajectory patterns\n\n"
        f"The dashboard groups {metadata['n_neighbourhoods']} neighbourhoods into three "
        "patterns of quality-adjusted apartment prices by biennium: falling then stabilising "
        f"({sizes[0]}), stable ({sizes[1]}) and a late rise ({sizes[2]}). Firmness comes from "
        "resampling whole block faces within each neighbourhood and biennium, because sales in "
        "the same building are not independent. The three patterns reappear in "
        f"{metadata['separation_share']:.0%} of {metadata['draws']} draws, but membership is "
        f"loose: {firm[0]}, {firm[1]} and {firm[2]} neighbourhoods stay in their pattern in at "
        f"least {metadata['firm_share']:.0%} of draws, and the median adjusted Rand index "
        f"against the published partition is {metadata['ari_median']:.2f}. Resampling "
        f"individual records would give {independent['ari_median']:.2f} and "
        f"{sum(independent['firm'].values())} firm members instead of {sum(firm)}, which "
        "overstates stability. Draws that miss the three patterns usually spend one centre on "
        "a single neighbourhood with an unusually wide spread of prices.\n\n"
        "These patterns replace a four-group typology built on unadjusted annual medians, "
        f"withdrawn when its bootstrap agreement came out at {old_ari:.2f}. The criterion for "
        "showing them (stable pattern shapes with membership reported per neighbourhood, "
        "rather than a stable partition) was settled after seeing these results."
    )


def _other_checks(checks: _AuditDiagnostics) -> str:
    noise, heaping = checks["adjacent_quarter_noise"], checks["round_numbers"]
    widths = checks["neighbourhood_quarterly_uncertainty"]["neighbourhoods"][
        "median_block_relative_width"
    ]
    autocorrelation = f"{noise['lag1_autocorrelation']:.2f}".replace("-", "−")
    return (
        "## Other checks\n\n"
        "- **Quarter-to-quarter noise.** Sampling error accounts for about "
        f"{noise['descriptive_ratio']:.0%} of the variance of quarterly changes in the "
        "published index, and consecutive changes are negatively correlated "
        f"({autocorrelation}), so single-quarter moves should not be over-read.\n"
        f"- **Round numbers.** {heaping['exact_10000_share']:.0%} of declared values in the "
        "dashboard's range are exact multiples of R$10,000, which produces spikes in "
        "fine-grained histograms.\n"
        "- **Neighbourhood quarterly medians.** Resampling by block face, the interval around "
        f"a reference neighbourhood's quarterly median is typically {widths.min():.0%} to "
        f"{widths.max():.0%} of the median itself."
    )


LIMITS = """## Limits

- The source does not identify market sales, so every specification is a proxy for the population of interest.
- The specifications share most of their records and their intervals are pointwise, so differences between them are descriptive rather than tests.
- The Huber intervals treat the estimated scales as fixed.
- Block faces approximate buildings; records without a matched face are resampled on their own."""  # noqa: E501

AUDIT_FILES = (
    ("protocol.json", "the specifications and estimator settings"),
    ("specifications.csv", "one row per specification: sample, fit and headline values"),
    ("index_trajectories.csv", "quarterly index and intervals for every specification"),
    ("decomposition.csv", "composition terms per specification and quarter"),
    ("exclusions.csv", "records removed by each screen, by year and property type"),
    ("huber_weights.csv", "Huber scales and down-weighting by year and property type"),
    (
        "diagnostics.json",
        "price tails, low-tail profile, tax-base series, round numbers, quarterly noise, "
        "neighbourhood medians and the withdrawn typology",
    ),
    ("trajectory_patterns.json", "pattern centres, ranges and membership per neighbourhood"),
    ("manifest.json", "hashes, Git commit and software versions"),
    ("index_comparison.svg", "the figure above"),
)


def _files_section(manifest: AuditManifest) -> str:
    rows = [(f"[{name}]({name})", contents) for name, contents in AUDIT_FILES]
    return (
        "## Files and reproduction\n\n"
        "Running `python main.py audit` on the prepared cache regenerates every file here. "
        f"This version comes from source revision `{manifest['revision'][:7]}`, model "
        f"`{manifest['model_version']}` and protocol `{manifest['protocol_id']}`.\n\n"
        + _markdown_rows(("File", "Contents"), rows)
    )


COMPARISON_SERIES = (
    IndexSeries("baseline", "Published", "#1d6f73"),
    IndexSeries("price_floor_1000", "Floor R$1,000/m²", "#b0612c"),
    IndexSeries("huber_year", "Huber", "#5b4b8a"),
    IndexSeries("ratio_floor_050", "Declared/base ≥ 0.50", "#7a7a7a", "5 4"),
)


def _render_audit_report(manifest: AuditManifest, outputs: _AuditOutputs) -> str:
    table = outputs.sensitivity.specifications
    checks = outputs.diagnostics
    deficit = outputs.weights.groupby("spec_id")["low_tail_share_of_total_deficit"].sum()
    sections = (
        _audit_summary(table),
        "## Where the spread comes from",
        _low_tail_paragraph(checks, float(deficit["huber_year"])),
        _cut_off_paragraph(table),
        _tax_base_paragraphs(table, checks, outputs.sensitivity.exclusions),
        _property_type_paragraph(table),
        _patterns_paragraphs(outputs.patterns, checks["clustering"]["bootstrap"]["ari_median"]),
        _other_checks(checks),
        LIMITS,
        _files_section(manifest),
    )
    return "\n\n".join(sections) + "\n"


def _write_audit_text(destination: Path, text: str) -> None:
    def write(path: Path) -> None:
        path.write_text(text, encoding="utf-8")

    data.atomic_write(destination, write)


def _publish_audit_outputs(
    destination: Path, manifest: AuditManifest, outputs: _AuditOutputs
) -> None:
    report = _render_audit_report(manifest, outputs)
    for filename, table in (
        ("specifications.csv", outputs.sensitivity.specifications),
        ("index_trajectories.csv", outputs.sensitivity.index),
        ("decomposition.csv", outputs.sensitivity.decomposition),
        ("exclusions.csv", outputs.sensitivity.exclusions),
        ("huber_weights.csv", outputs.weights),
    ):
        _write_audit_csv(destination / filename, table)
    _write_audit_json(destination / "diagnostics.json", outputs.diagnostics)
    _write_audit_json(destination / "trajectory_patterns.json", outputs.patterns)
    _write_audit_text(destination / "protocol.json", PROTOCOL.canonical_json())
    _write_audit_text(destination / "report.md", report)
    _write_audit_text(
        destination / "index_comparison.svg",
        index_comparison_svg(outputs.sensitivity.index, COMPARISON_SERIES),
    )
    _write_audit_json(destination / "manifest.json", manifest)


def run_audit(
    output_dir: Path,
    *,
    inputs: AuditInputs | None = None,
    settings: AuditSettings | None = None,
) -> AuditManifest:
    """Verify the baseline, compute the frozen protocol and publish the evidence files."""
    settings = settings if settings is not None else AuditSettings()
    print("Verifying audit inputs…", flush=True)
    inputs = inputs if inputs is not None else _verified_audit_inputs()
    manifest = _make_audit_manifest(inputs.provenance, settings)
    with threadpool_limits(limits=THREAD_LIMIT):
        print(f"Fitting {len(PROTOCOL.specifications)} hedonic specifications…", flush=True)
        try:
            sensitivity = run_specifications(inputs.frame)
        except SensitivityError as error:
            raise AuditError(str(error)) from error
        _verify_baseline_reproduction(inputs, sensitivity)
        print(
            "Computing descriptive diagnostics and resampling trajectories and medians…",
            flush=True,
        )
        diagnostics = _collect_audit_diagnostics(inputs, settings, sensitivity)
        weights = huber_weight_profiles(sensitivity.population, sensitivity.huber_fits)
        print("Resampling trajectory patterns by record and block face…", flush=True)
        patterns = audit_trajectory_patterns(inputs.frame)
    print("Writing audit evidence…", flush=True)
    _publish_audit_outputs(
        output_dir, manifest, _AuditOutputs(sensitivity, weights, diagnostics, patterns)
    )
    return manifest
