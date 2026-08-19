"""Event bus contract tests (BUILD_PLAN D2-M1 + D4-M7 + D6-M3, vision §7.2).

Covers: the Day-2 event types, the Day-4 pipeline additions
(document.parsed / document.routed), the Day-6 dead-letter type
(runner.dead_lettered), the envelope contract
{event_id, deal_id, ts, actor, type, payload, dedupe_key}, deterministic
dedupe keys (idempotency = event hash, D6-M2), JSON round-trip, and the
publisher interface with a Pub/Sub implementation tested against a stub client.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from runtime.events import (
    EventEnvelope,
    EventType,
    InMemoryPublisher,
    PubSubEventPublisher,
    new_event,
)

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


class TestEventType:
    def test_event_types_exact(self) -> None:
        assert {et.value for et in EventType} == {
            "document.ingested",
            "document.parsed",
            "document.routed",
            "finding.created",
            "finding.escalated",
            "gateway.decision",
            "security.event",
            "runner.dead_lettered",
            "run.bounds_exceeded",
            "evidence.rejected",
            "runner.checkpoint",
        }


class TestEnvelopeConstruction:
    def test_new_event_envelope_contract(self) -> None:
        event = new_event(
            deal_id="deal-falcon",
            actor="legal-agent@deal-falcon",
            event_type=EventType.DOCUMENT_INGESTED,
            payload={"document_id": "contract_meridian_logistics.pdf"},
        )
        assert event.deal_id == "deal-falcon"
        assert event.actor == "legal-agent@deal-falcon"
        assert event.type is EventType.DOCUMENT_INGESTED
        assert event.payload == {"document_id": "contract_meridian_logistics.pdf"}
        assert event.event_id
        assert event.ts.tzinfo is not None

    def test_rejects_naive_timestamp(self) -> None:
        with pytest.raises(ValueError, match="timezone"):
            EventEnvelope(
                event_id="e1",
                deal_id="deal-falcon",
                ts=datetime(2026, 8, 15, 12, 0),
                actor="a",
                type=EventType.SECURITY_EVENT,
                payload={},
                dedupe_key="k",
            )

    def test_rejects_empty_deal_id(self) -> None:
        with pytest.raises(ValueError, match="deal_id"):
            EventEnvelope(
                event_id="e1",
                deal_id="",
                ts=NOW,
                actor="a",
                type=EventType.SECURITY_EVENT,
                payload={},
                dedupe_key="k",
            )


class TestDedupeKey:
    def test_deterministic_for_same_content(self) -> None:
        a = new_event(
            deal_id="d",
            actor="x",
            event_type=EventType.FINDING_CREATED,
            payload={"finding_id": "LEGAL-001"},
            now=NOW,
        )
        b = new_event(
            deal_id="d",
            actor="x",
            event_type=EventType.FINDING_CREATED,
            payload={"finding_id": "LEGAL-001"},
            now=NOW,
        )
        assert a.dedupe_key == b.dedupe_key

    def test_differs_when_payload_differs(self) -> None:
        a = new_event(
            deal_id="d",
            actor="x",
            event_type=EventType.FINDING_CREATED,
            payload={"finding_id": "LEGAL-001"},
            now=NOW,
        )
        b = new_event(
            deal_id="d",
            actor="x",
            event_type=EventType.FINDING_CREATED,
            payload={"finding_id": "LEGAL-002"},
            now=NOW,
        )
        assert a.dedupe_key != b.dedupe_key

    def test_independent_of_event_id_and_ts(self) -> None:
        a = new_event(
            deal_id="d",
            actor="x",
            event_type=EventType.GATEWAY_DECISION,
            payload={"decision": "ALLOW"},
            now=NOW,
        )
        b = new_event(
            deal_id="d",
            actor="x",
            event_type=EventType.GATEWAY_DECISION,
            payload={"decision": "ALLOW"},
            now=datetime(2026, 8, 16, 9, 0, tzinfo=UTC),
        )
        assert a.event_id != b.event_id
        assert a.dedupe_key == b.dedupe_key


class TestJsonRoundTrip:
    def test_to_json_from_json_preserves_envelope(self) -> None:
        event = new_event(
            deal_id="deal-falcon",
            actor="finance-agent@deal-falcon",
            event_type=EventType.FINDING_CREATED,
            payload={"finding_id": "FIN-009", "exposure": 0.183},
            now=NOW,
        )
        restored = EventEnvelope.from_json(event.to_json())
        assert restored == event


class TestPublishers:
    def test_in_memory_publisher_records_serialized_events(self) -> None:
        publisher = InMemoryPublisher()
        event = new_event(
            deal_id="d",
            actor="a",
            event_type=EventType.SECURITY_EVENT,
            payload={"reason": "quarantined"},
        )
        publisher.publish(event)
        assert len(publisher.published) == 1
        assert EventEnvelope.from_json(publisher.published[0]) == event

    def test_pubsub_publisher_sets_dedupe_attribute_and_serializes(self) -> None:
        calls: list[tuple[bytes, dict[str, str]]] = []

        class _StubFuture:
            def result(self, timeout: float | None = None) -> str:
                return "message-1"

        class _StubClient:
            def publish(self, topic: str, data: bytes, **attributes: str) -> _StubFuture:
                calls.append((data, dict(attributes)))
                return _StubFuture()

        publisher = PubSubEventPublisher(
            topic="projects/diligence-room/topics/deal-events",
            client=_StubClient(),
        )
        event = new_event(
            deal_id="d",
            actor="a",
            event_type=EventType.DOCUMENT_INGESTED,
            payload={"document_id": "x.pdf"},
        )
        message_id = publisher.publish(event)
        assert message_id == "message-1"
        data, attributes = calls[0]
        assert attributes["dedupe_key"] == event.dedupe_key
        assert attributes["event_type"] == "document.ingested"
        assert EventEnvelope.from_json(data.decode("utf-8")) == event
