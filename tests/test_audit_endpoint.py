"""Check the read-only audit endpoint used by the models tab."""

import json
from pathlib import Path

import pytest

from bh_itbi.config import (
    AUDIT_EVIDENCE_DIR,
    AUDIT_PROTOCOL_ID,
    AUDIT_PROTOCOL_SHA256,
    REVISION,
)
from bh_itbi.data import DataError
from bh_itbi.models import load_audit_endpoint
from bh_itbi.sensitivity import PROTOCOL


def test_protocol_hash_matches_committed_evidence() -> None:
    manifest = json.loads((AUDIT_EVIDENCE_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert AUDIT_PROTOCOL_SHA256 == PROTOCOL.sha256 == manifest["protocol_sha256"]


@pytest.mark.parametrize("missing", ["manifest.json", "specifications.csv", None])
def test_audit_endpoint_omits_missing_evidence(tmp_path: Path, missing: str | None) -> None:
    if missing is not None:
        present = "specifications.csv" if missing == "manifest.json" else "manifest.json"
        (tmp_path / present).touch()
    assert load_audit_endpoint(tmp_path) is None


@pytest.mark.parametrize("key", ["revision", "protocol_id", "protocol_sha256"])
def test_audit_endpoint_rejects_stale_evidence(tmp_path: Path, key: str) -> None:
    manifest = {
        "revision": REVISION,
        "protocol_id": AUDIT_PROTOCOL_ID,
        "protocol_sha256": AUDIT_PROTOCOL_SHA256,
    }
    manifest[key] = "different"
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "specifications.csv").touch()
    with pytest.raises(DataError, match=rf"{key} mismatch.*Regenerate the audit evidence"):
        load_audit_endpoint(tmp_path)


def test_audit_endpoint_matches_published_evidence() -> None:
    endpoint = load_audit_endpoint()
    assert endpoint is not None and endpoint["quarter"] == "2025Q4"
    assert endpoint["published"] == pytest.approx(110.04, abs=0.005)
    assert endpoint["robust"] == pytest.approx(105.44, abs=0.005)
    assert endpoint["robust_lower"] == pytest.approx(102.57, abs=0.005)
    assert endpoint["robust_upper"] == pytest.approx(108.38, abs=0.005)
