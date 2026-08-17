"""Quarantine store tests (BUILD_PLAN D7-M3, vision §7.6).

Quarantined documents never reach agent context: each blocked document lands
in ``deals/{deal}/quarantined/{doc}``, the lineage document's
``security_status`` flips to ``quarantined``, and a security event lands on
the deal feed (unless the caller already emitted one).
"""

from __future__ import annotations

from datetime import UTC, datetime

from google.cloud import firestore

from armor.quarantine import QuarantineRecord, QuarantineStore
from ingestion.lineage import register_document
from runtime.events import EventEnvelope, EventType, InMemoryPublisher

DEAL = "deal-falcon"
NOW = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
LATER = datetime(2026, 8, 20, 9, 30, tzinfo=UTC)


def _register(client: firestore.Client, document_id: str, blob: bytes) -> tuple[str, int]:
    record = register_document(client, DEAL, document_id, document_id, blob)
    return record.checksum, record.version


class TestQuarantineWrite:
    def test_quarantine_writes_record(self, firestore_client: firestore.Client) -> None:
        checksum, version = _register(firestore_client, "poisoned.pdf", b"hostile-bytes")
        store = QuarantineStore(firestore_client)
        record = store.quarantine(
            DEAL,
            "poisoned.pdf",
            checksum=checksum,
            version=version,
            layer="model_armor",
            reason_codes=("authority_forgery", "exfiltration"),
            rule_ids=("authority.forgery", "exfil.mailto"),
            publisher=InMemoryPublisher(),
            now=NOW,
        )
        assert isinstance(record, QuarantineRecord)
        data = (
            firestore_client.collection("deals")
            .document(DEAL)
            .collection("quarantined")
            .document("poisoned.pdf")
            .get()
        )
        assert data.exists
        body = data.to_dict()
        assert body is not None
        assert body["layer"] == "model_armor"
        assert body["reason_codes"] == ["authority_forgery", "exfiltration"]
        assert body["rule_ids"] == ["authority.forgery", "exfil.mailto"]
        assert body["checksum"] == checksum
        assert body["version"] == version
        assert body["security_status"] == "quarantined"
        assert body["ts"] == NOW.isoformat()

    def test_quarantine_updates_lineage_security_status(
        self, firestore_client: firestore.Client
    ) -> None:
        _register(firestore_client, "poisoned.pdf", b"hostile-bytes")
        QuarantineStore(firestore_client).quarantine(
            DEAL,
            "poisoned.pdf",
            checksum="abc",
            version=1,
            layer="model_armor",
            reason_codes=("exfiltration",),
            publisher=InMemoryPublisher(),
            now=NOW,
        )
        lineage = (
            firestore_client.collection("deals")
            .document(DEAL)
            .collection("documents")
            .document("poisoned.pdf")
            .get()
            .to_dict()
        )
        assert lineage is not None
        assert lineage["security_status"] == "quarantined"
        assert lineage["document_id"] == "poisoned.pdf", "merge must preserve lineage fields"


class TestSecurityEvent:
    def test_quarantine_emits_security_event(self, firestore_client: firestore.Client) -> None:
        checksum, version = _register(firestore_client, "poisoned.pdf", b"hostile-bytes")
        publisher = InMemoryPublisher()
        QuarantineStore(firestore_client).quarantine(
            DEAL,
            "poisoned.pdf",
            checksum=checksum,
            version=version,
            layer="model_armor",
            reason_codes=("authority_forgery",),
            rule_ids=("authority.forgery",),
            publisher=publisher,
            now=NOW,
        )
        events = [EventEnvelope.from_json(raw) for raw in publisher.published]
        assert len(events) == 1
        event = events[0]
        assert event.type is EventType.SECURITY_EVENT
        assert event.actor == "ingestion-pipeline"
        assert event.payload["reason"] == "armor_quarantine"
        assert event.payload["document_id"] == "poisoned.pdf"
        assert event.payload["layer"] == "model_armor"
        assert event.payload["reason_codes"] == ["authority_forgery"]
        assert event.payload["rule_ids"] == ["authority.forgery"]

    def test_quarantine_without_emit_stays_silent(self, firestore_client: firestore.Client) -> None:
        _register(firestore_client, "poisoned.pdf", b"hostile-bytes")
        publisher = InMemoryPublisher()
        QuarantineStore(firestore_client).quarantine(
            DEAL,
            "poisoned.pdf",
            checksum="abc",
            version=1,
            layer="sentinel_tripwire",
            reason_codes=("ignore_instructions",),
            publisher=publisher,
            emit_event=False,
            now=NOW,
        )
        assert publisher.published == []
        assert QuarantineStore(firestore_client).is_quarantined(DEAL, "poisoned.pdf")


class TestReadback:
    def test_is_quarantined_false_until_recorded(self, firestore_client: firestore.Client) -> None:
        store = QuarantineStore(firestore_client)
        assert store.is_quarantined(DEAL, "ghost.pdf") is False
        _register(firestore_client, "poisoned.pdf", b"hostile-bytes")
        store.quarantine(
            DEAL,
            "poisoned.pdf",
            checksum="abc",
            version=1,
            layer="model_armor",
            reason_codes=("exfiltration",),
            publisher=InMemoryPublisher(),
            now=NOW,
        )
        assert store.is_quarantined(DEAL, "poisoned.pdf") is True

    def test_list_quarantined_sorted_by_timestamp(self, firestore_client: firestore.Client) -> None:
        store = QuarantineStore(firestore_client)
        for name, blob, stamp in (
            ("second.pdf", b"second-hostile", LATER),
            ("first.pdf", b"first-hostile", NOW),
        ):
            checksum, version = _register(firestore_client, name, blob)
            store.quarantine(
                DEAL,
                name,
                checksum=checksum,
                version=version,
                layer="model_armor",
                reason_codes=("authority_forgery",),
                publisher=InMemoryPublisher(),
                now=stamp,
            )
        records = store.list_quarantined(DEAL)
        assert [record.document_id for record in records] == ["first.pdf", "second.pdf"]
        assert all(record.security_status == "quarantined" for record in records)
