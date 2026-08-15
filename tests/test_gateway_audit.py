"""Append-only audit writer tests (BUILD_PLAN D2-M8).

Emulator-backed: sequential seq assignment, idempotent append, canonical
payload JSON roundtrip, and independent per-deal counters.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from google.cloud import firestore

from gateway.audit import DealEventAuditLog
from runtime.events import EventEnvelope, EventType


def _make_envelope(
    *,
    deal_id: str,
    event_id: str,
    actor: str = "legal-agent",
    event_type: EventType = EventType.DOCUMENT_INGESTED,
    payload: dict[str, object] | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id,
        deal_id=deal_id,
        ts=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        actor=actor,
        type=event_type,
        payload=payload if payload is not None else {"key": "value"},
        dedupe_key=f"dedupe-{event_id}",
    )


class TestDealEventAuditLog:
    def test_three_appends_yield_strict_sequential_seqs(
        self, firestore_client: firestore.Client
    ) -> None:
        audit = DealEventAuditLog(firestore_client)
        deal_id = "deal-sequential"

        seq1 = audit.append(_make_envelope(deal_id=deal_id, event_id="e1"))
        seq2 = audit.append(_make_envelope(deal_id=deal_id, event_id="e2"))
        seq3 = audit.append(_make_envelope(deal_id=deal_id, event_id="e3"))

        assert seq1 == 1
        assert seq2 == 2
        assert seq3 == 3

        records = audit.events(deal_id)
        assert len(records) == 3
        seqs = [r.seq for r in records]
        assert seqs == sorted(seqs), "events() must return seq-ascending"
        assert seqs == [1, 2, 3]

        for rec in records:
            assert rec.deal_id == deal_id
            assert rec.actor == "legal-agent"
            assert rec.type == EventType.DOCUMENT_INGESTED.value
            assert isinstance(rec.ts, datetime)

    def test_duplicate_append_returns_same_seq_no_new_doc(
        self, firestore_client: firestore.Client
    ) -> None:
        audit = DealEventAuditLog(firestore_client)
        deal_id = "deal-idempotent"
        envelope = _make_envelope(deal_id=deal_id, event_id="e-dup")

        seq_first = audit.append(envelope)
        seq_second = audit.append(envelope)

        assert seq_first == seq_second

        docs = list(
            firestore_client.collection("deals").document(deal_id).collection("events").stream()
        )
        assert len(docs) == 1

    def test_payload_json_roundtrip_nested(self, firestore_client: firestore.Client) -> None:
        audit = DealEventAuditLog(firestore_client)
        deal_id = "deal-payload"
        original: dict[str, object] = {
            "document_id": "x.pdf",
            "meta": {"size": 3},
        }
        envelope = _make_envelope(deal_id=deal_id, event_id="e-payload", payload=original)

        audit.append(envelope)
        records = audit.events(deal_id)

        assert len(records) == 1
        assert json.loads(records[0].payload_json) == original

    def test_independent_seq_counters_per_deal(self, firestore_client: firestore.Client) -> None:
        audit = DealEventAuditLog(firestore_client)

        seq_a = audit.append(_make_envelope(deal_id="deal-a", event_id="ea1"))
        seq_b = audit.append(_make_envelope(deal_id="deal-b", event_id="eb1"))

        assert seq_a == 1
        assert seq_b == 1
