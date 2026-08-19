"""Finding-create tool tests (BUILD_PLAN D6-M1 toolset, scenario S6).

The tool validates the finding JSON contract and enforces evidence integrity:
every verbatim span must be an actual substring of the cited source document,
so agents cannot fabricate evidence.
"""

from __future__ import annotations

import json
from typing import Any

from google.cloud import firestore

from agents.tools.data_room_read import DatasetDocSource
from agents.tools.finding_create import make_finding_create
from identity.principals import principal_for
from ingestion.chunking import chunk
from ingestion.parsing import LocalParser
from memory.findings import FindingsStore
from registry.models import Workstream
from runtime.events import EventEnvelope, EventType, InMemoryPublisher

DEAL = "deal-falcon"
_DATA = "data/vantage_robotics/"


def _contract_coc_span() -> str:
    path = DatasetDocSource().read("contract_meridian_logistics.pdf")
    assert path is not None
    doc = LocalParser().parse(path, "contract_meridian_logistics.pdf", DEAL)
    chunks = chunk(doc)
    return next(c.text for c in chunks if c.locator == "clause:11.3")


def _financials_meridian_span() -> str:
    path = DatasetDocSource().read("financials_fy27.xlsx")
    assert path is not None
    doc = LocalParser().parse(path, "financials_fy27.xlsx", DEAL)
    assert doc.text is not None
    rows = [line for line in doc.text.split("\n") if "Meridian Logistics" in line]
    assert rows
    return rows[0]


def _valid_finding_json(span: str) -> dict[str, object]:
    return {
        "title": "Meridian Logistics change-of-control termination right",
        "summary": (
            "The Meridian master services agreement grants a termination right "
            "within 90 days of a change of control."
        ),
        "severity": "high",
        "confidence": 0.9,
        "evidence": [
            {
                "verbatim_span": span,
                "document_id": "contract_meridian_logistics.pdf",
                "category": "contracts",
                "chunk_ref": "clause:11.3",
            }
        ],
        "source_documents": ["contract_meridian_logistics.pdf"],
        "affected_entities": ["Meridian Logistics, Inc."],
        "questions": [],
    }


class TestFindingCreate:
    def test_valid_finding_created_and_stored(self, firestore_client: firestore.Client) -> None:
        tool = make_finding_create(
            principal_for(Workstream.LEGAL, DEAL), firestore_client, DatasetDocSource()
        )
        result = tool(finding_json=json.dumps(_valid_finding_json(_contract_coc_span())))
        assert result["decision"] == "created"
        finding_id = str(result["finding_id"])
        stored = FindingsStore(firestore_client).get(DEAL, finding_id)
        assert stored.workstream is Workstream.LEGAL
        assert stored.owner == f"legal-agent@{DEAL}"
        assert stored.evidence[0].verbatim_span == _contract_coc_span()

    def test_partition_item_written(self, firestore_client: firestore.Client) -> None:
        tool = make_finding_create(
            principal_for(Workstream.LEGAL, DEAL), firestore_client, DatasetDocSource()
        )
        result = tool(finding_json=json.dumps(_valid_finding_json(_contract_coc_span())))
        finding_id = str(result["finding_id"])
        item = (
            firestore_client.collection("deals")
            .document(DEAL)
            .collection("workstreams")
            .document("legal")
            .collection("items")
            .document(finding_id)
            .get()
        )
        assert item.exists
        data = item.to_dict()
        assert data is not None
        assert data["finding_id"] == finding_id
        assert data["severity"] == "high"

    def test_fabricated_span_rejected(self, firestore_client: firestore.Client) -> None:
        tool = make_finding_create(
            principal_for(Workstream.LEGAL, DEAL), firestore_client, DatasetDocSource()
        )
        payload = _valid_finding_json("this text does not exist in any document")
        result = tool(finding_json=json.dumps(payload))
        assert result["decision"] == "reject"
        assert result["reason"] == "evidence_unresolvable"
        assert FindingsStore(firestore_client).list_for_workstream(DEAL, Workstream.LEGAL) == []

    def test_unresolvable_document_rejected(self, firestore_client: firestore.Client) -> None:
        tool = make_finding_create(
            principal_for(Workstream.LEGAL, DEAL), firestore_client, DatasetDocSource()
        )
        payload = _valid_finding_json("anything")
        payload["evidence"] = [
            {
                "verbatim_span": "anything",
                "document_id": "ghost.pdf",
                "category": "contracts",
                "chunk_ref": None,
            }
        ]
        result = tool(finding_json=json.dumps(payload))
        assert result["decision"] == "reject"
        assert result["reason"] == "evidence_unresolvable"

    def test_empty_evidence_rejected(self, firestore_client: firestore.Client) -> None:
        tool = make_finding_create(
            principal_for(Workstream.LEGAL, DEAL), firestore_client, DatasetDocSource()
        )
        payload = _valid_finding_json(_contract_coc_span())
        payload["evidence"] = []
        result = tool(finding_json=json.dumps(payload))
        assert result["decision"] == "reject"
        assert result["reason"] == "invalid_contract"

    def test_confidence_out_of_range_rejected(self, firestore_client: firestore.Client) -> None:
        tool = make_finding_create(
            principal_for(Workstream.LEGAL, DEAL), firestore_client, DatasetDocSource()
        )
        payload = _valid_finding_json(_contract_coc_span())
        payload["confidence"] = 1.5
        result = tool(finding_json=json.dumps(payload))
        assert result["decision"] == "reject"
        assert result["reason"] == "invalid_contract"

    def test_bad_severity_rejected(self, firestore_client: firestore.Client) -> None:
        tool = make_finding_create(
            principal_for(Workstream.LEGAL, DEAL), firestore_client, DatasetDocSource()
        )
        payload = _valid_finding_json(_contract_coc_span())
        payload["severity"] = "extreme"
        result = tool(finding_json=json.dumps(payload))
        assert result["decision"] == "reject"
        assert result["reason"] == "invalid_contract"

    def test_malformed_json_rejected(self, firestore_client: firestore.Client) -> None:
        tool = make_finding_create(
            principal_for(Workstream.LEGAL, DEAL), firestore_client, DatasetDocSource()
        )
        result = tool(finding_json="{not valid json")
        assert result["decision"] == "reject"
        assert result["reason"] == "invalid_contract"

    def test_duplicate_finding_id_rejected_not_raised(
        self, firestore_client: firestore.Client
    ) -> None:
        tool = make_finding_create(
            principal_for(Workstream.LEGAL, DEAL), firestore_client, DatasetDocSource()
        )
        payload = _valid_finding_json(_contract_coc_span())
        payload["finding_id"] = "STABLE-001"
        first = tool(finding_json=json.dumps(payload))
        assert first["decision"] == "created"
        second = tool(finding_json=json.dumps(payload))
        assert second["decision"] == "reject"
        assert second["reason"] == "duplicate_finding"
        assert len(FindingsStore(firestore_client).list_for_workstream(DEAL, Workstream.LEGAL)) == 1


class TestEvidenceAuthorization:
    """The evidence gate must enforce agent->data AuthZ, not just anti-fabrication."""

    def _legal_tool(
        self, firestore_client: firestore.Client, publisher: InMemoryPublisher | None = None
    ) -> Any:
        return make_finding_create(
            principal_for(Workstream.LEGAL, DEAL),
            firestore_client,
            DatasetDocSource(),
            publisher=publisher,
        )

    def test_citing_out_of_workstream_doc_rejected(
        self, firestore_client: firestore.Client
    ) -> None:
        tool = self._legal_tool(firestore_client)
        payload = _valid_finding_json(_financials_meridian_span())
        payload["evidence"] = [
            {
                "verbatim_span": _financials_meridian_span(),
                "document_id": "financials_fy27.xlsx",
                "category": "financials",
                "chunk_ref": None,
            }
        ]
        result = tool(finding_json=json.dumps(payload))
        assert result["decision"] == "reject"
        assert result["reason"] == "evidence_unauthorized"
        assert FindingsStore(firestore_client).list_for_workstream(DEAL, Workstream.LEGAL) == []

    def test_missing_category_rejected(self, firestore_client: firestore.Client) -> None:
        tool = self._legal_tool(firestore_client)
        payload = _valid_finding_json(_contract_coc_span())
        payload["evidence"] = [
            {
                "verbatim_span": _contract_coc_span(),
                "document_id": "contract_meridian_logistics.pdf",
                "chunk_ref": "clause:11.3",
            }
        ]
        result = tool(finding_json=json.dumps(payload))
        assert result["decision"] == "reject"
        assert result["reason"] == "invalid_contract"

    def test_unknown_category_rejected(self, firestore_client: firestore.Client) -> None:
        tool = self._legal_tool(firestore_client)
        payload = _valid_finding_json(_contract_coc_span())
        payload["evidence"] = [
            {
                "verbatim_span": _contract_coc_span(),
                "document_id": "contract_meridian_logistics.pdf",
                "category": "not-a-real-category",
                "chunk_ref": "clause:11.3",
            }
        ]
        result = tool(finding_json=json.dumps(payload))
        assert result["decision"] == "reject"
        assert result["reason"] == "invalid_contract"

    def test_unauthorized_citation_emits_security_event(
        self, firestore_client: firestore.Client
    ) -> None:
        publisher = InMemoryPublisher()
        tool = self._legal_tool(firestore_client, publisher=publisher)
        payload = _valid_finding_json(_financials_meridian_span())
        payload["evidence"] = [
            {
                "verbatim_span": _financials_meridian_span(),
                "document_id": "financials_fy27.xlsx",
                "category": "financials",
                "chunk_ref": None,
            }
        ]
        tool(finding_json=json.dumps(payload))
        events = [EventEnvelope.from_json(raw) for raw in publisher.published]
        security = [event for event in events if event.type is EventType.SECURITY_EVENT]
        assert len(security) == 1
        assert security[0].payload["decision"] == "deny"
        assert security[0].payload["reason"] == "workstream_boundary"
