"""Finding domain model and persistence store (BUILD_PLAN D1-M4 / D3-M6)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, cast

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

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


class FindingNotFoundError(KeyError):
    """Raised when a finding document does not exist in Firestore."""


class DuplicateFindingError(ValueError):
    """Raised when creating a finding whose document already exists."""


def findings_to_doc(finding: Finding) -> dict[str, Any]:
    """Serialize a Finding to a Firestore-compatible document dict."""
    return {
        "finding_id": finding.finding_id,
        "deal_id": finding.deal_id,
        "workstream": finding.workstream.value,
        "title": finding.title,
        "summary": finding.summary,
        "severity": finding.severity.value,
        "confidence": finding.confidence,
        "status": finding.status.value,
        "evidence": [
            {
                "verbatim_span": e.verbatim_span,
                "document_id": e.document_id,
                "chunk_ref": e.chunk_ref,
            }
            for e in finding.evidence
        ],
        "source_documents": list(finding.source_documents),
        "related_findings": list(finding.related_findings),
        "affected_entities": list(finding.affected_entities),
        "questions": list(finding.questions),
        "owner": finding.owner,
        "created_at": finding.created_at,
        "updated_at": finding.updated_at,
        "audit_trace_id": finding.audit_trace_id,
    }


def finding_from_doc(doc: dict[str, Any]) -> Finding:
    """Deserialize a Firestore document dict back into a Finding."""
    return Finding(
        finding_id=str(doc["finding_id"]),
        deal_id=str(doc["deal_id"]),
        workstream=Workstream(doc["workstream"]),
        title=str(doc["title"]),
        summary=str(doc["summary"]),
        severity=FindingSeverity(doc["severity"]),
        confidence=float(doc["confidence"]),
        status=FindingStatus(doc["status"]),
        evidence=tuple(
            Evidence(
                verbatim_span=str(e["verbatim_span"]),
                document_id=str(e["document_id"]),
                chunk_ref=e.get("chunk_ref"),
            )
            for e in doc["evidence"]
        ),
        source_documents=tuple(doc.get("source_documents", ())),
        related_findings=tuple(doc.get("related_findings", ())),
        affected_entities=tuple(doc.get("affected_entities", ())),
        questions=tuple(doc.get("questions", ())),
        owner=str(doc["owner"]),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        audit_trace_id=doc.get("audit_trace_id"),
    )


class FindingsStore:
    """Firestore-backed CRUD for findings at deals/{deal_id}/findings/{fid}."""

    def __init__(self, client: firestore.Client) -> None:
        self._client = client

    def _findings_collection(self, deal_id: str) -> firestore.CollectionReference:
        return cast(
            firestore.CollectionReference,
            self._client.collection("deals").document(deal_id).collection("findings"),
        )

    def create(self, finding: Finding) -> None:
        if not finding.evidence:
            raise ValueError("finding requires at least one evidence entry")
        doc_ref = self._findings_collection(finding.deal_id).document(finding.finding_id)
        if doc_ref.get().exists:
            raise DuplicateFindingError(f"finding {finding.finding_id} already exists")
        doc_ref.set(findings_to_doc(finding))

    def get(self, deal_id: str, finding_id: str) -> Finding:
        snapshot = self._findings_collection(deal_id).document(finding_id).get()
        if not snapshot.exists:
            raise FindingNotFoundError(finding_id)
        data = snapshot.to_dict()
        assert data is not None
        return finding_from_doc(data)

    def update(self, finding: Finding) -> None:
        doc_ref = self._findings_collection(finding.deal_id).document(finding.finding_id)
        if not doc_ref.get().exists:
            raise FindingNotFoundError(finding.finding_id)
        doc_ref.set(findings_to_doc(finding))

    def list_for_workstream(self, deal_id: str, workstream: Workstream | str) -> list[Finding]:
        ws_value = (
            workstream.value if isinstance(workstream, Workstream) else Workstream(workstream).value
        )
        docs = (
            self._findings_collection(deal_id)
            .where(filter=FieldFilter("workstream", "==", ws_value))
            .stream()
        )
        results: list[Finding] = []
        for doc in docs:
            data = doc.to_dict()
            assert data is not None
            results.append(finding_from_doc(data))
        return results
