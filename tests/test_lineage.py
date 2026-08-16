"""Lineage registry tests (BUILD_PLAN D4-M6, scenario S2; emulator-backed)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from google.cloud import firestore

from ingestion.lineage import checksum, get_record, register_document
from ingestion.models import LineageStatus

_T0 = datetime(2026, 8, 16, 9, 0, 0, tzinfo=UTC)
_T1 = datetime(2026, 8, 16, 10, 0, 0, tzinfo=UTC)


def _ref(client: firestore.Client, deal_id: str, document_id: str) -> Any:
    return (
        client.collection("deals").document(deal_id).collection("documents").document(document_id)
    )


class TestRegisterDocument:
    def test_first_registration_returns_new_with_sha256_checksum(
        self, firestore_client: firestore.Client
    ) -> None:
        content = b"contract bytes v1"
        record = register_document(
            firestore_client, "deal-falcon", "contract_customer_x", "contract-v1", content, now=_T0
        )
        assert record.status is LineageStatus.NEW
        assert record.version == 1
        assert record.supersedes is None
        assert record.checksum == checksum(content)
        assert len(record.checksum) == 64

    def test_identical_bytes_second_upload_returns_suppressed_without_write(
        self, firestore_client: firestore.Client
    ) -> None:
        content = b"identical content"
        register_document(
            firestore_client, "deal-falcon", "tech_inventory", "doc-a", content, now=_T0
        )
        suppressed = register_document(
            firestore_client, "deal-falcon", "tech_inventory", "doc-a-retry", content, now=_T1
        )
        assert suppressed.status is LineageStatus.SUPPRESSED
        assert suppressed.version == 1
        stored = _ref(firestore_client, "deal-falcon", "doc-a-retry").get()
        assert not stored.exists, "suppression must not write a duplicate record"

    def test_suppression_matches_checksum_not_document_id(
        self, firestore_client: firestore.Client
    ) -> None:
        content = b"same bytes, different ids"
        register_document(firestore_client, "deal-falcon", "roster", "upload-1", content, now=_T0)
        suppressed = register_document(
            firestore_client, "deal-falcon", "roster", "upload-2", content, now=_T1
        )
        assert suppressed.status is LineageStatus.SUPPRESSED

    def test_revised_content_returns_new_version_with_supersedes_link(
        self, firestore_client: firestore.Client
    ) -> None:
        register_document(
            firestore_client, "deal-falcon", "vendor_agreement", "vendor-v1", b"v1", now=_T0
        )
        revised = register_document(
            firestore_client, "deal-falcon", "vendor_agreement", "vendor-v2", b"v2", now=_T1
        )
        assert revised.status is LineageStatus.NEW_VERSION
        assert revised.version == 2
        assert revised.supersedes == "vendor-v1"

    def test_logical_key_stable_across_versions(self, firestore_client: firestore.Client) -> None:
        register_document(firestore_client, "d", "amendment_chain", "a1", b"x", now=_T0)
        second = register_document(firestore_client, "d", "amendment_chain", "a2", b"y", now=_T1)
        third = register_document(firestore_client, "d", "amendment_chain", "a3", b"z", now=_T1)
        assert second.logical_key == first_logical(firestore_client, "d", "a1")
        assert third.version == 3
        assert third.supersedes == "a2"

    def test_record_fields_contract_readback(self, firestore_client: firestore.Client) -> None:
        record = register_document(
            firestore_client, "deal-falcon", "financials", "fin-v1", b"$$$", now=_T0
        )
        readback = get_record(firestore_client, "deal-falcon", "fin-v1")
        assert readback is not None
        assert readback == record
        raw = _ref(firestore_client, "deal-falcon", "fin-v1").get().to_dict()
        assert raw is not None
        assert set(raw) == {
            "document_id",
            "deal_id",
            "logical_key",
            "checksum",
            "version",
            "supersedes",
            "ingested_at",
            "status",
        }
        assert raw["ingested_at"] == _T0.isoformat()

    def test_default_now_is_utc_aware(self, firestore_client: firestore.Client) -> None:
        record = register_document(firestore_client, "d", "k", "doc", b"q")
        assert record.ingested_at.tzinfo is not None


def first_logical(client: firestore.Client, deal_id: str, document_id: str) -> str:
    record = get_record(client, deal_id, document_id)
    assert record is not None
    return record.logical_key
