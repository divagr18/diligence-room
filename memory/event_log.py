"""Canonical append-only event log (BUILD_PLAN D3-M4).

Single writer for EventEnvelope persistence: writes to
deals/{deal_id}/events/{event_id} with transactional seq assignment.
Append is idempotent on event_id — a duplicate returns the existing seq
without creating a new document (vision §7.3, D6-M2).

gateway/audit.py delegates here; this module is the source of truth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from google.cloud import firestore

from runtime.events import EventEnvelope


def _canonical_payload(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True, slots=True)
class EventRecord:
    event_id: str
    deal_id: str
    ts: datetime
    seq: int
    actor: str
    type: str
    payload_json: str
    dedupe_key: str


class EventLog:
    """Firestore-backed append-only event log with per-deal monotonic seq.

    Each deal has an independent monotonic seq counter starting at 1.
    Append is idempotent on event_id: a duplicate returns the stored seq.
    """

    def __init__(self, client: firestore.Client) -> None:
        self._client = client

    def _events_collection(self, deal_id: str) -> Any:
        return self._client.collection("deals").document(deal_id).collection("events")

    def append(self, envelope: EventEnvelope) -> int:
        transaction = self._client.transaction()

        @firestore.transactional
        def _append_txn(txn: Any, env: EventEnvelope) -> int:
            events_col = self._events_collection(env.deal_id)
            doc_ref = events_col.document(env.event_id)

            snapshot = doc_ref.get(transaction=txn)
            if snapshot.exists:
                existing: dict[str, Any] = snapshot.to_dict() or {}
                return int(existing["seq"])

            last_docs = list(
                events_col.order_by("seq", direction=firestore.Query.DESCENDING)
                .limit(1)
                .stream(transaction=txn)
            )
            last_seq = int(last_docs[0].to_dict()["seq"]) if last_docs else 0
            next_seq = last_seq + 1

            txn.set(
                doc_ref,
                {
                    "event_id": env.event_id,
                    "deal_id": env.deal_id,
                    "ts": env.ts,
                    "seq": next_seq,
                    "actor": env.actor,
                    "type": env.type.value,
                    "payload_json": _canonical_payload(dict(env.payload)),
                    "dedupe_key": env.dedupe_key,
                },
            )
            return next_seq

        result: int = _append_txn(transaction, envelope)
        return result

    def exists(self, deal_id: str, event_id: str) -> bool:
        doc_ref = self._events_collection(deal_id).document(event_id)
        return bool(doc_ref.get().exists)

    def events(self, deal_id: str) -> list[EventRecord]:
        docs = (
            self._events_collection(deal_id)
            .order_by("seq", direction=firestore.Query.ASCENDING)
            .stream()
        )
        out: list[EventRecord] = []
        for doc in docs:
            d: dict[str, Any] = doc.to_dict() or {}
            out.append(
                EventRecord(
                    event_id=str(d["event_id"]),
                    deal_id=str(d["deal_id"]),
                    ts=d["ts"],
                    seq=int(d["seq"]),
                    actor=str(d["actor"]),
                    type=str(d["type"]),
                    payload_json=str(d["payload_json"]),
                    dedupe_key=str(d["dedupe_key"]),
                )
            )
        return out

    def list_for_type(self, deal_id: str, event_type: str) -> list[EventRecord]:
        return [record for record in self.events(deal_id) if record.type == event_type]


class EventLogPublisher:
    """Publisher adapter that persists envelopes through the canonical log.

    Satisfies the ``_Publisher`` protocol wherever the runtime publishes
    events (e.g. ``agents.negotiation.drafts``), so every transition lands
    in ``deals/{deal_id}/events`` with the append idempotency of EventLog.
    """

    def __init__(self, event_log: EventLog) -> None:
        self._event_log = event_log

    def publish(self, event: EventEnvelope) -> str:
        self._event_log.append(event)
        return event.event_id
