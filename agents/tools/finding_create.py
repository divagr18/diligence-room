"""Finding-create tool (BUILD_PLAN D6-M1 toolset, vision §9 / §19.2).

Validates the finding JSON contract and enforces evidence integrity: every
``verbatim_span`` must be an actual substring of the cited source document's
parsed text — fabricated or unverifiable evidence is rejected, never stored.
Created findings land in the canonical ``FindingsStore`` AND in the agent's
workstream memory partition (``deals/{deal}/workstreams/{ws}/items/{fid}``).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from google.cloud import firestore

from agents.tools.data_room_read import DocSource
from coordination.escalation import escalate_if_critical
from identity.authz import Action, Resource, can, denial_envelope
from identity.principals import Principal
from ingestion.parsing import LocalParser
from memory.findings import (
    DuplicateFindingError,
    Evidence,
    Finding,
    FindingSeverity,
    FindingsStore,
    FindingStatus,
)
from memory.partitions import partition_collection
from runtime.events import EventEnvelope

_SEVERITIES = frozenset(severity.value for severity in FindingSeverity)

_AUTH_DENIED = "evidence_unauthorized"
_INVALID_CATEGORY = "invalid_category"


class _EventPublisher(Protocol):
    def publish(self, event: EventEnvelope) -> str: ...


def _reject(reason: str, detail: str) -> dict[str, Any]:
    return {"decision": "reject", "reason": reason, "detail": detail}


def _string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _structural_evidence(
    entries: Any,
) -> tuple[tuple[str, str, str | None, str], ...] | None:
    """Validate evidence structure; return (span, document_id, chunk_ref, category).

    Returns None for any structural problem (missing/empty/non-list evidence,
    or an entry lacking a non-empty verbatim_span + document_id + category).
    """
    if not isinstance(entries, list) or not entries:
        return None
    parsed: list[tuple[str, str, str | None, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            return None
        span = entry.get("verbatim_span")
        document_id = entry.get("document_id")
        category = entry.get("category")
        if not isinstance(span, str) or not span.strip():
            return None
        if not isinstance(document_id, str) or not document_id:
            return None
        if not isinstance(category, str) or not category:
            return None
        chunk_ref = entry.get("chunk_ref")
        parsed.append(
            (span, document_id, chunk_ref if isinstance(chunk_ref, str) else None, category)
        )
    return tuple(parsed)


def _authorize_evidence(
    entries: tuple[tuple[str, str, str | None, str], ...],
    principal: Principal,
    publisher: _EventPublisher | None,
) -> str | None:
    """Authorize every cited document; return None when all are readable.

    The evidence gate must not become a read bypass: every cited document is
    checked against agent->data AuthZ exactly like data-room-read. Returns
    ``_INVALID_CATEGORY`` for a category unknown to the ACL matrix, or
    ``_AUTH_DENIED`` when the principal may not read a cited document (a denial
    event is emitted when a publisher is supplied).
    """
    for _span, document_id, _chunk_ref, category in entries:
        try:
            resource = Resource(
                deal_id=principal.deal_id,
                workstream=None,
                category=category,
                name=document_id,
            )
        except ValueError:
            return _INVALID_CATEGORY
        allowed, denial = can(principal, Action.READ, resource)
        if not allowed:
            assert denial is not None  # noqa: S101 — guaranteed by can() contract
            if publisher is not None:
                publisher.publish(denial_envelope(principal, Action.READ, resource, denial))
            return _AUTH_DENIED
    return None


def _verify_spans(
    entries: tuple[tuple[str, str, str | None, str], ...],
    principal: Principal,
    doc_source: DocSource,
) -> tuple[Evidence, ...] | None:
    """Resolve each cited document and confirm the span is a real substring.

    Returns verified Evidence entries, or None when any span is unverifiable
    (document missing, unparseable, needs OCR, or span not present in text).
    """
    verified: list[Evidence] = []
    for span, document_id, chunk_ref, _category in entries:
        blob = doc_source.read(document_id)
        if blob is None:
            return None
        parsed = LocalParser().parse(blob, document_id, principal.deal_id)
        if parsed.text is None or span not in parsed.text:
            return None
        verified.append(Evidence(verbatim_span=span, document_id=document_id, chunk_ref=chunk_ref))
    return tuple(verified)


def make_finding_create(
    principal: Principal,
    client: firestore.Client,
    doc_source: DocSource,
    now: datetime | None = None,
    publisher: _EventPublisher | None = None,
) -> Any:
    """Bind the finding-create tool to *principal* (one agent, one deal)."""
    store = FindingsStore(client)

    def finding_create(finding_json: str) -> dict[str, Any]:
        """Create an evidence-gated finding for this agent's workstream.

        Args:
            finding_json: One JSON object following the finding contract:
                title, summary, severity (informational|low|medium|high|
                critical), confidence (0.0-1.0), evidence[] with exact
                verbatim_span + document_id + category (the data-room category
                of the cited document), source_documents[],
                affected_entities[], questions[].

        Returns:
            Dict with "decision" ("created" plus "finding_id", or "reject"
            plus machine-readable "reason": invalid_contract |
            evidence_unauthorized | evidence_not_verifiable | duplicate_finding).
        """
        try:
            payload = json.loads(finding_json)
        except ValueError:
            return _reject("invalid_contract", "finding_json is not valid JSON")
        if not isinstance(payload, dict):
            return _reject("invalid_contract", "finding_json must be a JSON object")

        title = payload.get("title")
        summary = payload.get("summary")
        severity = payload.get("severity")
        confidence = payload.get("confidence")
        if not isinstance(title, str) or not title.strip():
            return _reject("invalid_contract", "title must be a non-empty string")
        if not isinstance(summary, str) or not summary.strip():
            return _reject("invalid_contract", "summary must be a non-empty string")
        if not isinstance(severity, str) or severity not in _SEVERITIES:
            return _reject("invalid_contract", f"severity must be one of {sorted(_SEVERITIES)}")
        if isinstance(confidence, bool) or not isinstance(confidence, int | float):
            return _reject("invalid_contract", "confidence must be a number")
        if not 0.0 <= float(confidence) <= 1.0:
            return _reject("invalid_contract", "confidence must be in [0, 1]")

        structural = _structural_evidence(payload.get("evidence"))
        if structural is None:
            return _reject(
                "invalid_contract",
                "evidence must be a non-empty list of {verbatim_span, document_id, category}",
            )
        auth_outcome = _authorize_evidence(structural, principal, publisher)
        if auth_outcome == _INVALID_CATEGORY:
            return _reject("invalid_contract", "evidence category is unknown to the data-room ACL")
        if auth_outcome is not None:
            return _reject(
                _AUTH_DENIED,
                "evidence cites a document this agent is not authorized to read",
            )
        evidence = _verify_spans(structural, principal, doc_source)
        if evidence is None:
            return _reject(
                "evidence_not_verifiable",
                "every evidence entry needs a verbatim_span that is an exact "
                "substring of the cited document's parsed text",
            )

        requested_id = payload.get("finding_id")
        finding_id = (
            requested_id
            if isinstance(requested_id, str) and requested_id.strip()
            else uuid.uuid4().hex[:12]
        )
        stamp = now if now is not None else datetime.now(UTC)
        source_documents = _string_list(payload.get("source_documents")) or tuple(
            entry.document_id for entry in evidence
        )
        finding = Finding(
            finding_id=finding_id,
            deal_id=principal.deal_id,
            workstream=principal.workstream,
            title=title,
            summary=summary,
            severity=FindingSeverity(severity),
            confidence=float(confidence),
            status=FindingStatus.OPEN,
            evidence=evidence,
            owner=principal.name,
            created_at=stamp,
            updated_at=stamp,
            source_documents=source_documents,
            affected_entities=_string_list(payload.get("affected_entities")),
            questions=_string_list(payload.get("questions")),
        )
        try:
            store.create(finding)
        except DuplicateFindingError:
            # A rerun must not surface as an unhandled exception to the ADK
            # model loop; report it through the same structured contract.
            return _reject("duplicate_finding", f"finding {finding_id} already exists")
        partition_collection(client, principal.deal_id, principal.workstream).document(
            finding_id
        ).set(
            {
                "finding_id": finding_id,
                "title": finding.title,
                "severity": finding.severity.value,
                "status": finding.status.value,
                "created_at": stamp.isoformat(),
            }
        )
        # Vision §10: critical findings automatically notify the deal lead.
        escalate_if_critical(client, publisher, finding, now=stamp)
        return {"decision": "created", "finding_id": finding_id}

    return finding_create
