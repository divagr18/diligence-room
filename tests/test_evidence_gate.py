"""Evidence gate tests (BUILD_PLAN D9-M2, vision §19.3).

A finding cannot enter `candidate` status without evidence whose verbatim
span resolves to an actual passage in a source document (span lookup runs at
write time). Findings failing the gate are rejected with reason
`evidence_unresolvable` and logged. Confidence below threshold additionally
caps a finding at `candidate` (no auto-escalation) — the anti-hallucination
answer to *what happens if a worker agent returns a hallucination?*
"""

from __future__ import annotations

import json
from typing import Any

from google.cloud import firestore

from agents.tools.data_room_read import DatasetDocSource
from agents.tools.finding_create import EVIDENCE_CANDIDATE_THRESHOLD, make_finding_create
from identity.principals import principal_for
from ingestion.chunking import chunk
from ingestion.parsing import LocalParser
from memory.findings import FindingsStore, FindingStatus
from registry.models import Workstream
from runtime.events import EventEnvelope, EventType, InMemoryPublisher

DEAL = "deal-falcon"


def _contract_coc_span() -> str:
    path = DatasetDocSource().read("contract_meridian_logistics.pdf")
    assert path is not None
    doc = LocalParser().parse(path, "contract_meridian_logistics.pdf", DEAL)
    chunks = chunk(doc)
    return next(c.text for c in chunks if c.locator == "clause:11.3")


def _payload(
    span: str, *, severity: str = "high", confidence: float = 0.9, document_id: str | None = None
) -> dict[str, object]:
    return {
        "title": "Evidence-gate probe finding",
        "summary": "Probe finding for the anti-hallucination gate.",
        "severity": severity,
        "confidence": confidence,
        "evidence": [
            {
                "verbatim_span": span,
                "document_id": document_id or "contract_meridian_logistics.pdf",
                "category": "contracts",
                "chunk_ref": "clause:11.3",
            }
        ],
        "source_documents": [document_id or "contract_meridian_logistics.pdf"],
        "affected_entities": ["Meridian Logistics, Inc."],
        "questions": [],
    }


def _tool(firestore_client: firestore.Client, publisher: InMemoryPublisher | None = None) -> Any:
    return make_finding_create(
        principal_for(Workstream.LEGAL, DEAL),
        firestore_client,
        DatasetDocSource(),
        publisher=publisher,
    )


class TestUnresolvableRejection:
    def test_fabricated_span_rejected_as_unresolvable(
        self, firestore_client: firestore.Client
    ) -> None:
        tool = _tool(firestore_client)
        result = tool(finding_json=json.dumps(_payload("text fabricated by a hallucinating agent")))
        assert result["decision"] == "reject"
        assert result["reason"] == "evidence_unresolvable"
        assert FindingsStore(firestore_client).list_for_workstream(DEAL, Workstream.LEGAL) == []

    def test_ghost_document_rejected_as_unresolvable(
        self, firestore_client: firestore.Client
    ) -> None:
        tool = _tool(firestore_client)
        result = tool(finding_json=json.dumps(_payload("anything", document_id="ghost.pdf")))
        assert result["decision"] == "reject"
        assert result["reason"] == "evidence_unresolvable"

    def test_rejection_is_logged_for_the_security_feed(
        self, firestore_client: firestore.Client
    ) -> None:
        publisher = InMemoryPublisher()
        tool = _tool(firestore_client, publisher=publisher)
        tool(finding_json=json.dumps(_payload("fabricated, resolves nowhere")))
        envelopes = [EventEnvelope.from_json(raw) for raw in publisher.published]
        rejections = [e for e in envelopes if e.type is EventType.EVIDENCE_REJECTED]
        assert len(rejections) == 1
        assert rejections[0].payload["reason"] == "evidence_unresolvable"
        assert rejections[0].payload["identity"] == f"legal-agent@{DEAL}"


class TestCandidateCap:
    def test_low_confidence_finding_capped_at_candidate(
        self, firestore_client: firestore.Client
    ) -> None:
        tool = _tool(firestore_client)
        result = tool(finding_json=json.dumps(_payload(_contract_coc_span(), confidence=0.5)))
        assert result["decision"] == "created"
        stored = FindingsStore(firestore_client).get(DEAL, str(result["finding_id"]))
        assert stored.status is FindingStatus.CANDIDATE

    def test_confidence_at_threshold_stays_open(self, firestore_client: firestore.Client) -> None:
        tool = _tool(firestore_client)
        result = tool(
            finding_json=json.dumps(
                _payload(_contract_coc_span(), confidence=EVIDENCE_CANDIDATE_THRESHOLD)
            )
        )
        assert result["decision"] == "created"
        stored = FindingsStore(firestore_client).get(DEAL, str(result["finding_id"]))
        assert stored.status is FindingStatus.OPEN

    def test_confident_finding_stays_open(self, firestore_client: firestore.Client) -> None:
        tool = _tool(firestore_client)
        result = tool(finding_json=json.dumps(_payload(_contract_coc_span())))
        stored = FindingsStore(firestore_client).get(DEAL, str(result["finding_id"]))
        assert stored.status is FindingStatus.OPEN

    def test_candidate_cap_blocks_auto_escalation(self, firestore_client: firestore.Client) -> None:
        publisher = InMemoryPublisher()
        tool = _tool(firestore_client, publisher=publisher)
        result = tool(
            finding_json=json.dumps(
                _payload(_contract_coc_span(), severity="critical", confidence=0.5)
            )
        )
        assert result["decision"] == "created"
        finding_id = str(result["finding_id"])
        stored = FindingsStore(firestore_client).get(DEAL, finding_id)
        assert stored.status is FindingStatus.CANDIDATE
        inbox = (
            firestore_client.collection("deals")
            .document(DEAL)
            .collection("inbox")
            .document(finding_id)
            .get()
        )
        assert not inbox.exists
        envelopes = [EventEnvelope.from_json(raw) for raw in publisher.published]
        assert all(e.type is not EventType.FINDING_ESCALATED for e in envelopes)

    def test_confident_critical_finding_still_escalates(
        self, firestore_client: firestore.Client
    ) -> None:
        publisher = InMemoryPublisher()
        tool = _tool(firestore_client, publisher=publisher)
        result = tool(
            finding_json=json.dumps(
                _payload(_contract_coc_span(), severity="critical", confidence=0.9)
            )
        )
        assert result["decision"] == "created"
        stored = FindingsStore(firestore_client).get(DEAL, str(result["finding_id"]))
        assert stored.status is FindingStatus.OPEN
        envelopes = [EventEnvelope.from_json(raw) for raw in publisher.published]
        assert any(e.type is EventType.FINDING_ESCALATED for e in envelopes)
