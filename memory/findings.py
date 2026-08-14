"""Finding domain model (BUILD_PLAN D1-M4, vision §9 + §19.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from registry.models import Workstream


class FindingSeverity(StrEnum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingStatus(StrEnum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


@dataclass(frozen=True, slots=True)
class Evidence:
    verbatim_span: str
    document_id: str
    chunk_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.verbatim_span.strip():
            raise ValueError("evidence verbatim_span must be non-empty text")
        if not self.document_id:
            raise ValueError("evidence document_id must be set")


@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: str
    deal_id: str
    workstream: Workstream
    title: str
    summary: str
    severity: FindingSeverity
    confidence: float
    status: FindingStatus
    evidence: tuple[Evidence, ...]
    owner: str
    created_at: datetime
    updated_at: datetime
    source_documents: tuple[str, ...] = ()
    related_findings: tuple[str, ...] = ()
    affected_entities: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
    audit_trace_id: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        if not self.evidence:
            raise ValueError("finding requires at least one evidence entry (vision §19.2)")
