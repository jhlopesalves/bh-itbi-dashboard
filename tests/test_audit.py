"""Exercise the audit's cache verification, bootstrap, outputs and command entry point."""

import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bh_itbi import data, models, patterns
from bh_itbi.audit import (
    AuditError,
    AuditInputs,
    AuditSettings,
    run_audit,
)
from bh_itbi.config import REVISION, ROOT, SOURCE_SHA256
from bh_itbi.resampling import _block_face_codes, _block_face_medians
from bh_itbi.sensitivity import PROTOCOL

FILES = {
    "manifest.json",
    "protocol.json",
    "specifications.csv",
    "index_trajectories.csv",
    "decomposition.csv",
    "exclusions.csv",
    "huber_weights.csv",
    "diagnostics.json",
    "report.md",
    "index_comparison.svg",
    "trajectory_patterns.json",
}


@pytest.fixture
def audit_inputs(snapshot_frame, monkeypatch) -> AuditInputs:
    monkeypatch.setattr(patterns, "PATTERN_DRAWS", 8)
    frame = snapshot_frame.copy()
    # The dashboard fixture deliberately has invalid tax bases and sparse
    # late-quarter house cells. Give the audit a feasible synthetic population.
    frame["value_tax_base_brl"] = frame["value_tax_base_brl"].where(
        frame["value_tax_base_brl"].gt(0), frame["value_declared_brl"]
    )
    population = models.model_population(frame)
    apartments = population.loc[population["property_type"].eq("apartment")]
    houses = (
        apartments.groupby(["quarter", "neighbourhood"], observed=True)
        .head(1)
        .loc[:, frame.columns]
        .assign(property_type="house")
    )
    return AuditInputs(
        frame=pd.concat([frame, houses], ignore_index=True),
        provenance={
            "revision": "synthetic",
            "source_sha256": "synthetic-source",
            "transactions_sha256": "synthetic-table",
            "cached_table_verified": False,
        },
    )


def test_audit_writes_exactly_the_required_outputs_deterministically(
    tmp_path: Path, audit_inputs: AuditInputs
) -> None:
    settings = AuditSettings(cluster_draws=4, median_draws=8)
    a, b = [tmp_path / name for name in ("a", "b")]
    manifest = run_audit(a, inputs=audit_inputs, settings=settings)
    assert manifest == run_audit(b, inputs=audit_inputs, settings=settings)
    assert {path.name for path in a.iterdir()} == {path.name for path in b.iterdir()} == FILES
    for name in FILES:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name
    assert not manifest["protocol_settings"]
    assert (
        manifest["protocol_sha256"] == data.file_sha256(a / "protocol.json") == PROTOCOL.sha256
    )
    assert json.loads((a / "manifest.json").read_text(encoding="utf-8")) == manifest
    summary = pd.read_csv(a / "specifications.csv")
    assert len(summary) == 18
    assert all("rank" not in column and "prefer" not in column for column in summary.columns)
    report = (a / "report.md").read_text(encoding="utf-8")
    assert report.startswith("# How robust is the price index?\n")
    assert "](index_comparison.svg)" in report
    for name in FILES - {"report.md"}:
        assert f"[{name}]({name})" in report, name
    for prohibited in ("preferred", "best", "corrected", "true index", "reported as such"):
        assert prohibited not in report.lower()
    figure = (a / "index_comparison.svg").read_text(encoding="utf-8")
    assert figure.startswith("<svg ") and figure.count("<polyline") == 4


def test_losing_a_quarter_raises_audit_error(tmp_path: Path, audit_inputs: AuditInputs) -> None:
    frame = audit_inputs.frame.loc[audit_inputs.frame["quarter"].ne(pd.Timestamp(2016, 1, 1))]
    with pytest.raises(AuditError, match=r"baseline.*2016Q1"):
        run_audit(tmp_path / "audit", inputs=replace(audit_inputs, frame=frame))


@pytest.mark.parametrize(
    ("revision", "digest", "match"),
    [
        (REVISION, "other-table", "SHA-256 mismatch"),
        ("other-revision", "table", "pinned revision"),
    ],
)
def test_audit_rejects_incompatible_cache_provenance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, revision: str, digest: str, match: str
) -> None:
    def source_metadata(*, allow_prepare: bool) -> dict[str, str]:
        assert allow_prepare is False
        return {
            "revision": revision,
            "source_sha256": SOURCE_SHA256,
            "transactions_sha256": "table",
        }

    def unexpected_input(*_args: object, **_kwargs: object) -> None:
        pytest.fail("The audit reached a data load after provenance verification failed.")

    monkeypatch.setattr(data, "load_source_metadata", source_metadata)
    monkeypatch.setattr(data, "file_sha256", lambda _path: digest)
    monkeypatch.setattr(data, "load_transactions", unexpected_input)
    monkeypatch.setattr(models, "load_models", unexpected_input)
    with pytest.raises(data.DataError, match=match) as raised:
        run_audit(tmp_path / "audit")
    assert "uv run python main.py prepare" in str(raised.value)
    assert not (tmp_path / "audit").exists()


def test_block_face_draws_keep_whole_faces_and_singletons() -> None:
    rows = pd.DataFrame(
        {
            "face_geocoded": [True, True, False, False],
            "lat": [-19.92, -19.92000001, -19.92, -19.92],
            "lon": [-43.96] * 4,
        }
    )
    codes = _block_face_codes(rows)
    np.testing.assert_array_equal(codes, [2, 2, 1, 0])

    class Draw:
        multinomial: Callable[..., np.ndarray] = staticmethod(
            lambda *_args, **_kwargs: np.array([[0, 0, 3], [1, 0, 2], [1, 2, 0]])
        )

    actual = _block_face_medians(np.array([10.0, 100.0, 20.0, 30.0]), codes, Draw(), 3)
    np.testing.assert_array_equal(actual, [55.0, 30.0, 20.0])


def test_command_help_does_not_import_audit() -> None:
    script = """
import sys
import main
sys.argv = ["main.py", "--help"]
try:
    main.main()
except SystemExit as error:
    assert error.code == 0
else:
    raise AssertionError("Expected argparse to handle --help")
assert "bh_itbi.audit" not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "{serve,prepare,audit}" in result.stdout
