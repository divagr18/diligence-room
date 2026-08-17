"""Quarantine store (BUILD_PLAN D7-M3, vision §7.6).

Quarantined documents never reach agent context. Each blocked document is
recorded under ``deals/{deal_id}/quarantined/{document_id}``, the lineage
document gains ``security_status: quarantined``, and (unless the caller
already emitted one) a security event lands on the deal feed for the
dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast

from google.cloud import firestore

from runtime.events import EventEnvelope, EventType, new_event

_COLLECTION = "quarantined"
_STATUS_QUARANTINED = "quarantined"
_QUARANTINE_ACTOR = "ingestion-pipeline"
_REASON_QUARANTINE = "armor_quarantine"


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    """One quarantined document with its screening context."""

    deal_id: str
    document_id: str
    checksum: str
    version: int
    layer: str
    reason_codes: tuple[str, ...]
    rule_ids: tuple[str, ...]
    ts: datetime
    security_status: str = _STATUS_QUARANTINED


class _Publisher(Protocol):
    def publish(self, event: EventEnvelope) -> str: ...


def _from_doc(doc: dict[str, object]) -> QuarantineRecord:
    raw_codes = doc.get("reason_codes", [])
    raw_rules = doc.get("rule_ids", [])
    return QuarantineRecord(
        deal_id=str(doc["deal_id"]),
        document_id=str(doc["document_id"]),
        checksum=str(doc["checksum"]),
        version=int(str(doc["version"])),
        layer=str(doc["layer"]),
        reason_codes=tuple(str(code) for code in raw_codes) if isinstance(raw_codes, list) else (),
        rule_ids=tuple(str(rule) for rule in raw_rules) if isinstance(raw_rules, list) else (),
        ts=datetime.fromisoformat(str(doc["ts"])),
    )


class QuarantineStore:
    """Firestore-backed quarantine record store for one deal namespace."""

    def __init__(self, client: firestore.Client) -> None:
        self._client = client

    def _collection(self, deal_id: str) -> firestore.CollectionReference:
        return cast(
            firestore.CollectionReference,
            self._client.collection("deals").document(deal_id).collection(_COLLECTION),
        )

    def quarantine(
        self,
        deal_id: str,
        document_id: str,
        *,
        checksum: str,
        version: int,
        layer: str,
        reason_codes: tuple[str, ...],
        rule_ids: tuple[str, ...] = (),
        publisher: _Publisher | None = None,
        emit_event: bool = True,
        now: datetime | None = None,
    ) -> QuarantineRecord:
        """Record a blocked document, mark its lineage, and emit the feed event."""
        stamp = now if now is not None else datetime.now(UTC)
        record = QuarantineRecord(
            deal_id=deal_id,
            document_id=document_id,
            checksum=checksum,
            version=version,
            layer=layer,
            reason_codes=tuple(reason_codes),
            rule_ids=tuple(rule_ids),
            ts=stamp,
        )
        self._collection(deal_id).document(document_id).set(
            {
                "deal_id": record.deal_id,
                "document_id": record.document_id,
                "checksum": record.checksum,
                "version": record.version,
                "layer": record.layer,
                "reason_codes": list(record.reason_codes),
                "rule_ids": list(record.rule_ids),
                "security_status": record.security_status,
                "ts": record.ts.isoformat(),
            }
        )
        self._client.collection("deals").document(deal_id).collection("documents").document(
            document_id
        ).set({"security_status": record.security_status}, merge=True)
        if emit_event and publisher is not None:
            publisher.publish(
                new_event(
                    deal_id,
                    _QUARANTINE_ACTOR,
                    EventType.SECURITY_EVENT,
                    {
                        "document_id": document_id,
                        "reason": _REASON_QUARANTINE,
                        "layer": record.layer,
                        "reason_codes": list(record.reason_codes),
                        "rule_ids": list(record.rule_ids),
                        "checksum": record.checksum,
                        "version": record.version,
                    },
                    now=stamp,
                )
            )
        return record

    def is_quarantined(self, deal_id: str, document_id: str) -> bool:
        return bool(self._collection(deal_id).document(document_id).get().exists)

    def list_quarantined(self, deal_id: str) -> list[QuarantineRecord]:
        records: list[QuarantineRecord] = []
        for snapshot in self._collection(deal_id).stream():
            data = snapshot.to_dict()
            if data:
                records.append(_from_doc(data))
        records.sort(key=lambda record: record.ts)
        return records
