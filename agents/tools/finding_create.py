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
from typing import Any

from google.cloud import firestore

from agents.tools.data_room_read import DocSource
from identity.principals import Principal
from ingestion.parsing import LocalParser
from memory.findings import Evidence, Finding, FindingSeverity, FindingsStore, FindingStatus
from memory.partitions import partition_collection

_SEVERITIES = frozenset(severity.value for severity in FindingSeverity)


def _reject(reason: str, detail: str) -> dict[str, Any]:
    return {"decision": "reject", "reason": reason, "detail": detail}


def _string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _structural_evidence(
    entries: Any,
) -> tuple[tuple[str, str, str | None], ...] | None:
    """Validate evidence structure; return (span, document_id, chunk_ref) tuples.

    Returns None for any structural problem (missing/empty/non-list evidence,
    or an entry lacking a non-empty verbatim_span + document_id).
    """
    if not isinstance(entries, list) or not entries:
        return None
    parsed: list[tuple[str, str, str | None]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            return None
        span = entry.get("verbatim_span")
        document_id = entry.get("document_id")
        if not isinstance(span, str) or not span.strip():
            return None
        if not isinstance(document_id, str) or not document_id:
            return None
        chunk_ref = entry.get("chunk_ref")
        parsed.append((span, document_id, chunk_ref if isinstance(chunk_ref, str) else None))
    return tuple(parsed)


def _verify_evidence(
    entries: tuple[tuple[str, str, str | None], ...],
    principal: Principal,
    doc_source: DocSource,
) -> tuple[Evidence, ...] | None:
    """Resolve each cited document and confirm the span is a real substring.

    Returns verified Evidence entries, or None when any span is unverifiable
    (document missing, unparseable, needs OCR, or span not present in text).
    """
    verified: list[Evidence] = []
    for span, document_id, chunk_ref in entries:
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
) -> Any:
    """Bind the finding-create tool to *principal* (one agent, one deal)."""
    store = FindingsStore(client)

    def finding_create(finding_json: str) -> dict[str, Any]:
        """Create an evidence-gated finding for this agent's workstream.

        Args:
            finding_json: One JSON object following the finding contract:
                title, summary, severity (informational|low|medium|high|
                critical), confidence (0.0-1.0), evidence[] with exact
                verbatim_span + document_id, source_documents[],
                affected_entities[], questions[].

        Returns:
            Dict with "decision" ("created" plus "finding_id", or "reject"
            plus machine-readable "reason": invalid_contract |
            evidence_not_verifiable).
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
                "evidence must be a non-empty list of {verbatim_span, document_id}",
            )
        evidence = _verify_evidence(structural, principal, doc_source)
        if evidence is None:
            return _reject(
                "evidence_not_verifiable",
                "every evidence entry needs a verbatim_span that is an exact "
                "substring of the cited document's parsed text",
            )

        finding_id = uuid.uuid4().hex[:12]
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
        store.create(finding)
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
        return {"decision": "created", "finding_id": finding_id}

    return finding_create
