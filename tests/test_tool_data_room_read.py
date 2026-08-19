"""Scoped data-room read tool tests (BUILD_PLAN D6-M1 toolset, scenario S5)."""

from __future__ import annotations

import json

from google.cloud import firestore

from agents.tools.data_room_read import DatasetDocSource, make_data_room_read
from identity.principals import principal_for
from memory.event_log import EventLog
from registry.models import Workstream
from runtime.events import EventEnvelope

DEAL = "deal-falcon"


class _LogPublisher:
    def __init__(self, client: firestore.Client) -> None:
        self._log = EventLog(client)
        self.published: list[EventEnvelope] = []

    def publish(self, event: EventEnvelope) -> str:
        self.published.append(event)
        self._log.append(event)
        return event.event_id


def _security_payloads(publisher: _LogPublisher) -> list[dict[str, object]]:
    return [
        json.loads(json.dumps(dict(event.payload)))
        for event in publisher.published
        if event.type.value == "security.event"
    ]


class TestDataRoomRead:
    def test_legal_reads_contracts_allowed(self, firestore_client: firestore.Client) -> None:
        publisher = _LogPublisher(firestore_client)
        reader = make_data_room_read(
            principal_for(Workstream.LEGAL, DEAL), publisher, DatasetDocSource()
        )
        result = reader(category="contracts", name="contract_meridian_logistics.pdf")
        assert result["decision"] == "allow"
        assert result["document_id"] == "contract_meridian_logistics.pdf"
        text = str(result["text"])
        assert "Change of Control" in text
        chunks = result["chunks"]
        assert isinstance(chunks, list) and chunks
        assert any(c["locator"] == "clause:11.3" for c in chunks)

    def test_finance_reads_financials_allowed(self, firestore_client: firestore.Client) -> None:
        publisher = _LogPublisher(firestore_client)
        reader = make_data_room_read(
            principal_for(Workstream.FINANCE, DEAL), publisher, DatasetDocSource()
        )
        result = reader(category="financials", name="financials_fy27.xlsx")
        assert result["decision"] == "allow"
        assert "Meridian Logistics" in str(result["text"])

    def test_legal_reading_financials_denied_and_audited(
        self, firestore_client: firestore.Client
    ) -> None:
        publisher = _LogPublisher(firestore_client)
        reader = make_data_room_read(
            principal_for(Workstream.LEGAL, DEAL), publisher, DatasetDocSource()
        )
        result = reader(category="financials", name="financials_fy27.xlsx")
        assert result["decision"] == "deny"
        assert result["reason"] == "workstream_boundary"
        assert "text" not in result
        payloads = _security_payloads(publisher)
        assert len(payloads) == 1
        denied = payloads[0]
        assert denied["decision"] == "deny"
        assert denied["reason"] == "workstream_boundary"
        assert denied["identity"] == f"legal-agent@{DEAL}"
        assert "financials" in str(denied["resource"])

    def test_unknown_category_denied(self, firestore_client: firestore.Client) -> None:
        publisher = _LogPublisher(firestore_client)
        reader = make_data_room_read(
            principal_for(Workstream.LEGAL, DEAL), publisher, DatasetDocSource()
        )
        result = reader(category="astrology", name="stars.pdf")
        assert result["decision"] == "deny"
        assert result["reason"] == "invalid_resource"

    def test_missing_document_denied_not_found(self, firestore_client: firestore.Client) -> None:
        publisher = _LogPublisher(firestore_client)
        reader = make_data_room_read(
            principal_for(Workstream.LEGAL, DEAL), publisher, DatasetDocSource()
        )
        result = reader(category="contracts", name="no_such_contract.pdf")
        assert result["decision"] == "deny"
        assert result["reason"] == "not_found"

    def test_scanned_document_flags_needs_ocr(self, firestore_client: firestore.Client) -> None:
        publisher = _LogPublisher(firestore_client)
        reader = make_data_room_read(
            principal_for(Workstream.FINANCE, DEAL), publisher, DatasetDocSource()
        )
        result = reader(category="financials", name="scanned_invoice.pdf")
        assert result["decision"] == "allow"
        assert result["needs_ocr"] is True
        assert result["text"] is None
