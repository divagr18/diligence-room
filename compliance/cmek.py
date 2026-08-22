"""CMEK helpers (BUILD_PLAN D11-M3).

Pure config loader + audit-log shape checker. Live application is
`gcloud kms` + `gcloud firestore databases update` guarded behind
`--confirm-live`; offline tests assert the committed YAML files exist
and are shape-valid.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml


def load_keyring(path: str | Path) -> dict[str, object]:
    """Load and return the KMS keyring config at *path*."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return dict(data)


def verify_audit_log(entries: Sequence[Mapping[str, object]]) -> bool:
    """Return True when audit entries contain both CMEK signals."""
    methods = {str(entry.get("methodName", "")) for entry in entries}
    has_create = any("CreateCryptoKey" in method for method in methods)
    has_update = any("UpdateDatabase" in method for method in methods)
    return has_create and has_update
