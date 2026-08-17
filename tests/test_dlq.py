"""Dead-letter queue tests (BUILD_PLAN D6-M3, scenario S2; emulator-backed)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from google.cloud import firestore

from runtime.dlq import DeadLetterRecord, FirestoreDeadLetterSink
from runtime.events import EventEnvelope, EventType, new_event

DEAL = "deal-falcon"
T0 = datetime(2026, 8, 19, 9, 0, tzinfo=UTC)
T1 = datetime(2026, 8, 19, 9, 30, tzinfo=UTC)


class _OkHandler:
    def __init__(self) -> None:
        self.calls = 0

    def handle(self, envelope: EventEnvelope) -> None:
        self.calls += 1


class _RaisingHandler:
    def __init__(self) -> None:
        self.calls = 0

    def handle(self, envelope: EventEnvelope) -> None:
        self.calls += 1
        raise ValueError("still broken")


def _envelope(document_id: str = "broken.pdf") -> EventEnvelope:
    return new_event(
        deal_id=DEAL,
        actor="ingestion-pipeline",
        event_type=EventType.DOCUMENT_INGESTED,
        payload={"document_id": document_id, "bucket": "diligence-room-dataroom-deal-falcon-us"},
    )


def _events_of_type(client: firestore.Client, event_type: str) -> list[dict[str, object]]:
    docs = client.collection("deals").document(DEAL).collection("events").stream()
    return [doc.to_dict() for doc in docs if doc.to_dict().get("type") == event_type]


class TestDeadLetter:
    def test_dead_letter_creates_record(self, firestore_client: firestore.Client) -> None:
        sink = FirestoreDeadLetterSink(firestore_client)
        envelope = _envelope()
        dlq_id = sink.dead_letter(
            envelope,
            reason="max_retries_exceeded",
            last_error="ValueError: unexpected EOF",
            attempts=3,
            now=T0,
        )
        records = sink.list_dead_letters(DEAL)
        assert len(records) == 1
        record = records[0]
        assert isinstance(record, DeadLetterRecord)
        assert record.dlq_id == dlq_id
        assert record.deal_id == DEAL
        assert record.event_id == envelope.event_id
        assert record.dedupe_key == envelope.dedupe_key
        assert record.reason == "max_retries_exceeded"
        assert record.last_error == "ValueError: unexpected EOF"
        assert record.attempts == 3
        assert record.ts == T0

    def test_record_round_trips_envelope(self, firestore_client: firestore.Client) -> None:
        sink = FirestoreDeadLetterSink(firestore_client)
        envelope = _envelope()
        sink.dead_letter(envelope, reason="r", last_error="e", attempts=1, now=T0)
        record = sink.list_dead_letters(DEAL)[0]
        assert EventEnvelope.from_json(record.envelope_json) == envelope

    def test_dead_letter_emits_dead_lettered_event(
        self, firestore_client: firestore.Client
    ) -> None:
        sink = FirestoreDeadLetterSink(firestore_client)
        envelope = _envelope()
        sink.dead_letter(
            envelope, reason="max_retries_exceeded", last_error="boom", attempts=3, now=T0
        )
        events = _events_of_type(firestore_client, "runner.dead_lettered")
        assert len(events) == 1
        event = events[0]
        assert event["actor"] == envelope.actor
        import json

        payload = json.loads(str(event["payload_json"]))
        assert payload["event_id"] == envelope.event_id
        assert payload["dedupe_key"] == envelope.dedupe_key
        assert payload["reason"] == "max_retries_exceeded"
        assert payload["attempts"] == 3

    def test_list_orders_by_timestamp(self, firestore_client: firestore.Client) -> None:
        sink = FirestoreDeadLetterSink(firestore_client)
        first = _envelope("first.pdf")
        second = _envelope("second.pdf")
        sink.dead_letter(first, reason="r", last_error="e", attempts=1, now=T1)
        sink.dead_letter(second, reason="r", last_error="e", attempts=1, now=T0)
        records = sink.list_dead_letters(DEAL)
        assert [record.event_id for record in records] == [second.event_id, first.event_id]

    def test_list_is_deal_scoped(self, firestore_client: firestore.Client) -> None:
        sink = FirestoreDeadLetterSink(firestore_client)
        sink.dead_letter(_envelope(), reason="r", last_error="e", attempts=1, now=T0)
        assert sink.list_dead_letters("deal-osprey") == []


class TestRedrive:
    def test_redrive_success_removes_record(self, firestore_client: firestore.Client) -> None:
        sink = FirestoreDeadLetterSink(firestore_client)
        envelope = _envelope()
        dlq_id = sink.dead_letter(envelope, reason="r", last_error="e", attempts=3, now=T0)
        handler = _OkHandler()
        assert sink.redrive(DEAL, dlq_id, handler) is True
        assert handler.calls == 1
        assert sink.list_dead_letters(DEAL) == []

    def test_redrive_failure_retains_and_bumps_attempts(
        self, firestore_client: firestore.Client
    ) -> None:
        sink = FirestoreDeadLetterSink(firestore_client)
        envelope = _envelope()
        dlq_id = sink.dead_letter(envelope, reason="r", last_error="old", attempts=3, now=T0)
        handler = _RaisingHandler()
        assert sink.redrive(DEAL, dlq_id, handler) is False
        assert handler.calls == 1
        records = sink.list_dead_letters(DEAL)
        assert len(records) == 1
        assert records[0].attempts == 4
        assert records[0].last_error == "ValueError: still broken"

    def test_redrive_missing_record_raises(self, firestore_client: firestore.Client) -> None:
        sink = FirestoreDeadLetterSink(firestore_client)
        with pytest.raises(KeyError):
            sink.redrive(DEAL, "no-such-id", _OkHandler())
