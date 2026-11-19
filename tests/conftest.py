"""Small deterministic records exercise boundary cases, never supply app data."""

from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from threadpoolctl import threadpool_limits

from bh_itbi import models
from bh_itbi.data import prepare_transactions

PRACA_SETE_COORDS = (-19.9191, -43.9386)
SNAPSHOT_YEARS = tuple(range(2016, 2026))
FULL_NEIGHBOURHOODS = (
    "SAVASSI",
    "LOURDES",
    "BURITIS",
    "CASTELO",
    "FUNCIONARIOS",
    "SANTO AGOSTINHO",
    "ANCHIETA",
)
MEDIUM_NEIGHBOURHOODS = (
    "CENTRO",
    "SION",
    "SERRA",
    "CARMO",
    "CRUZEIRO",
    "GUTIERREZ",
    "GRAJAU",
    "CIDADE JARDIM",
    "BELVEDERE",
    "MANGABEIRAS",
    "SANTA EFIGENIA",
    "FLORESTA",
    "PADRE EUSTAQUIO",
    "CARLOS PRATES",
    "CAICARA",
    "PAMPULHA",
)
SMALL_NEIGHBOURHOODS = (
    ("SANTA TEREZA", 12),
    ("PRADO", 9),
    ("HORTO", 7),
    ("LAGOINHA", 5),
)
AGE_BANDS = ("new", "3_10", "11_25", "26_plus")
AGE_EFFECT = {"new": 0.28, "3_10": 0.16, "11_25": 0.07, "26_plus": 0.0}


@pytest.fixture
def source_factory():
    def make(n: int = 40) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "transaction_id": f"test-{i}",
                    "city": "belo_horizonte",
                    "transaction_date": f"2016-01-{i % 28 + 1:02d}",
                    "year": 2016,
                    "property_type": "apartment",
                    "neighbourhood": "SAVASSI" if i % 2 else "LOURDES",
                    "building_age_band": "26_plus",
                    "value_flag": None,
                    "geo_precision": "face_centroid",
                    "value_declared_brl": Decimal(100_000 + i * 1000),
                    "value_tax_base_brl": Decimal(120_000),
                    "value_declared_brl_real": Decimal(200_000 + i * 2000),
                    "built_area_m2": Decimal(100),
                    "price_per_m2_brl": Decimal(1000 + i * 10),
                    "price_per_m2_brl_real": Decimal(2000 + i * 20),
                    "lat": -19.9191,
                    "lon": -43.9386,
                }
                for i in range(n)
            ]
        )

    return make


@dataclass
class _RecordSpec:
    year: int
    month: int
    day: int
    property_type: str
    neighbourhood: str
    age_band: str
    distance_km: float
    area_m2: float
    real_m2: float
    nominal_factor: float
    tax_ratio: float
    geocoded: bool = True
    round_price: bool = False


class _SnapshotBuilder:
    def __init__(self, seed: int = 20260418) -> None:
        self.rng = np.random.default_rng(seed)
        self.records: list[dict[str, object]] = []

    def add(self, spec: _RecordSpec) -> None:
        tx_id = len(self.records) + 1
        nom_m2 = float(np.clip(spec.real_m2 * spec.nominal_factor, 120.0, 180_000.0))
        eff_area = spec.area_m2 if spec.area_m2 > 0 else 80.0
        declared = nom_m2 * eff_area
        real_m2 = spec.real_m2
        if spec.round_price:
            multiple = float(
                np.clip(np.round(declared / 50_000.0) * 50_000.0, 100_000.0, 950_000.0)
            )
            declared = multiple + float(self.rng.integers(-1800, 1801))
            if spec.area_m2 > 0:
                nom_m2 = declared / spec.area_m2
                real_m2 = nom_m2 / spec.nominal_factor
        declared_real = declared / spec.nominal_factor
        tax_base = declared * spec.tax_ratio
        angle = (tx_id * 0.6180339887) * 2 * np.pi
        lat = PRACA_SETE_COORDS[0] + (spec.distance_km / 111.195) * np.cos(angle)
        lon_scale = 111.195 * np.cos(np.radians(PRACA_SETE_COORDS[0]))
        lon = PRACA_SETE_COORDS[1] + (spec.distance_km / lon_scale) * np.sin(angle)
        self.records.append(
            {
                "transaction_id": f"snap-{tx_id:05d}",
                "city": "belo_horizonte",
                "transaction_date": f"{spec.year:04d}-{spec.month:02d}-{spec.day:02d}",
                "year": spec.year,
                "property_type": spec.property_type,
                "neighbourhood": spec.neighbourhood,
                "building_age_band": spec.age_band,
                "value_flag": None,
                "geo_precision": "face_centroid" if spec.geocoded else "postcode_centroid",
                "value_declared_brl": round(declared, 2),
                "value_tax_base_brl": round(tax_base, 2),
                "value_declared_brl_real": round(declared_real, 2),
                "built_area_m2": round(spec.area_m2, 2),
                "price_per_m2_brl": round(nom_m2, 2),
                "price_per_m2_brl_real": round(real_m2, 2),
                "lat": round(float(lat), 6),
                "lon": round(float(lon), 6),
            }
        )

    def add_full_neighbourhoods(self) -> None:
        band_choices = (0.5, 2.5, 5.5, 9.5)
        for n_idx, neigh in enumerate(FULL_NEIGHBOURHOODS):
            base_log = 8.45 + 0.08 * (6 - n_idx)
            for y_idx, year in enumerate(SNAPSHOT_YEARS):
                self._add_full_year_apartments(n_idx, neigh, y_idx, year, band_choices)
                self._add_full_year_houses(n_idx, neigh, y_idx, year, base_log)

    def _add_full_year_apartments(
        self,
        n_idx: int,
        neigh: str,
        y_idx: int,
        year: int,
        band_choices: tuple[float, ...],
    ) -> None:
        base_log = 8.45 + 0.08 * (6 - n_idx)
        trend_slope = 0.016 * ((n_idx % 4) - 1.2) + 0.006 * (n_idx // 4)
        nom_factor = 0.62 + 0.038 * y_idx
        n_apts = 54 if (neigh == "SAVASSI" and year == 2024) else 32
        for j in range(n_apts):
            month = (j % 2) + 1 if j < 22 else 3 + (j % 10)
            day = int(self.rng.integers(1, 28))
            if neigh == "SAVASSI" and year == 2024:
                age_band = "3_10" if j < 6 else ("new", "11_25", "26_plus")[j % 3]
            else:
                age_band = AGE_BANDS[(j + y_idx + n_idx) % 4]
            area = float(
                np.exp(self.rng.normal(4.45 + 0.04 * (3 - n_idx % 4) - 0.02 * y_idx, 0.22))
            )
            nonlinear = 0.045 * np.sin((y_idx / 9.0) * np.pi * (1 + (n_idx % 3)))
            log_p = (
                base_log
                + trend_slope * y_idx
                + nonlinear
                + AGE_EFFECT[age_band]
                - 0.18 * (np.log(area) - 4.4)
                + self.rng.normal(0, 0.09)
            )
            dist = band_choices[(j + n_idx) % 4] + float(self.rng.uniform(-0.35, 0.35))
            if j == n_apts - 1:
                dist = float(self.rng.uniform(0.2, 14.5))
            tax_ratio = 1.15 if (j % 3 == 0) else (0.0 if j == 31 else 0.92)
            self.add(
                _RecordSpec(
                    year=year,
                    month=month,
                    day=day,
                    property_type="apartment",
                    neighbourhood=neigh,
                    age_band=age_band,
                    distance_km=dist,
                    area_m2=area,
                    real_m2=float(np.exp(log_p)),
                    nominal_factor=nom_factor,
                    tax_ratio=tax_ratio,
                    geocoded=(j < 12),
                    round_price=(j % 3 == 0),
                )
            )

    def _add_full_year_houses(
        self, n_idx: int, neigh: str, y_idx: int, year: int, base_log: float
    ) -> None:
        nom_factor = 0.62 + 0.038 * y_idx
        n_houses = 16 if year in (2016, 2017) else 6
        for j in range(n_houses):
            month = (j % 3) + 1 if j < 15 else 4 + (j % 8)
            # Vary the quarterly type mix so a composition contrast does not
            # depend on the sign of round-off around an exact zero.
            if month == 11 and (n_idx + y_idx) % 5 < 2:
                month = 8
            day = int(self.rng.integers(1, 28))
            age_band = AGE_BANDS[(j + y_idx) % 4]
            area = float(np.exp(self.rng.normal(5.1 + 0.03 * (n_idx % 3), 0.25)))
            log_p = (
                base_log
                - 0.22
                + 0.012 * y_idx
                + AGE_EFFECT[age_band]
                + self.rng.normal(0, 0.11)
            )
            dist = float(np.clip(1.5 + 1.6 * n_idx + self.rng.normal(0, 0.4), 0.4, 13.8))
            tax_ratio = 1.12 if (j % 2 == 0) else 0.88
            self.add(
                _RecordSpec(
                    year=year,
                    month=month,
                    day=day,
                    property_type="house",
                    neighbourhood=neigh,
                    age_band=age_band,
                    distance_km=dist,
                    area_m2=area,
                    real_m2=float(np.exp(log_p)),
                    nominal_factor=nom_factor,
                    tax_ratio=tax_ratio,
                    geocoded=(j < 3),
                    round_price=(j % 2 == 0),
                )
            )

    def add_medium_neighbourhoods(self) -> None:
        for m_idx, neigh in enumerate(MEDIUM_NEIGHBOURHOODS):
            n_rows = 42 if neigh == "CENTRO" else (18 + (m_idx % 24))
            for j in range(n_rows):
                if neigh == "CENTRO" and j < 24:
                    year = 2024
                    prop_type = "apartment"
                    age_band = "3_10" if j < 4 else ("new", "11_25", "26_plus")[j % 3]
                else:
                    recent = j < int(n_rows * 0.75)
                    year = 2023 + (j % 3) if recent else SNAPSHOT_YEARS[j % len(SNAPSHOT_YEARS)]
                    prop_type = "apartment" if (j % 5 != 0) else "house"
                    age_band = AGE_BANDS[(j + m_idx) % 4]
                month = (j % 12) + 1
                day = int(self.rng.integers(1, 28))
                zero_area = j == n_rows - 1 and m_idx % 3 == 0
                area = 0.0 if zero_area else float(np.exp(self.rng.normal(4.35, 0.25)))
                nom_factor = 0.62 + 0.038 * (year - 2016)
                log_p = (
                    8.15 + 0.03 * (m_idx % 5) + AGE_EFFECT[age_band] + self.rng.normal(0, 0.12)
                )
                dist = float(
                    np.clip(0.5 + (m_idx % 14) + self.rng.uniform(-0.3, 0.3), 0.2, 13.8)
                )
                self.add(
                    _RecordSpec(
                        year=year,
                        month=month,
                        day=day,
                        property_type=prop_type,
                        neighbourhood=neigh,
                        age_band=age_band,
                        distance_km=dist,
                        area_m2=area,
                        real_m2=float(np.exp(log_p)),
                        nominal_factor=nom_factor,
                        tax_ratio=1.10 if (j % 3 == 0) else 0.90,
                        geocoded=(j < 6),
                        round_price=(j % 4 == 0),
                    )
                )

    def add_small_neighbourhoods(self) -> None:
        for s_idx, (neigh, count) in enumerate(SMALL_NEIGHBOURHOODS):
            for j in range(count):
                year = 2022 + (j % 4)
                month = (j * 3) % 12 + 1
                day = int(self.rng.integers(1, 28))
                age_band = AGE_BANDS[(j + s_idx) % 4]
                area = float(np.exp(self.rng.normal(4.3, 0.2)))
                nom_factor = 0.62 + 0.038 * (year - 2016)
                log_p = 8.05 + 0.04 * s_idx + AGE_EFFECT[age_band] + self.rng.normal(0, 0.1)
                dist = float(np.clip(2.0 + s_idx * 2.5, 0.5, 13.0))
                self.add(
                    _RecordSpec(
                        year=year,
                        month=month,
                        day=day,
                        property_type="apartment",
                        neighbourhood=neigh,
                        age_band=age_band,
                        distance_km=dist,
                        area_m2=area,
                        real_m2=float(np.exp(log_p)),
                        nominal_factor=nom_factor,
                        tax_ratio=0.95,
                        geocoded=(j < 3),
                    )
                )


def make_snapshot_source() -> pd.DataFrame:
    """Build a deterministic synthetic source covering every dashboard code path."""
    builder = _SnapshotBuilder()
    builder.add_full_neighbourhoods()
    builder.add_medium_neighbourhoods()
    builder.add_small_neighbourhoods()
    return pd.DataFrame(builder.records)


@pytest.fixture(scope="session")
def snapshot_frame() -> pd.DataFrame:
    return prepare_transactions(make_snapshot_source())


@pytest.fixture(scope="session")
def snapshot_models(tmp_path_factory: pytest.TempPathFactory, snapshot_frame: pd.DataFrame):
    model_dir = tmp_path_factory.mktemp("snapshot_models")
    with patch.object(models, "MODEL_DIR", model_dir), threadpool_limits(limits=1):
        models.prepare_models(snapshot_frame, force=True)
        return models.load_models(model_dir)
