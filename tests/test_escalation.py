"""Escalation path tests (BUILD_PLAN D7-M6, vision §10 escalation policy).

A critical finding must automatically notify the deal lead: an audit event
(FINDING_ESCALATED) plus a dashboard-readable inbox entry. Non-critical
findings never escalate.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from google.cloud import firestore

from agents.tools.data_room_read import DatasetDocSource
from agents.tools.finding_create import make_finding_create
from coordination.escalation import (
    EscalationRecord,
    escalate_critical,
    escalate_if_critical,
)
from identity.principals import principal_for
from ingestion.chunking import chunk
from ingestion.parsing import LocalParser
from memory.findings import (
    Evidence,
    Finding,
    FindingSeverity,
    FindingStatus,
)
from registry.models import Workstream
from runtime.events import EventEnvelope, EventType, InMemoryPublisher

DEAL = "deal-falcon"
NOW = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)


def _contract_coc_span() -> str:
    blob = DatasetDocSource().read("contract_customer_x.pdf")
    assert blob is not None
    doc = LocalParser().parse(blob, "contract_customer_x.pdf", DEAL)
    chunks = chunk(doc)
    return next(c.text for c in chunks if c.locator == "clause:11.3")


def _critical_finding_json(span: str) -> dict[str, object]:
    return {
        "title": "Customer X change-of-control termination right",
        "summary": "Terminal revenue risk if the CoC clause fires at close.",
        "severity": "critical",
        "confidence": 0.9,
        "evidence": [
            {
                "verbatim_span": span,
                "document_id": "contract_customer_x.pdf",
                "category": "contracts",
                "chunk_ref": "clause:11.3",
            }
        ],
        "source_documents": ["contract_customer_x.pdf"],
        "affected_entities": ["Meridian Logistics, Inc."],
        "questions": [],
    }


def _finding(severity: FindingSeverity) -> Finding:
    return Finding(
        finding_id="LEGAL-900",
        deal_id=DEAL,
        workstream=Workstream.LEGAL,
        title="Forced critical finding",
        summary="Gate scenario: escalation must fire.",
        severity=severity,
        confidence=0.9,
        status=FindingStatus.OPEN,
        evidence=(Evidence(verbatim_span="quoted span", document_id="contract_customer_x.pdf"),),
        owner="legal-agent@deal-falcon",
        created_at=NOW,
        updated_at=NOW,
    )


def _inbox_entry(client: firestore.Client, finding_id: str) -> dict[str, object] | None:
    snapshot = (
        client.collection("deals").document(DEAL).collection("inbox").document(finding_id).get()
    )
    return snapshot.to_dict() if snapshot.exists else None


class TestEscalationThroughFindingCreate:
    def test_critical_finding_fires_event_and_inbox_entry(
        self, firestore_client: firestore.Client
    ) -> None:
        publisher = InMemoryPublisher()
        tool = make_finding_create(
            principal_for(Workstream.LEGAL, DEAL),
            firestore_client,
            DatasetDocSource(),
            now=NOW,
            publisher=publisher,
        )
        result = tool(finding_json=json.dumps(_critical_finding_json(_contract_coc_span())))
        assert result["decision"] == "created"
        finding_id = str(result["finding_id"])

        events = [EventEnvelope.from_json(raw) for raw in publisher.published]
        escalated = [event for event in events if event.type is EventType.FINDING_ESCALATED]
        assert len(escalated) == 1
        payload = escalated[0].payload
        assert payload["finding_id"] == finding_id
        assert payload["severity"] == "critical"
        assert payload["workstream"] == "legal"
        assert payload["owner"] == f"legal-agent@{DEAL}"
        assert escalated[0].deal_id == DEAL

        entry = _inbox_entry(firestore_client, finding_id)
        assert entry is not None
        assert entry["kind"] == "escalation"
        assert entry["severity"] == "critical"
        assert entry["workstream"] == "legal"
        assert entry["status"] == "open"
        assert entry["title"]

    def test_high_severity_finding_does_not_escalate(
        self, firestore_client: firestore.Client
    ) -> None:
        publisher = InMemoryPublisher()
        tool = make_finding_create(
            principal_for(Workstream.LEGAL, DEAL),
            firestore_client,
            DatasetDocSource(),
            now=NOW,
            publisher=publisher,
        )
        payload = _critical_finding_json(_contract_coc_span())
        payload["severity"] = "high"
        result = tool(finding_json=json.dumps(payload))
        assert result["decision"] == "created"
        finding_id = str(result["finding_id"])

        events = [EventEnvelope.from_json(raw) for raw in publisher.published]
        assert all(event.type is not EventType.FINDING_ESCALATED for event in events)
        assert _inbox_entry(firestore_client, finding_id) is None


class TestEscalateFunctions:
    def test_escalate_critical_rejects_non_critical(self) -> None:
        with pytest.raises(ValueError, match="critical"):
            escalate_critical(
                None,  # type: ignore[arg-type]
                InMemoryPublisher(),
                _finding(FindingSeverity.HIGH),
                now=NOW,
            )

    def test_escalate_if_critical_noop_for_non_critical(
        self, firestore_client: firestore.Client
    ) -> None:
        publisher = InMemoryPublisher()
        record = escalate_if_critical(
            firestore_client, publisher, _finding(FindingSeverity.MEDIUM), now=NOW
        )
        assert record is None
        assert publisher.published == []
        assert _inbox_entry(firestore_client, "LEGAL-900") is None

    def test_escalate_critical_returns_record_and_emits_event(
        self, firestore_client: firestore.Client
    ) -> None:
        publisher = InMemoryPublisher()
        record = escalate_critical(
            firestore_client, publisher, _finding(FindingSeverity.CRITICAL), now=NOW
        )
        assert isinstance(record, EscalationRecord)
        assert record.finding_id == "LEGAL-900"
        assert record.deal_id == DEAL
        events = [EventEnvelope.from_json(raw) for raw in publisher.published]
        assert len(events) == 1
        assert events[0].type is EventType.FINDING_ESCALATED

    def test_escalate_without_publisher_writes_inbox_only(
        self, firestore_client: firestore.Client
    ) -> None:
        record = escalate_if_critical(
            firestore_client, None, _finding(FindingSeverity.CRITICAL), now=NOW
        )
        assert record is not None
        assert _inbox_entry(firestore_client, "LEGAL-900") is not None
