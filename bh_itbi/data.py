"""Acquire a pinned public dataset and preserve the notebook's eligibility rules.

The prepared cache contains eligible *transactions*, never medians of medians.
Coordinates remain generalised street-face centroids; neighbourhood names are
independent source attributes, rather than inferred geographical boundaries.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parents[1]
REPO_ID = "pracadata/brazil-itbi"
REVISION = "5908d77ed56fc9adb6dbafaf2cb38f34245bcd76"
FILENAME = "data/belo_horizonte_transactions.parquet"
SOURCE_SHA256 = "386a922d539e78538cd31dd21f7f3ed32db7505ecc70d16a683f69aadf7dbe86"
IPCA_BASE = "setembro de 2026"  # DATA_DICTIONARY.md at the pinned revision.
CACHE_VERSION = "v2"
CACHE_DIR = ROOT / "data" / "cache" / f"{CACHE_VERSION}-{REVISION[:12]}"
YEARS = tuple(range(2016, 2026))
PRACA_SETE = (-19.9191, -43.9386)
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


class DataError(ValueError):
    """The source cannot safely support the documented calculations."""


def prepare_transactions(source: pd.DataFrame) -> pd.DataFrame:
    """Validate and type source records, then apply the notebook's price screen.

    Eligibility matches notebook cell 10 before its date and non-null real-price
    restrictions: apartments/houses, no value flag and nominal R$100–200,000/m²
    inclusive. Positive built area is an additional rule for the diagnostics and
    models, as in cell 15. No imputation, winsorisation or deduplication occurs.
    """
    missing = sorted(set(REQUIRED_COLUMNS) - set(source.columns))
    if missing:
        raise DataError(f"Colunas ausentes na fonte: {', '.join(missing)}")
    frame = source[REQUIRED_COLUMNS].copy()
    if frame["transaction_id"].isna().any() or frame["transaction_id"].duplicated().any():
        raise DataError("A fonte deve conter um identificador único por transação.")
    if not frame["city"].eq("belo_horizonte").all():
        raise DataError("A fonte contém registros de outra cidade.")
    frame["transaction_date"] = pd.to_datetime(
        frame["transaction_date"], format="%Y-%m-%d", errors="coerce"
    )
    if frame["transaction_date"].isna().any():
        raise DataError("A fonte contém datas ausentes ou inválidas.")
    if not frame["transaction_date"].dt.year.eq(frame["year"]).all():
        raise DataError("O ano da fonte não coincide com a data da transação.")
    for column in NUMERIC_COLUMNS:
        numeric = pd.to_numeric(frame[column], errors="coerce").astype(float)
        frame[column] = numeric.where(np.isfinite(numeric))
    frame["neighbourhood"] = frame["neighbourhood"].astype("string").str.strip().str.upper()
    frame["neighbourhood"] = frame["neighbourhood"].replace("", pd.NA)
    frame = frame.loc[
        frame["property_type"].isin(["apartment", "house"])
        & frame["value_flag"].isna()
        & frame["price_per_m2_brl"].between(100, 200_000)
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
    frame["distance_km"] = (2 * 6371.0 * np.arcsin(np.sqrt(a.clip(0, 1)))).where(valid_geo)
    for column in ["property_type", "geo_precision", "building_age_band", "neighbourhood"]:
        frame[column] = frame[column].astype("category")
    return frame.reset_index(drop=True)


def atomic_parquet(frame: pd.DataFrame, destination: Path) -> None:
    """Replace one generated table atomically; never expose a partial Parquet."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, suffix=".parquet", delete=False
    ) as temporary:
        name = Path(temporary.name)
    try:
        frame.to_parquet(name, index=False)
        os.replace(name, destination)
    finally:
        name.unlink(missing_ok=True)


def prepare_cache() -> dict:
    """Fetch the pinned snapshot, verify its published hash and cache typed rows."""
    path = Path(
        hf_hub_download(
            repo_id=REPO_ID, repo_type="dataset", filename=FILENAME, revision=REVISION
        )
    )
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != SOURCE_SHA256:
        raise DataError("O SHA-256 do Parquet não coincide com o manifesto da fonte.")
    source = pd.read_parquet(path, columns=REQUIRED_COLUMNS)
    frame = prepare_transactions(source)
    report = {
        "revision": REVISION,
        "cache_version": CACHE_VERSION,
        "source_sha256": digest,
        "source_rows": len(source),
        "eligible_rows": len(frame),
        "first_date": str(source["transaction_date"].min()),
        "last_date": str(source["transaction_date"].max()),
        "ipca_base": IPCA_BASE,
    }
    atomic_parquet(frame, CACHE_DIR / "transactions.parquet")
    (CACHE_DIR / "source.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    load_transactions.cache_clear()
    return report


def load_source_metadata() -> dict:
    """Return validated metadata for the cached transaction snapshot."""
    path = CACHE_DIR / "transactions.parquet"
    metadata = CACHE_DIR / "source.json"
    if not path.exists() or not metadata.exists():
        prepare_cache()
    report = json.loads(metadata.read_text(encoding="utf-8"))
    if report.get("revision") != REVISION or report.get("cache_version") != CACHE_VERSION:
        raise DataError("Cache incompatível. Execute novamente a preparação dos dados.")
    return report


@lru_cache(maxsize=1)
def load_transactions() -> pd.DataFrame:
    """Load once per server process; subsequent callbacks share read-only rows."""
    load_source_metadata()
    return pd.read_parquet(CACHE_DIR / "transactions.parquet")
