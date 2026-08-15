"""Offline end-to-end gate substitute (BUILD_PLAN Day-2 gate, scenario S8).

Proves the Day-2 chain without any live GCP call:

    simulated OBJECT_FINALIZE notification (falcon US bucket, contract PDF)
        -> bucket_notify.parse_notification (document.ingested envelope)
        -> InMemoryPublisher (event bus)
        -> consumer drains envelopes -> DealEventAuditLog.append (Firestore
           emulator, seq assignment)
        -> deal workspace document readable
        -> registry API serves the seeded 8-agent fleet

When GCP revives, the live equivalent is the runbook in
docs/deal_provisioning.md.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from google.cloud import firestore

from gateway.audit import DealEventAuditLog
from registry.api import create_app
from registry.seed import seed_registry
from registry.store import AgentRegistryStore
from runtime.bucket_notify import parse_notification
from runtime.deal_workspace import build_falcon_deal, provision_deal
from runtime.events import EventEnvelope, InMemoryPublisher

NOW = datetime(2026, 8, 15, 9, 0, tzinfo=UTC)

EXPECTED_SEED_VERSIONS: dict[str, str] = {
    "legal": "2.4.0",
    "finance": "3.1.0",
    "hr": "1.8.0",
    "ip_tech": "2.2.0",
    "tax": "1.5.0",
    "regulatory": "2.0.0",
    "esg": "1.3.0",
    "real_estate": "1.1.0",
}


class TestOfflineEndToEnd:
    def test_full_day2_chain(self, firestore_client: firestore.Client) -> None:
        store = AgentRegistryStore(firestore_client)
        assert seed_registry(store, now=NOW) == 8
        provision_deal(firestore_client, build_falcon_deal(NOW))

        notification = {
            "bucket": "diligence-room-dataroom-deal-falcon-us",
            "name": "contract_customer_x.pdf",
            "eventType": "OBJECT_FINALIZE",
            "contentType": "application/pdf",
        }
        envelope = parse_notification(notification)

        publisher = InMemoryPublisher()
        publisher.publish(envelope)

        audit = DealEventAuditLog(firestore_client)
        for raw in publisher.published:
            audit.append(EventEnvelope.from_json(raw))

        records = audit.events("deal-falcon")
        assert len(records) == 1
        first = records[0]
        assert first.seq == 1
        assert first.type == "document.ingested"
        assert first.actor == "bucket-notification"
        payload = json.loads(first.payload_json)
        assert payload["document_id"] == "contract_customer_x.pdf"
        assert payload["bucket"] == "diligence-room-dataroom-deal-falcon-us"

        deal_snapshot = firestore_client.collection("deals").document("deal-falcon").get()
        deal_data = deal_snapshot.to_dict()
        assert deal_data is not None
        assert deal_data["name"] == "Project Falcon"
        assert deal_data["status"] == "active"

        api_client = TestClient(create_app(store))
        agents = api_client.get("/agents").json()
        assert {a["agent_id"]: a["version"] for a in agents} == EXPECTED_SEED_VERSIONS

    def test_duplicate_notification_is_idempotent(self, firestore_client: firestore.Client) -> None:
        store = AgentRegistryStore(firestore_client)
        seed_registry(store, now=NOW)
        provision_deal(firestore_client, build_falcon_deal(NOW))

        notification = {
            "bucket": "diligence-room-dataroom-deal-falcon-eu",
            "name": "financials_fy27.xlsx",
            "eventType": "OBJECT_FINALIZE",
        }
        envelope = parse_notification(notification)

        audit = DealEventAuditLog(firestore_client)
        seq_first = audit.append(envelope)
        seq_second = audit.append(envelope)
        assert seq_first == seq_second == 1
        assert len(audit.events("deal-falcon")) == 1
