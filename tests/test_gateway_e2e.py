"""Day-5 governed E2E gate (BUILD_PLAN Phase 3, vision §6 keystone).

The full chain, offline against the emulator:
Legal CoC finding -> ask_agent(finance) -> gateway ALLOW (AGGREGATE_PERMITTED)
-> real-workbook 18.3% -> second linked finding -> direct cross-workstream
read DENIED + audited -> debug listing shows both decisions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from google.cloud import firestore

from agents.tools.gateway_query import LocalGatewayClient, OfflineFinanceResponder
from gateway.decide import DecisionReason, Verdict, decisions_for_deal
from gateway.policy import PolicyStore
from identity.authz import AuthzDenied, DenialReason, Resource
from identity.principals import principal_for
from ingestion.chunking import chunk
from ingestion.lineage import register_document
from ingestion.parsing import LocalParser
from memory.event_log import EventLog
from memory.findings import (
    Evidence,
    Finding,
    FindingSeverity,
    FindingsStore,
    FindingStatus,
)
from registry.models import Workstream
from runtime.dispatcher import authorized_read
from runtime.events import EventEnvelope

DEAL = "deal-falcon"
_DATA = Path(__file__).resolve().parent.parent / "data" / "acme_robotics"
_CONTRACT = _DATA / "contract_customer_x.pdf"
_FINANCIALS = _DATA / "financials_fy27.xlsx"

T0 = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)
T1 = datetime(2026, 8, 18, 9, 5, tzinfo=UTC)


class _EventLogPublisher:
    """Publisher that persists envelopes to the canonical event log."""

    def __init__(self, client: firestore.Client) -> None:
        self._log = EventLog(client)
        self.published: list[EventEnvelope] = []

    def publish(self, event: EventEnvelope) -> str:
        self.published.append(event)
        self._log.append(event)
        return event.event_id


def _contract_coc_span() -> str:
    doc = LocalParser().parse(_CONTRACT.read_bytes(), _CONTRACT.name, DEAL)
    chunks = chunk(doc)
    target = next(c for c in chunks if c.locator == "clause:11.3")
    assert doc.text is not None
    assert target.text in doc.text
    return target.text


def _financials_meridian_row() -> str:
    doc = LocalParser().parse(_FINANCIALS.read_bytes(), _FINANCIALS.name, DEAL)
    assert doc.text is not None
    rows = [line for line in doc.text.split("\n") if "Meridian Logistics" in line]
    assert rows
    return rows[0]


@pytest.fixture()
def governed_deal(firestore_client: firestore.Client) -> firestore.Client:
    PolicyStore(firestore_client).seed_defaults(DEAL)
    firestore_client.collection("deals").document(DEAL).set({"deal_id": DEAL})
    for path in (_CONTRACT, _FINANCIALS):
        register_document(firestore_client, DEAL, path.name, path.name, path.read_bytes())
    return firestore_client


class TestGovernedChain:
    def test_coc_finding_triggers_allowed_query_returning_18_3(
        self, governed_deal: firestore.Client
    ) -> None:
        client = governed_deal
        store = FindingsStore(client)
        legal = principal_for(Workstream.LEGAL, DEAL)

        coc_finding = Finding(
            finding_id="LEGAL-001",
            deal_id=DEAL,
            workstream=Workstream.LEGAL,
            title="Customer X change-of-control termination right",
            summary=(
                "The Meridian Logistics master services agreement grants either "
                "party a termination right within 90 days of a change of control."
            ),
            severity=FindingSeverity.HIGH,
            confidence=0.9,
            status=FindingStatus.OPEN,
            evidence=(
                Evidence(
                    verbatim_span=_contract_coc_span(),
                    document_id=_CONTRACT.name,
                    chunk_ref="clause:11.3",
                ),
            ),
            owner=legal.name,
            created_at=T0,
            updated_at=T0,
            source_documents=(_CONTRACT.name,),
            affected_entities=("Meridian Logistics, Inc.",),
        )
        store.create(coc_finding)

        gateway = LocalGatewayClient(client, {Workstream.FINANCE: OfflineFinanceResponder()})
        response = gateway.ask(
            sender=legal,
            deal_id=DEAL,
            target=Workstream.FINANCE,
            question=(
                "What percentage of projected FY27 revenue comes from Meridian "
                "Logistics (Customer X)?"
            ),
            purpose="change_of_control_exposure",
            ts=T1,
        )
        assert response.verdict is Verdict.ALLOW
        assert response.reason is DecisionReason.AGGREGATE_PERMITTED
        assert response.answer == "18.3%"

    def test_18_3_recorded_as_linked_finding_with_verbatim_evidence(
        self, governed_deal: firestore.Client
    ) -> None:
        client = governed_deal
        store = FindingsStore(client)
        legal = principal_for(Workstream.LEGAL, DEAL)

        exposure_finding = Finding(
            finding_id="LEGAL-002",
            deal_id=DEAL,
            workstream=Workstream.LEGAL,
            title="Customer X revenue concentration amplifies CoC termination risk",
            summary=(
                "Finance confirmed via the gateway that Customer X represents "
                "18.3% of projected FY27 revenue; the CoC termination right "
                "therefore carries material revenue risk."
            ),
            severity=FindingSeverity.HIGH,
            confidence=0.85,
            status=FindingStatus.OPEN,
            evidence=(
                Evidence(
                    verbatim_span=_financials_meridian_row(),
                    document_id=_FINANCIALS.name,
                    chunk_ref="sheet:FY27 Projected Revenue!rows:2-2",
                ),
            ),
            owner=legal.name,
            created_at=T1,
            updated_at=T1,
            source_documents=(_FINANCIALS.name,),
            related_findings=("LEGAL-001",),
            affected_entities=("Meridian Logistics, Inc.",),
        )
        store.create(exposure_finding)
        assert "18.3%" in store.get(DEAL, "LEGAL-002").summary
        assert store.get(DEAL, "LEGAL-002").related_findings == ("LEGAL-001",)

    def test_direct_financials_read_by_legal_denied_and_audited(
        self, governed_deal: firestore.Client
    ) -> None:
        client = governed_deal
        legal = principal_for(Workstream.LEGAL, DEAL)
        publisher = _EventLogPublisher(client)
        resource = Resource(deal_id=DEAL, workstream=None, category="financials", name="fy27")
        with pytest.raises(AuthzDenied) as excinfo:
            authorized_read(legal, resource, publisher=publisher)
        assert excinfo.value.reason is DenialReason.workstream_boundary
        security = [
            event
            for event in publisher.published
            if event.payload["reason"] == "workstream_boundary"
        ]
        assert len(security) == 1
        assert security[0].payload["decision"] == "deny"

    def test_debug_listing_shows_allow_and_deny(self, governed_deal: firestore.Client) -> None:
        client = governed_deal
        legal = principal_for(Workstream.LEGAL, DEAL)
        gateway = LocalGatewayClient(client, {Workstream.FINANCE: OfflineFinanceResponder()})
        gateway.ask(
            sender=legal,
            deal_id=DEAL,
            target=Workstream.FINANCE,
            question="q",
            purpose="revenue_concentration",
            ts=T1,
        )
        gateway.ask(
            sender=legal, deal_id=DEAL, target=Workstream.HR, question="q", purpose="x", ts=T1
        )
        listing = decisions_for_deal(client, DEAL)
        verdicts = [str(item["payload_json"]) for item in listing]
        assert len(listing) == 2
        combined = " ".join(verdicts)
        assert '"decision": "allow"' in combined or '"decision":"allow"' in combined
        assert '"decision": "deny"' in combined or '"decision":"deny"' in combined

    def test_lineage_supersedes_ready_for_amendment(self, governed_deal: firestore.Client) -> None:
        """The amendment (Day-7 scenario) chains onto the vendor agreement."""
        client = governed_deal
        vendor_path = _DATA / "vendor_agreement_2027.pdf"
        amendment_path = _DATA / "amendment_2030.pdf"
        register_document(
            client, DEAL, vendor_path.name, vendor_path.name, vendor_path.read_bytes()
        )
        amendment = register_document(
            client,
            DEAL,
            amendment_path.name,
            amendment_path.name,
            amendment_path.read_bytes(),
            chains_from=vendor_path.name,
        )
        assert amendment.version == 2
        assert amendment.supersedes == vendor_path.name
