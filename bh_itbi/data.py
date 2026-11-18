"""Download, validate, screen and cache the pinned ITBI transaction snapshot."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict

import numpy as np
import pandas as pd

from bh_itbi.config import (
    CACHE_DIR,
    CACHE_VERSION,
    EARTH_RADIUS_KM,
    FILENAME,
    IPCA_BASE,
    PRACA_SETE,
    PRICE_PER_M2_MAX,
    PRICE_PER_M2_MIN,
    REPO_ID,
    RESIDENTIAL_TYPES,
    REVISION,
    ROOT,
    SOURCE_SHA256,
    YEARS,
)

__all__ = [
    "CACHE_DIR",
    "CACHE_VERSION",
    "FILENAME",
    "IPCA_BASE",
    "PRACA_SETE",
    "REPO_ID",
    "REVISION",
    "ROOT",
    "SOURCE_SHA256",
    "TRANSACTION_COLUMNS",
    "YEARS",
    "DataError",
    "SourceMetadata",
    "atomic_json",
    "atomic_parquet",
    "atomic_write",
    "file_sha256",
    "load_source_metadata",
    "load_transactions",
    "prepare_cache",
    "prepare_transactions",
]
NUMERIC_COLUMNS = [
    "value_declared_brl",
    "value_tax_base_brl",
    "value_declared_brl_real",
    "built_area_m2",
    "price_per_m2_brl",
    "price_per_m2_brl_real",
    "lat",
    "lon",
]
REQUIRED_COLUMNS = [
    "transaction_id",
    "city",
    "transaction_date",
    "year",
    "property_type",
    "neighbourhood",
    "building_age_band",
    "value_flag",
    "geo_precision",
    *NUMERIC_COLUMNS,
]
# Validation still uses every required source field. Only these redundant fields
# are omitted from the generated table; all eligible rows and float64 values stay.
UNUSED_COLUMNS = {
    "transaction_id",
    "city",
    "value_flag",
    "geo_precision",
    "value_declared_brl_real",
}
TRANSACTION_COLUMNS = [c for c in REQUIRED_COLUMNS if c not in UNUSED_COLUMNS] + [
    "month",
    "quarter",
    "face_geocoded",
    "distance_km",
]


class DataError(ValueError):
    """The source cannot safely support the documented calculations."""


class SourceMetadata(TypedDict):
    """Validated provenance and row counts for the cached transaction snapshot."""

    revision: str
    cache_version: str
    source_sha256: str
    source_rows: int
    eligible_rows: int
    first_date: str
    last_date: str
    ipca_base: str
    transactions_sha256: str


def prepare_transactions(source: pd.DataFrame) -> pd.DataFrame:
    """Validate and type source records, then apply the price-eligibility screen.

    The price-eligibility screen retains residential records (apartments and
    houses) with no value flag and nominal price between R$100/m² and
    R$200,000/m² inclusive. The positive-area screen is applied separately by
    diagnostics and models. No imputation, winsorisation or deduplication occurs.
    """
    missing = sorted(set(REQUIRED_COLUMNS) - set(source.columns))
    if missing:
        raise DataError(f"Missing source columns: {', '.join(missing)}")
    frame = source[REQUIRED_COLUMNS].copy()
    if frame["transaction_id"].isna().any() or frame["transaction_id"].duplicated().any():
        raise DataError("The source must have a unique identifier for each transaction.")
    if not frame["city"].eq("belo_horizonte").all():
        raise DataError("The source contains records from another city.")
    frame["transaction_date"] = pd.to_datetime(
        frame["transaction_date"], format="%Y-%m-%d", errors="coerce"
    )
    if frame["transaction_date"].isna().any():
        raise DataError("The source contains missing or invalid dates.")
    if not frame["transaction_date"].dt.year.eq(frame["year"]).all():
        raise DataError("The source year does not match the transaction date.")
    for column in NUMERIC_COLUMNS:
        numeric = pd.to_numeric(frame[column], errors="coerce").astype(float)
        frame[column] = numeric.where(np.isfinite(numeric))
    frame["neighbourhood"] = frame["neighbourhood"].astype("string").str.strip().str.upper()
    frame["neighbourhood"] = frame["neighbourhood"].replace("", pd.NA)
    frame = frame.loc[
        frame["property_type"].isin(RESIDENTIAL_TYPES)
        & frame["value_flag"].isna()
        & frame["price_per_m2_brl"].between(PRICE_PER_M2_MIN, PRICE_PER_M2_MAX)
    ].copy()
    frame["month"] = frame["transaction_date"].dt.to_period("M").dt.start_time
    frame["quarter"] = frame["transaction_date"].dt.to_period("Q").dt.start_time
    valid_geo = (
        frame["geo_precision"].eq("face_centroid")
        & frame["lat"].between(-90, 90)
        & frame["lon"].between(-180, 180)
    )
    frame["face_geocoded"] = valid_geo
    lat = np.radians(frame["lat"])
    lon = np.radians(frame["lon"])
    centre_lat, centre_lon = np.radians(PRACA_SETE)
    a = (
        np.sin((lat - centre_lat) / 2) ** 2
        + np.cos(lat) * np.cos(centre_lat) * np.sin((lon - centre_lon) / 2) ** 2
    )
    frame["distance_km"] = (2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a.clip(0, 1)))).where(
        valid_geo
    )
    for column in ["property_type", "geo_precision", "building_age_band", "neighbourhood"]:
        frame[column] = frame[column].astype("category")
    return frame.reset_index(drop=True)


def atomic_write(destination: Path, write: Callable[[Path], None]) -> None:
    """Write to a sibling temporary file and replace ``destination`` atomically."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, suffix=destination.suffix, delete=False
    ) as temporary:
        name = Path(temporary.name)
    try:
        write(name)
        os.replace(name, destination)
    finally:
        name.unlink(missing_ok=True)


def atomic_parquet(frame: pd.DataFrame, destination: Path) -> None:
    """Replace one generated table atomically; never expose a partial Parquet."""
    atomic_write(destination, lambda path: frame.to_parquet(path, index=False))


def file_sha256(path: Path) -> str:
    """Hash a file without materialising its bytes in memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_json(report: Mapping[str, Any], destination: Path) -> None:
    """Publish a manifest only after its tables have been written successfully."""

    def write(path: Path) -> None:
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    atomic_write(destination, write)


def prepare_cache() -> SourceMetadata:
    """Fetch the pinned snapshot, verify its published hash and cache typed rows."""
    # The serving process needs neither the downloader nor its HTTP dependencies.
    from huggingface_hub import hf_hub_download  # noqa: PLC0415

    path = Path(
        hf_hub_download(
            repo_id=REPO_ID, repo_type="dataset", filename=FILENAME, revision=REVISION
        )
    )
    digest = file_sha256(path)
    if digest != SOURCE_SHA256:
        raise DataError("The Parquet file's SHA-256 does not match the source manifest.")
    source = pd.read_parquet(path, columns=REQUIRED_COLUMNS, use_threads=False)
    frame = prepare_transactions(source)
    frame = frame[TRANSACTION_COLUMNS]
    frame["year"] = pd.to_numeric(frame["year"], downcast="integer")
    table_path = CACHE_DIR / "transactions.parquet"
    atomic_parquet(frame, table_path)
    report: SourceMetadata = {
        "revision": REVISION,
        "cache_version": CACHE_VERSION,
        "source_sha256": digest,
        "source_rows": len(source),
        "eligible_rows": len(frame),
        "first_date": str(source["transaction_date"].min()),
        "last_date": str(source["transaction_date"].max()),
        "ipca_base": IPCA_BASE,
        "transactions_sha256": file_sha256(table_path),
    }
    atomic_json(report, CACHE_DIR / "source.json")
    _read_transactions.cache_clear()
    return report


def load_source_metadata(*, allow_prepare: bool = True) -> SourceMetadata:
    """Return validated metadata for the cached transaction snapshot."""
    path = CACHE_DIR / "transactions.parquet"
    metadata = CACHE_DIR / "source.json"
    if not path.exists() or not metadata.exists():
        if not allow_prepare:
            raise DataError(
                "Prepared data are missing. Run python main.py prepare during the build."
            )
        prepare_cache()
    report = json.loads(metadata.read_text(encoding="utf-8"))
    if (
        report.get("revision") != REVISION
        or report.get("cache_version") != CACHE_VERSION
        or report.get("source_sha256") != SOURCE_SHA256
        or report.get("transactions_sha256") != file_sha256(path)
    ):
        raise DataError("The cache is incompatible. Run data preparation again.")
    return report


@lru_cache(maxsize=1)
def _read_transactions(path: Path) -> pd.DataFrame:
    # Serial decoding bounds Arrow's temporary buffers on the 512 MB instance.
    return pd.read_parquet(path, columns=TRANSACTION_COLUMNS, use_threads=False)


def load_transactions(*, allow_prepare: bool = True) -> pd.DataFrame:
    """Load once per server process; subsequent callbacks share read-only rows."""
    load_source_metadata(allow_prepare=allow_prepare)
    return _read_transactions(CACHE_DIR / "transactions.parquet")
