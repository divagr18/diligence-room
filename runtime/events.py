"""Deal event bus (BUILD_PLAN D2-M1, vision §7.2).

Typed events with the envelope contract {event_id, deal_id, ts, actor, type,
payload, dedupe_key}. The dedupe key is a content hash excluding event_id/ts,
which makes it the idempotency key for runtime dispatch (D6-M2) and replay (D13).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class EventType(StrEnum):
    DOCUMENT_INGESTED = "document.ingested"
    DOCUMENT_PARSED = "document.parsed"
    DOCUMENT_ROUTED = "document.routed"
    FINDING_CREATED = "finding.created"
    GATEWAY_DECISION = "gateway.decision"
    SECURITY_EVENT = "security.event"
    DEAD_LETTERED = "runner.dead_lettered"


def _canonical_json(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_dedupe_key(
    deal_id: str, actor: str, event_type: EventType, payload: Mapping[str, object]
) -> str:
    digest_input = "|".join((deal_id, actor, event_type.value, _canonical_json(payload)))
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_id: str
    deal_id: str
    ts: datetime
    actor: str
    type: EventType
    payload: Mapping[str, object]
    dedupe_key: str

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id must be set")
        if not self.deal_id:
            raise ValueError("deal_id must be set")
        if self.ts.tzinfo is None:
            raise ValueError("ts must be timezone-aware (UTC)")

    def to_json(self) -> str:
        return json.dumps(
            {
                "event_id": self.event_id,
                "deal_id": self.deal_id,
                "ts": self.ts.isoformat(),
                "actor": self.actor,
                "type": self.type.value,
                "payload": dict(self.payload),
                "dedupe_key": self.dedupe_key,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> EventEnvelope:
        data = json.loads(raw)
        return cls(
            event_id=str(data["event_id"]),
            deal_id=str(data["deal_id"]),
            ts=datetime.fromisoformat(str(data["ts"])),
            actor=str(data["actor"]),
            type=EventType(str(data["type"])),
            payload=dict(data["payload"]),
            dedupe_key=str(data["dedupe_key"]),
        )


def new_event(
    deal_id: str,
    actor: str,
    event_type: EventType,
    payload: Mapping[str, object],
    now: datetime | None = None,
) -> EventEnvelope:
    ts = now if now is not None else datetime.now(UTC)
    return EventEnvelope(
        event_id=str(uuid.uuid4()),
        deal_id=deal_id,
        ts=ts,
        actor=actor,
        type=event_type,
        payload=dict(payload),
        dedupe_key=compute_dedupe_key(deal_id, actor, event_type, payload),
    )


class InMemoryPublisher:
    """Publisher for tests and local runs; keeps serialized envelopes."""

    def __init__(self) -> None:
        self.published: list[str] = []

    def publish(self, event: EventEnvelope) -> str:
        self.published.append(event.to_json())
        return event.event_id


class PubSubEventPublisher:
    """Publishes envelopes to a Pub/Sub topic with the dedupe key as attribute."""

    def __init__(
        self,
        topic: str,
        client: object | None = None,
    ) -> None:
        self.topic = topic
        self._client = client

    @property
    def client(self) -> object:
        if self._client is None:
            from importlib import import_module

            pubsub_v1 = import_module("google.cloud.pubsub_v1")
            self._client = pubsub_v1.PublisherClient()
        return self._client

    def publish(self, event: EventEnvelope) -> str:
        future = self.client.publish(  # type: ignore[attr-defined]
            self.topic,
            event.to_json().encode("utf-8"),
            dedupe_key=event.dedupe_key,
            event_id=event.event_id,
            event_type=event.type.value,
            deal_id=event.deal_id,
        )
        message_id: str = future.result(timeout=30)
        return message_id
