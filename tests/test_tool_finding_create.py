"""Finding-create tool tests (BUILD_PLAN D6-M1 toolset, scenario S6).

The tool validates the finding JSON contract and enforces evidence integrity:
every verbatim span must be an actual substring of the cited source document,
so agents cannot fabricate evidence.
"""

from __future__ import annotations

import json

from google.cloud import firestore

from agents.tools.data_room_read import DatasetDocSource
from agents.tools.finding_create import make_finding_create
from identity.principals import principal_for
from ingestion.chunking import chunk
from ingestion.parsing import LocalParser
from memory.findings import FindingsStore
from registry.models import Workstream

DEAL = "deal-falcon"
_DATA = "data/acme_robotics/"


def _contract_coc_span() -> str:
    path = DatasetDocSource().read("contract_customer_x.pdf")
    assert path is not None
    doc = LocalParser().parse(path, "contract_customer_x.pdf", DEAL)
    chunks = chunk(doc)
    return next(c.text for c in chunks if c.locator == "clause:11.3")


def _valid_finding_json(span: str) -> dict[str, object]:
    return {
        "title": "Customer X change-of-control termination right",
        "summary": (
            "The Meridian master services agreement grants a termination right "
            "within 90 days of a change of control."
        ),
        "severity": "high",
        "confidence": 0.9,
        "evidence": [
            {
                "verbatim_span": span,
                "document_id": "contract_customer_x.pdf",
                "chunk_ref": "clause:11.3",
            }
        ],
        "source_documents": ["contract_customer_x.pdf"],
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
        assert result["reason"] == "evidence_not_verifiable"
        assert FindingsStore(firestore_client).list_for_workstream(DEAL, Workstream.LEGAL) == []

    def test_unresolvable_document_rejected(self, firestore_client: firestore.Client) -> None:
        tool = make_finding_create(
            principal_for(Workstream.LEGAL, DEAL), firestore_client, DatasetDocSource()
        )
        payload = _valid_finding_json("anything")
        payload["evidence"] = [
            {"verbatim_span": "anything", "document_id": "ghost.pdf", "chunk_ref": None}
        ]
        result = tool(finding_json=json.dumps(payload))
        assert result["decision"] == "reject"
        assert result["reason"] == "evidence_not_verifiable"

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
