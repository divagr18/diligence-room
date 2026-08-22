"""VPC-SC helpers (BUILD_PLAN D11-M8).

Pure config loader + audit-log shape checker. Live application is
`gcloud access-context-manager perimeters create/update` guarded behind
`--confirm-live`; offline tests assert the committed YAML exists and is
shape-valid.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def perimeter_from_yaml(path: str | Path) -> dict[str, object]:
    """Load and return the VPC-SC perimeter config at *path*."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return dict(data)


def check_violation(entry: dict[str, object]) -> bool:
    """Return True when *entry* represents a VPC-SC denied storage get."""
    method = str(entry.get("methodName", ""))
    if "storage.objects.get" not in method:
        return False
    status = entry.get("status")
    if isinstance(status, dict):
        code = status.get("code")
        message = str(status.get("message", ""))
        if code == 7 or "PERMISSION_DENIED" in message or "permission_denied" in message.lower():
            return True
    # Fallback: look for permission-denied signals in the entry payload
    text = str(entry)
    return "PERMISSION_DENIED" in text or "permission_denied" in text.lower()
