"""Small deterministic records exercise boundary cases, never supply app data."""

from decimal import Decimal

import pandas as pd
import pytest


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
