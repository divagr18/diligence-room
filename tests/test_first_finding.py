"""Day-3 gate substitute test (offline wiring proof).

The live LLM-driven legal agent run is live-only by design (the agent fleet
executes against the real Vertex AI Agent Engine, which requires GCP).
This module proves the *wiring* chain without any live call:

    simulated GCS notification (falcon US bucket, contract PDF)
        -> bucket_notify.parse_notification (document.ingested envelope)
        -> InMemoryPublisher -> EventLog.append (seq 1)
        -> dispatcher.authorized_read for the legal principal (no denial)
        -> stub legal agent returns a canned Finding (CoC clause verbatim)
        -> FindingsStore.create
        -> finding.created event (seq 2)
        -> deal-doc documents_ingested mirrors runtime/consumer.py
        -> negative: hr principal on the legal resource is denied (seq 3)

The stub agent's evidence span quotes the CoC termination clause verbatim;
the real agent would extract it from the parsed document.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from google.cloud import firestore

from identity.authz import Action, AuthzDenied, parse_resource
from identity.principals import principal_for
from memory.event_log import EventLog
from memory.findings import Evidence, Finding, FindingSeverity, FindingsStore, FindingStatus
from registry.models import Workstream
from runtime.bucket_notify import parse_notification
from runtime.deal_workspace import FALCON_DEAL_ID, build_falcon_deal, provision_deal
from runtime.dispatcher import authorized_read
from runtime.events import EventEnvelope, EventType, InMemoryPublisher, new_event

NOW = datetime(2026, 8, 15, 9, 0, tzinfo=UTC)
COC_SPAN = (
    "may terminate this Agreement by written notice delivered "
    "within ninety (90) days following a Change of Control"
)
US_BUCKET = "diligence-room-dataroom-deal-falcon-us"
DOCUMENT_ID = "contract_meridian_logistics.pdf"
FINDING_ID = "LEGAL-001"

GCS_NOTIFICATION: dict[str, object] = {
    "bucket": US_BUCKET,
    "name": DOCUMENT_ID,
    "eventType": "OBJECT_FINALIZE",
    "contentType": "application/pdf",
}

LEGAL_CONTRACT_RESOURCE = f"deals/{FALCON_DEAL_ID}/workstreams/legal/contracts/{DOCUMENT_ID}"


class _EventLogPublisher:
    """Adapter satisfying dispatcher's publisher Protocol via EventLog.append."""

    def __init__(self, event_log: EventLog) -> None:
        self._event_log = event_log

    def publish(self, event: EventEnvelope) -> str:
        self._event_log.append(event)
        return event.event_id


def _stub_legal_finding(now: datetime) -> Finding:
    """Canned Finding that a real legal agent would produce from the CoC."""
    return Finding(
        finding_id=FINDING_ID,
        deal_id=FALCON_DEAL_ID,
        workstream=Workstream.LEGAL,
        title="Change-of-Control termination right",
        summary=(
            "Counterparty holds a 90-day post-Change-of-Control termination "
            "window — flagged as material risk for deal continuity."
        ),
        severity=FindingSeverity.HIGH,
        confidence=0.94,
        status=FindingStatus.CANDIDATE,
        evidence=(Evidence(verbatim_span=COC_SPAN, document_id=DOCUMENT_ID),),
        source_documents=(DOCUMENT_ID,),
        owner="legal-agent@deal-falcon",
        created_at=now,
        updated_at=now,
    )


@pytest.fixture()
def falcon_client(firestore_client: firestore.Client) -> firestore.Client:
    provision_deal(firestore_client, build_falcon_deal(NOW))
    return firestore_client


class TestFirstFindingWiring:
    def test_notification_to_finding_chain(self, falcon_client: firestore.Client) -> None:
        event_log = EventLog(falcon_client)
        audit_pub = _EventLogPublisher(event_log)

        # Step 1 — GCS notification -> document.ingested envelope
        envelope = parse_notification(GCS_NOTIFICATION)
        assert envelope.type == EventType.DOCUMENT_INGESTED
        assert envelope.deal_id == FALCON_DEAL_ID

        # Step 2 — InMemoryPublisher drain -> EventLog seq 1
        publisher = InMemoryPublisher()
        publisher.publish(envelope)
        seq = None
        for raw in publisher.published:
            seq = event_log.append(EventEnvelope.from_json(raw))
        assert seq == 1

        # Step 3 — authorized_read for legal principal (no denial event)
        legal_principal = principal_for("legal", FALCON_DEAL_ID)
        resource = parse_resource(LEGAL_CONTRACT_RESOURCE)
        authorized_read(legal_principal, resource, publisher=audit_pub)
        assert len(event_log.events(FALCON_DEAL_ID)) == 1  # no security event

        # Step 4 — stub legal agent produces canned Finding
        finding = _stub_legal_finding(NOW)
        assert finding.finding_id == FINDING_ID
        assert finding.severity == FindingSeverity.HIGH
        assert finding.confidence == 0.94

        # Step 5 — FindingsStore.create + finding.created event (seq 2)
        findings = FindingsStore(falcon_client)
        findings.create(finding)
        finding_envelope = new_event(
            deal_id=FALCON_DEAL_ID,
            actor=legal_principal.name,
            event_type=EventType.FINDING_CREATED,
            payload={"finding_id": FINDING_ID, "severity": "high"},
            now=NOW,
        )
        seq2 = event_log.append(finding_envelope)
        assert seq2 == 2

        # Step 6 — assertions: finding retrieved, event ordering, deal state
        retrieved = findings.get(FALCON_DEAL_ID, FINDING_ID)
        assert retrieved.evidence[0].verbatim_span == COC_SPAN
        assert retrieved.evidence[0].document_id == DOCUMENT_ID

        all_events = event_log.events(FALCON_DEAL_ID)
        assert len(all_events) == 2
        assert all_events[0].seq == 1
        assert all_events[0].type == "document.ingested"
        ingested_payload = json.loads(all_events[0].payload_json)
        assert ingested_payload["document_id"] == DOCUMENT_ID

        assert all_events[1].seq == 2
        assert all_events[1].type == "finding.created"
        finding_payload = json.loads(all_events[1].payload_json)
        assert finding_payload["finding_id"] == FINDING_ID
        assert finding_payload["severity"] == "high"

        # Mirror runtime/consumer.py deal-state update exactly
        falcon_client.collection("deals").document(FALCON_DEAL_ID).update(
            {
                "documents_ingested": firestore.Increment(1),
                "last_document_id": DOCUMENT_ID,
                "last_ingested_at": envelope.ts,
            }
        )
        deal_data = falcon_client.collection("deals").document(FALCON_DEAL_ID).get().to_dict()
        assert deal_data is not None
        assert deal_data["documents_ingested"] == 1
        assert deal_data["last_document_id"] == DOCUMENT_ID
        last_ingested_at = deal_data["last_ingested_at"]
        assert isinstance(last_ingested_at, datetime)
        assert last_ingested_at.tzinfo is not None

    def test_hr_cross_workstream_denial_recorded(self, falcon_client: firestore.Client) -> None:
        """An hr principal on a legal-contracts resource is denied and the
        denial IS recorded as security.event seq 3, proving the gate
        enforces before any finding could be created by the wrong workstream.
        """
        event_log = EventLog(falcon_client)
        audit_pub = _EventLogPublisher(event_log)
        deal_id = FALCON_DEAL_ID

        # Establish seq 1 (document.ingested) + seq 2 (finding.created)
        envelope = parse_notification(GCS_NOTIFICATION)
        publisher = InMemoryPublisher()
        publisher.publish(envelope)
        for raw in publisher.published:
            event_log.append(EventEnvelope.from_json(raw))

        findings = FindingsStore(falcon_client)
        findings.create(_stub_legal_finding(NOW))
        legal_principal = principal_for("legal", deal_id)
        finding_envelope = new_event(
            deal_id=deal_id,
            actor=legal_principal.name,
            event_type=EventType.FINDING_CREATED,
            payload={"finding_id": FINDING_ID, "severity": "high"},
            now=NOW,
        )
        event_log.append(finding_envelope)

        # Negative: hr principal reads legal contract -> AuthzDenied
        hr_principal = principal_for("hr", deal_id)
        resource = parse_resource(LEGAL_CONTRACT_RESOURCE)
        with pytest.raises(AuthzDenied) as exc_info:
            authorized_read(hr_principal, resource, publisher=audit_pub)

        denied = exc_info.value
        assert denied.action == Action.READ
        assert denied.principal.workstream == Workstream.HR

        all_events = event_log.events(deal_id)
        assert len(all_events) == 3
        assert all_events[2].seq == 3
        assert all_events[2].type == "security.event"
        denial_payload = json.loads(all_events[2].payload_json)
        assert denial_payload["decision"] == "deny"
        assert denial_payload["identity"] == hr_principal.name
