"""Canonical event log tests (BUILD_PLAN D3-M4).

Emulator-backed: monotonic seq assignment, exists() lifecycle, idempotent
append, events() ordering with field equality, and independent per-deal
counters — all through the memory.event_log.EventLog writer.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from google.cloud import firestore

from memory.event_log import EventLog, EventRecord
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


class TestEventLog:
    def test_three_appends_yield_monotonic_seqs(self, firestore_client: firestore.Client) -> None:
        log = EventLog(firestore_client)
        deal_id = "deal-monotonic"

        seq1 = log.append(_make_envelope(deal_id=deal_id, event_id="e1"))
        seq2 = log.append(_make_envelope(deal_id=deal_id, event_id="e2"))
        seq3 = log.append(_make_envelope(deal_id=deal_id, event_id="e3"))

        assert seq1 == 1
        assert seq2 == 2
        assert seq3 == 3

    def test_exists_false_before_append_true_after(
        self, firestore_client: firestore.Client
    ) -> None:
        log = EventLog(firestore_client)
        deal_id = "deal-exists"
        event_id = "e-exists"

        assert log.exists(deal_id, event_id) is False

        log.append(_make_envelope(deal_id=deal_id, event_id=event_id))

        assert log.exists(deal_id, event_id) is True

    def test_duplicate_append_returns_same_seq_no_new_doc(
        self, firestore_client: firestore.Client
    ) -> None:
        log = EventLog(firestore_client)
        deal_id = "deal-dup"
        envelope = _make_envelope(deal_id=deal_id, event_id="e-dup")

        seq_first = log.append(envelope)
        seq_second = log.append(envelope)

        assert seq_first == seq_second

        docs = list(
            firestore_client.collection("deals").document(deal_id).collection("events").stream()
        )
        assert len(docs) == 1

    def test_events_ordering_and_field_equality(self, firestore_client: firestore.Client) -> None:
        log = EventLog(firestore_client)
        deal_id = "deal-fields"
        payload: dict[str, object] = {"document_id": "x.pdf", "meta": {"size": 3}}
        envelope = _make_envelope(
            deal_id=deal_id,
            event_id="e-fields",
            event_type=EventType.FINDING_CREATED,
            actor="compliance-agent",
            payload=payload,
        )

        log.append(envelope)
        records = log.events(deal_id)

        assert len(records) == 1
        rec: EventRecord = records[0]
        assert rec.event_id == "e-fields"
        assert rec.deal_id == deal_id
        assert rec.seq == 1
        assert rec.actor == "compliance-agent"
        assert rec.type == EventType.FINDING_CREATED.value
        assert isinstance(rec.ts, datetime)
        assert json.loads(rec.payload_json) == payload
        assert rec.dedupe_key == envelope.dedupe_key

    def test_independent_seq_counters_per_deal(self, firestore_client: firestore.Client) -> None:
        log = EventLog(firestore_client)

        seq_a = log.append(_make_envelope(deal_id="deal-x", event_id="ex1"))
        seq_b = log.append(_make_envelope(deal_id="deal-y", event_id="ey1"))

        assert seq_a == 1
        assert seq_b == 1
