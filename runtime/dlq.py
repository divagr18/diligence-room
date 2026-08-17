"""Dead-letter queue (BUILD_PLAN D6-M3, vision §7.2 failure tolerance).

Events that exhaust their retry budget land here instead of being dropped:
the envelope is stored verbatim (replayable), the failure context is recorded,
and a ``runner.dead_lettered`` event is appended to the canonical event log.
Redrive re-runs a handler against the stored envelope and removes the record
only on success.

Live mapping (documented, not built Day 6): in production the same semantics
attach to a Pub/Sub dead-letter topic on the deal-events subscription; the
offline/test sink is Firestore-backed at ``deals/{deal_id}/dlq/{dlq_id}``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast

from google.cloud import firestore

from memory.event_log import EventLog
from runtime.events import EventEnvelope, EventType, new_event

_DLQ_COLLECTION = "dlq"


class RedriveHandler(Protocol):
    def handle(self, envelope: EventEnvelope) -> None: ...


@dataclass(frozen=True, slots=True)
class DeadLetterRecord:
    """One dead-lettered event with its failure context."""

    dlq_id: str
    deal_id: str
    event_id: str
    dedupe_key: str
    envelope_json: str
    reason: str
    last_error: str
    attempts: int
    ts: datetime


def _record_to_doc(record: DeadLetterRecord) -> dict[str, object]:
    return {
        "dlq_id": record.dlq_id,
        "deal_id": record.deal_id,
        "event_id": record.event_id,
        "dedupe_key": record.dedupe_key,
        "envelope_json": record.envelope_json,
        "reason": record.reason,
        "last_error": record.last_error,
        "attempts": record.attempts,
        "ts": record.ts.isoformat(),
    }


def _record_from_doc(doc: dict[str, object]) -> DeadLetterRecord:
    return DeadLetterRecord(
        dlq_id=str(doc["dlq_id"]),
        deal_id=str(doc["deal_id"]),
        event_id=str(doc["event_id"]),
        dedupe_key=str(doc["dedupe_key"]),
        envelope_json=str(doc["envelope_json"]),
        reason=str(doc["reason"]),
        last_error=str(doc["last_error"]),
        attempts=int(str(doc["attempts"])),
        ts=datetime.fromisoformat(str(doc["ts"])),
    )


class FirestoreDeadLetterSink:
    """Firestore-backed DLQ at deals/{deal_id}/dlq/{dlq_id}."""

    def __init__(self, client: firestore.Client) -> None:
        self._client = client
        self._event_log = EventLog(client)

    def _collection(self, deal_id: str) -> firestore.CollectionReference:
        return cast(
            firestore.CollectionReference,
            self._client.collection("deals").document(deal_id).collection(_DLQ_COLLECTION),
        )

    def dead_letter(
        self,
        envelope: EventEnvelope,
        *,
        reason: str,
        last_error: str,
        attempts: int,
        now: datetime | None = None,
    ) -> str:
        """Store the envelope and emit a runner.dead_lettered audit event."""
        stamp = now if now is not None else datetime.now(UTC)
        dlq_id = uuid.uuid4().hex
        record = DeadLetterRecord(
            dlq_id=dlq_id,
            deal_id=envelope.deal_id,
            event_id=envelope.event_id,
            dedupe_key=envelope.dedupe_key,
            envelope_json=envelope.to_json(),
            reason=reason,
            last_error=last_error,
            attempts=attempts,
            ts=stamp,
        )
        self._collection(envelope.deal_id).document(dlq_id).set(_record_to_doc(record))
        event = new_event(
            deal_id=envelope.deal_id,
            actor=envelope.actor,
            event_type=EventType.DEAD_LETTERED,
            payload={
                "event_id": envelope.event_id,
                "dedupe_key": envelope.dedupe_key,
                "reason": reason,
                "attempts": attempts,
            },
            now=stamp,
        )
        self._event_log.append(event)
        return dlq_id

    def list_dead_letters(self, deal_id: str) -> list[DeadLetterRecord]:
        records: list[DeadLetterRecord] = []
        for snapshot in self._collection(deal_id).stream():
            data = snapshot.to_dict()
            if data:
                records.append(_record_from_doc(data))
        records.sort(key=lambda record: record.ts)
        return records

    def redrive(self, deal_id: str, dlq_id: str, handler: RedriveHandler) -> bool:
        """Re-run *handler* on the stored envelope; remove the record on success.

        Returns True on success. On failure the record stays, with attempts
        bumped and the latest error recorded. Raises KeyError for unknown ids.
        """
        doc_ref = self._collection(deal_id).document(dlq_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            raise KeyError(f"dead letter {dlq_id!r} not found for deal {deal_id!r}")
        data = snapshot.to_dict()
        assert data is not None
        record = _record_from_doc(data)
        envelope = EventEnvelope.from_json(record.envelope_json)
        try:
            handler.handle(envelope)
        except Exception as exc:  # noqa: BLE001 — the DLQ must survive any handler error
            doc_ref.update(
                {
                    "attempts": record.attempts + 1,
                    "last_error": f"{type(exc).__name__}: {exc}",
                }
            )
            return False
        doc_ref.delete()
        return True
