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
from bh_itbi.audit_patterns import AuditPatterns, audit_trajectory_patterns
from bh_itbi.cluster import (
    ClusterMetadata,
    TrajectoryStability,
    cluster_trajectories,
    trajectory_stability,
)
from bh_itbi.config import (
    AUDIT_VERSION,
    END_YEAR,
    HEDONIC_CONFIDENCE_LEVEL,
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
SELECTED_QUARTERS = ("2016Q3", "2019Q4", "2021Q4", "2023Q4", "2025Q4")

TARGET_AND_POPULATION = """## Target and observable population

**Scientific target.** The evolution of inflation-adjusted declared values of residential properties transferred in arm's-length market sales in Belo Horizonte, adjusted for the characteristics observed in the hedonic specification.

**Observable population.** Eligible residential ITBI records (apartments and houses) with a declared value, a positive built area and complete model characteristics. ITBI covers onerous transfers of any nature. The municipal source has no field for the nature of the transfer or the date of the underlying contract, so membership in the target population is unobserved. No rule in this audit identifies arm's-length market sales. Every screen defines an operational proxy population and is reported as such.

**Source definitions recorded, not verified here.** According to the municipal data dictionary, the published built area is the unit's built area multiplied by the acquired percentage ("Área Construída Adquirida"), and the tax base is the market value of the rights transferred ("Valor Base Cálculo"). Whether the harmonised `built_area_m2` maps to "Área Construída Adquirida" remains to be confirmed against the raw files.
"""  # noqa: E501 - Fixed wording from the audit protocol.

INTERPRETATION = """## Interpretation rules

- Each screen defines an operational proxy population. Membership in the target is unobserved.
- Differences between specifications are descriptive. The estimates share records, and no
  joint covariance is estimated.
- Huber-weighted means depend on the fitted model.
- The adjacent-quarter variance ratio is descriptive.
- The tax-base series and contrasts establish no causal effects of legislation, tax
  administration or market behaviour.
"""

LIMITATIONS = """## Limitations and open source questions

- The mapping of `built_area_m2` to the municipal acquired-area definition requires
  verification against the raw records.
- The municipal source contains neither transaction nature nor the underlying contract date.
- The Huber sandwich holds the estimated scales fixed. Its intervals are pointwise and
  model-dependent. A neighbourhood bootstrap of the Huber fits is deferred on
  computational grounds.
- Block faces approximate buildings. Records without a face match form singleton clusters.
"""

TRAJECTORY_PATTERNS_CONTEXT = (
    "The v1 annual typology (four groups on unadjusted medians indexed to 2016) was "
    "withdrawn after bootstrap agreement with the published partition reached a median ARI "
    "of 0.45. A rule proposed before any re-analysis (publish groups only if the bootstrap "
    "median ARI reaches 0.75) was not met by any specification tested: the best reached about "
    "0.61. After inspecting those results, the publication criterion was changed: patterns "
    "are shown because their centres are stable under resampling, while membership is "
    "reported per neighbourhood and borderline neighbourhoods are identified as such. "
    "This change was made after seeing the data and is reported as such."
)


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


def _audit_display(value: object, precision: str = ".3f") -> str:
    if value is None or value is pd.NA:
        return "—"
    if isinstance(value, float):
        return format(value, precision) if math.isfinite(value) else "—"
    return str(value)


def _audit_report_table(
    frame: pd.DataFrame,
    columns: Mapping[str, str] | None = None,
    *,
    precision: str = ".3f",
) -> str:
    if frame.empty:
        return "No eligible cells."
    labels = {str(name): str(name).replace("_", " ") for name in frame.columns}
    if columns is not None:
        labels = dict(columns)
    rows = [
        [_audit_display(value, precision) for value in row]
        for row in frame[list(labels)].itertuples(index=False, name=None)
    ]
    return _markdown_rows(list(labels.values()), rows)


def _audit_provenance_section(manifest: AuditManifest) -> str:
    return (
        "## Provenance\n\n"
        f"- Source revision `{manifest['revision']}`\n"
        f"- Source SHA-256 `{manifest['source_sha256']}`\n"
        f"- Cached transaction table verified: **{manifest['cached_table_verified']}**\n"
        f"- Model version `{manifest['model_version']}` and audit version "
        f"`{manifest['audit_version']}`\n"
        f"- Protocol `{manifest['protocol_id']}` with SHA-256 `{manifest['protocol_sha256']}`\n"
        f"- Seed {manifest['seed']}, {manifest['cluster_draws']} trajectory bootstrap draws, "
        f"{manifest['median_draws']} draws per quarterly median bootstrap and "
        f"{manifest['thread_limit']} numerical threads\n\n"
        "The cached-table hash, Git state and software versions are in "
        "[manifest.json](manifest.json)."
    )


def _audit_protocol_section(specifications: pd.DataFrame) -> str:
    columns = {
        "spec_id": "Specification",
        "family": "Family",
        "rule": "Retained rows",
        "estimator": "Estimator",
    }
    return (
        "## Protocol\n\n"
        "All screens remove records from the published model population. Neighbourhood "
        "eligibility is applied once to that population. The fixed comparisons of separately "
        "estimated property types address the common trend imposed by the pooled model.\n\n"
        f"{_audit_report_table(specifications, columns)}\n\n"
        "Huber clips the residual score at ±k and minimises quadratic loss inside those "
        "bounds and linear loss outside, conditional on the final thresholds. The thresholds "
        f"are {PROTOCOL.tuning} times the residual MAD divided by {PROTOCOL.mad_consistency}, "
        "using a global scale or a scale for each calendar year. The year-specific fit changes "
        "only the threshold. Standardised Huber loss would weight years by inverse scale "
        "squared even in the absence of clipping, changing the estimand. Both fits recover "
        "OLS in the absence of clipping.\n\n"
        "Huber estimates start at OLS and use iteratively reweighted least squares. "
        f"The maximum coefficient change and maximum relative scale change must both be below "
        f"{PROTOCOL.tolerance:g} within {PROTOCOL.max_iterations} iterations. The audit also "
        "checks the score, the fixed point and the weighted quarterly residual means. "
        f"All specifications have pointwise {HEDONIC_CONFIDENCE_LEVEL:.0%} intervals based "
        "on their own neighbourhood-clustered covariance."
    )


def _audit_specification_sections(sensitivity: SensitivityResults) -> str:
    table = sensitivity.specifications
    base = table.iloc[0]
    rows = [
        (
            row.spec_id,
            f"{row.n:,}",
            f"{row.index_2016Q3:.2f}",
            f"{row.index_2025Q4:.2f} [{row.lower_2025Q4:.2f}, {row.upper_2025Q4:.2f}]",
            f"{row.max_abs_log_dev:.5f}",
            row.quarter_of_max_dev,
        )
        for row in table.itertuples(index=False)
    ]
    summary = _markdown_rows(
        (
            "Specification",
            "n",
            "2016Q3",
            "2025Q4 [95% interval]",
            "Max absolute log deviation",
            "Quarter",
        ),
        rows,
    )
    selected = sensitivity.index.pivot(index="spec_id", columns="quarter", values="index")
    selected = selected.loc[table["spec_id"], list(SELECTED_QUARTERS)].reset_index()
    return (
        "## Baseline reproduction\n\n"
        f"The baseline reproduced the published quarterly index, intervals and fit metadata "
        f"within relative tolerance {BASELINE_RTOL:g}. The OLS fit has {base['n']:,} records, "
        f"R² {base['r_squared']:.3f} and residual SD {base['residual_sd']:.3f} log points.\n\n"
        "## Specification summary\n\n"
        f"{summary}\n\n"
        "## Selected quarters\n\n"
        "The full trajectories and log deviations are in "
        "[index_trajectories.csv](index_trajectories.csv).\n\n"
        f"{_audit_report_table(selected, precision='.2f')}"
    )


def _audit_exclusion_section(sensitivity: SensitivityResults) -> str:
    grouped = sensitivity.exclusions.groupby(["spec_id", "year"])[
        ["n_population", "n_removed"]
    ].sum()
    shares = (grouped["n_removed"] / grouped["n_population"]).unstack("year")
    screens = sensitivity.specifications.loc[
        ~sensitivity.specifications["family"].isin(["reference", "estimator"])
    ]
    table = shares.reindex(screens["spec_id"]).reset_index()
    table.insert(1, "family", screens["family"].to_list())
    table.columns = table.columns.astype(str)
    return (
        "## Exclusion composition\n\n"
        "Annual shares use each year's published-model records as the denominator. "
        "[exclusions.csv](exclusions.csv) also gives counts and shares by property type.\n\n"
        + _audit_report_table(table, precision=".1%")
    )


def _audit_huber_section(outputs: _AuditOutputs) -> str:
    weights = outputs.weights
    grouped = (
        weights.assign(downweighted=weights["n"] * weights["share_downweighted"])
        .groupby(["spec_id", "year"], as_index=False)
        .agg(n=("n", "sum"), downweighted=("downweighted", "sum"), scale=("scale", "first"))
    )
    grouped["share_downweighted"] = grouped["downweighted"] / grouped["n"]
    deficit = weights.groupby("spec_id")["low_tail_share_of_total_deficit"].sum()
    text = (
        "## Huber weights and residual dispersion\n\n"
        "Shares use the weights from the final solve. Annual scales are in log points. "
        "The year-by-type detail is in [huber_weights.csv](huber_weights.csv).\n\n"
        + _audit_report_table(grouped[["spec_id", "year", "scale", "share_downweighted"]])
    )
    for spec_id, share in deficit.items():
        text += (
            f"\n\nRecords below R$1,000/m² carry {share:.1%} of the `{spec_id}` weight deficit."
        )
    return (
        text
        + "\n\n**Baseline OLS residual MAD scale, in log points**\n\n"
        + _audit_report_table(outputs.diagnostics["residual_dispersion"])
    )


def _audit_descriptive_section(checks: _AuditDiagnostics) -> str:
    tails = checks["tails"]
    noise = checks["adjacent_quarter_noise"]
    tax = checks["tax_base"]
    heaping = checks["round_numbers"]
    heaping_ratio = _audit_display(heaping["ratio_to_one_fifth_share"], ".2f")
    uncertainty = checks["neighbourhood_quarterly_uncertainty"]
    return "\n\n".join(
        (
            "## Descriptive diagnostics",
            f"**Price tails.** {tails['eligible_n']:,} eligible records have positive area.",
            _audit_report_table(tails["quantiles"], precision=",.3f"),
            _audit_report_table(tails["by_year"], precision=".3%"),
            "**Low-tail profile and fraction windows.** Counts at each fraction use ±0.003. "
            "The side counts are averaged over windows centred 0.012 to either side.",
            _audit_report_table(checks["low_tail_profile"]),
            _audit_report_table(checks["fraction_test"]),
            "**Reach of a declared/base floor of 0.50.**",
            _audit_report_table(checks["ratio_screen_reach"]),
            "**Adjacent-quarter changes.** "
            f"Across {noise['n_changes']} changes, observed variance is "
            f"{noise['observed_variance']:.6f} and mean estimated sampling variance is "
            f"{noise['mean_sampling_variance']:.6f} log points squared. "
            f"The descriptive ratio is {_audit_display(noise['descriptive_ratio'])}. "
            f"Lag-1 autocorrelation is {noise['lag1_autocorrelation']:.3f}, with "
            f"1/√n = {noise['white_noise_reference']:.3f} as a white-noise reference.",
            f"**Tax-base comparisons.** {tax['declared_above_base']:,} of {tax['n']:,} "
            "records with a positive tax base have declared values above it. Quarterly shares "
            "are in [diagnostics.json](diagnostics.json).",
            _audit_report_table(tax["annual"]),
            f"**Round numbers.** Among {heaping['n']:,} records in the dashboard's range, "
            f"{heaping['exact_10000_share']:.1%} are exact R$10,000 multiples and "
            f"{heaping['exact_50000_share']:.1%} are exact R$50,000 multiples. "
            f"The second share divided by one fifth of the first is {heaping_ratio}.",
            _audit_report_table(heaping["bin_widths"]),
            "**Quarterly neighbourhood medians.** Relative widths divide interval width by "
            "the sample median. Block-face draws take all records from each selected face. "
            "Quarterly intervals and counts are in [diagnostics.json](diagnostics.json).",
            _audit_report_table(uncertainty["neighbourhoods"], precision=".1%"),
        )
    )


def _audit_clustering_section(stability: TrajectoryStability) -> str:
    boot = stability["bootstrap"]
    rows = [
        (k, _audit_display(silhouette))
        for k, silhouette in stability["published_silhouettes"].items()
    ]
    silhouettes = _markdown_rows(("k", "Silhouette"), rows)
    sizes = _markdown_rows(
        ("Published group", "Neighbourhoods"), sorted(stability["published_sizes"].items())
    )
    return "\n\n".join(
        (
            "## Clustering stability and composition check",
            "The published trajectories index annual apartment medians to the first year.",
            sizes,
            silhouettes,
            f"**Sampling instability.** Across {boot['draws']} draws, the adjusted Rand index "
            f"against the published partition has median {boot['ari_median']:.3f}, "
            f"P10 {boot['ari_p10']:.3f} and P90 {boot['ari_p90']:.3f}. The endpoint "
            f"bootstrap SE has median {boot['endpoint_se_median']:.2f} and "
            f"P90 {boot['endpoint_se_p90']:.2f} index points. Resampling records independently "
            "omits within-cell dependence and is likely to overstate stability.",
            "**Representation dependence.** All representations use the same K-means settings.",
            _audit_report_table(pd.DataFrame(stability["representations"])),
            f"**Composition check.** The ratio of {END_YEAR} to {START_YEAR} apartment medians "
            "is indexed to 100 for all apartments and for the subset excluding the new "
            "age band. "
            "The table gives the median ratio in each published group. Neighbourhood ratios, "
            "endpoint counts, small-cell flags and membership are in "
            "[diagnostics.json](diagnostics.json).",
            _audit_report_table(pd.DataFrame(stability["group_composition"]), precision=".2f"),
        )
    )


def _audit_patterns_section(evidence: AuditPatterns) -> str:
    metadata = evidence["metadata"]
    alternative = evidence["alternative"]
    alternative_sizes = " / ".join(str(alternative["sizes"][name]) for name in PATTERN_ORDER)
    switches = ", ".join(name.title() for name in alternative["stable_rising_switches"])
    other = ", ".join(name.title() for name in alternative["other_switches"])
    near_tie = (
        f"The chosen fit has inertia {metadata['inertia']:.10f} and the {alternative_sizes} "
        f"alternative has inertia {alternative['inertia']:.10f}"
    )
    if switches:
        near_tie += f", with {switches} switching between stable and rising"
    if other:
        near_tie += f" and {other} switching assignment elsewhere"
    summaries = pd.DataFrame(
        [{"pattern": name, **metadata["patterns"][name]} for name in PATTERN_ORDER]
    )
    records_firm = {name: metadata["patterns"][name]["firm"] for name in PATTERN_ORDER}
    block = evidence["block_face"]
    stability = pd.DataFrame(
        [
            {
                "resampling": scheme,
                "ARI P10": result["ari_p10"],
                "ARI median": result["ari_median"],
                "ARI P90": result["ari_p90"],
                **{f"{name} firm": firm[name] for name in PATTERN_ORDER},
            }
            for scheme, result, firm in (
                ("Independent records", metadata, records_firm),
                ("Block faces", block, block["firm"]),
            )
        ]
    )
    return "\n\n".join(
        (
            "## Trajectory patterns",
            f"> {TRAJECTORY_PATTERNS_CONTEXT}",
            f"{near_tie}.",
            _audit_report_table(summaries),
            _audit_report_table(stability),
            "Block faces are resampled within each neighbourhood and biennium, with unmatched "
            "records treated as singleton faces. See [trajectory_patterns.json]"
            "(trajectory_patterns.json) for the full estimates and membership shares.",
        )
    )


def _render_audit_report(manifest: AuditManifest, outputs: _AuditOutputs) -> str:
    return (
        "\n\n".join(
            (
                "# Robustness audit of the Belo Horizonte ITBI dashboard",
                _audit_provenance_section(manifest),
                TARGET_AND_POPULATION.strip(),
                _audit_protocol_section(outputs.sensitivity.specifications),
                _audit_specification_sections(outputs.sensitivity),
                _audit_exclusion_section(outputs.sensitivity),
                _audit_huber_section(outputs),
                _audit_descriptive_section(outputs.diagnostics),
                _audit_clustering_section(outputs.diagnostics["clustering"]),
                _audit_patterns_section(outputs.patterns),
                INTERPRETATION.strip(),
                LIMITATIONS.strip(),
            )
        )
        + "\n"
    )


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
