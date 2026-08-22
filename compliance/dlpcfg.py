"""DLP helpers (BUILD_PLAN D11-M9).

Pure inspection-template loader + HR-path redaction. Live application is
`gcloud dlp inspect-templates create` guarded behind `--confirm-live`;
offline tests assert the committed YAML exists and is shape-valid and that
the redaction is deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from ingestion.sentinel import FakeSentinel, heavy_pii


@dataclass(frozen=True, slots=True)
class InspectionTemplate:
    """Parsed DLP inspection template (subset)."""

    template_id: str
    display_name: str
    info_types: tuple[str, ...]
    min_likelihood: str


def load_template(path: str | Path) -> InspectionTemplate:
    """Load and return the DLP inspection template at *path*."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return InspectionTemplate(
        template_id=str(data["template_id"]),
        display_name=str(data["display_name"]),
        info_types=tuple(str(item) for item in data["info_types"]),
        min_likelihood=str(data["min_likelihood"]),
    )


_PII_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"\(\d{3}\)\s?\d{3}-\d{4}|\b\d{3}-\d{3}-\d{4}\b"), "[PHONE]"),
)


def trigger_on(text: str, doc_type: str | None = None) -> bool:
    """Return True when *text* should be redacted before agent context."""
    if doc_type == "hr_roster":
        return True
    sentinel = FakeSentinel()
    spans = sentinel.mark_pii_spans(text)
    return heavy_pii(spans)


def redact(text: str) -> str:
    """Redact PII spans in *text* to stable tokens."""
    result = text
    for pattern, token in _PII_REPLACEMENTS:
        result = pattern.sub(token, result)
    return result
