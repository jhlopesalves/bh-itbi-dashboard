"""Canonical encoding and digests for local dashboard snapshots."""

import hashlib
import json
from typing import Any


def snapshot_json(payload: Any) -> str:
    """Encode the canonicalised payload as stable UTF-8 JSON."""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def snapshot_digest(content: str) -> str:
    """Fingerprint a canonical JSON document without storing it in Git."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
