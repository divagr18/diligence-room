"""Checksum + version-chain lineage registry (BUILD_PLAN D4-M6, vision §8).

Duplicate documents and revised versions are recognized by content checksum
plus an explicit version chain so later updates (e.g. the Day-5 amendment)
supersede instead of duplicating. The register verdict decides whether the
pipeline processes a document at all: NEW and NEW_VERSION proceed;
SUPPRESSED stops reprocessing.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from google.cloud import firestore

from ingestion.models import LineageRecord, LineageStatus

# The google.* surface is untyped under our mypy override (ignore_missing_imports);
# the Firestore-shaped helpers below return that Any surface deliberately and are
# covered by the emulator-backed tests.
_FirestoreDocuments = Any


def checksum(content: bytes) -> str:
    """SHA-256 hexdigest over the raw document bytes."""
    return hashlib.sha256(content).hexdigest()


def _collection(client: firestore.Client, deal_id: str) -> _FirestoreDocuments:
    return client.collection("deals").document(deal_id).collection("documents")


def _to_record(document_id: str, data: dict[str, object]) -> LineageRecord:
    supersedes = data.get("supersedes")
    return LineageRecord(
        document_id=str(data["document_id"]),
        deal_id=str(data["deal_id"]),
        logical_key=str(data["logical_key"]),
        checksum=str(data["checksum"]),
        version=int(str(data["version"])),
        supersedes=str(supersedes) if supersedes else None,
        ingested_at=datetime.fromisoformat(str(data["ingested_at"])),
        status=LineageStatus(str(data["status"])),
    )


def get_record(client: firestore.Client, deal_id: str, document_id: str) -> LineageRecord | None:
    snapshot = _collection(client, deal_id).document(document_id).get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict()
    assert data is not None  # noqa: S101 — snapshot.exists guarantees a body
    return _to_record(document_id, data)


def _existing_for_key(
    client: firestore.Client, deal_id: str, logical_key: str
) -> list[LineageRecord]:
    # Collection scan is intentional: hackathon-scale deals have few document
    # versions per logical key; the chain must stay consistent under replays.
    records: list[LineageRecord] = []
    query = _collection(client, deal_id).where(
        filter=firestore.FieldFilter("logical_key", "==", logical_key)
    )
    for snapshot in query.stream():
        data = snapshot.to_dict()
        if data:
            records.append(_to_record(snapshot.id, data))
    return records


def register_document(
    client: firestore.Client,
    deal_id: str,
    logical_key: str,
    document_id: str,
    content: bytes,
    now: datetime | None = None,
    chains_from: str | None = None,
) -> LineageRecord:
    """Register *content* under *logical_key*; return the lineage verdict.

    Identical checksums suppress without writing; new checksums append a
    version that supersedes the latest registered document id. With
    *chains_from*, a differently-named document (e.g. an amendment)
    explicitly continues the named prior chain.
    """
    digest = checksum(content)
    stamp = now if now is not None else datetime.now(UTC)
    existing = _existing_for_key(client, deal_id, logical_key)
    for record in existing:
        if record.checksum == digest:
            return replace(record, status=LineageStatus.SUPPRESSED)
    base_version = 0
    explicit_supersedes: str | None = None
    if chains_from is not None:
        prior = _latest_for_key(client, deal_id, chains_from)
        if prior is None:
            raise ValueError(f"no registered version under logical key {chains_from!r}")
        base_version = prior.version
        explicit_supersedes = prior.logical_key
    latest = max(existing, key=lambda record: record.version, default=None)
    version = max(latest.version if latest is not None else 0, base_version) + 1
    supersedes = latest.document_id if latest is not None else explicit_supersedes
    status = LineageStatus.NEW if version == 1 and supersedes is None else LineageStatus.NEW_VERSION
    record = LineageRecord(
        document_id=document_id,
        deal_id=deal_id,
        logical_key=logical_key,
        checksum=digest,
        version=version,
        supersedes=supersedes,
        ingested_at=stamp,
        status=status,
    )
    _collection(client, deal_id).document(document_id).set(
        {
            "document_id": record.document_id,
            "deal_id": record.deal_id,
            "logical_key": record.logical_key,
            "checksum": record.checksum,
            "version": record.version,
            "supersedes": record.supersedes,
            "ingested_at": record.ingested_at.isoformat(),
            "status": record.status.value,
        },
        merge=True,
    )
    return record


def record_span_context(
    client: firestore.Client, deal_id: str, document_id: str, trace_id: str, span_id: str
) -> None:
    """Attach the ingestion span that parsed this document (D10-M4 carrier)."""
    _collection(client, deal_id).document(document_id).update(
        {"trace_id": trace_id, "span_id": span_id}
    )


def span_context_for(
    client: firestore.Client, deal_id: str, document_id: str
) -> tuple[str, str] | None:
    """Return the recorded ingestion span context for *document_id*, if any."""
    data = _collection(client, deal_id).document(document_id).get().to_dict() or {}
    trace_id = data.get("trace_id")
    span_id = data.get("span_id")
    if isinstance(trace_id, str) and isinstance(span_id, str):
        return trace_id, span_id
    return None


def _latest_for_key(
    client: firestore.Client, deal_id: str, logical_key: str
) -> LineageRecord | None:
    records = _existing_for_key(client, deal_id, logical_key)
    if not records:
        return None
    return max(records, key=lambda record: record.version)


def link_supersedes(
    client: firestore.Client,
    deal_id: str,
    new_logical_key: str,
    prior_logical_key: str,
) -> LineageRecord:
    """Chain the latest version of *new_logical_key* to *prior_logical_key*.

    Continues the prior version counter so readers can resolve the current
    version across differently-named documents (Day-7 amendment scenario).
    """
    prior = _latest_for_key(client, deal_id, prior_logical_key)
    if prior is None:
        raise ValueError(f"no registered version under logical key {prior_logical_key!r}")
    current = _latest_for_key(client, deal_id, new_logical_key)
    if current is None:
        raise ValueError(f"no registered version under logical key {new_logical_key!r}")
    updated = replace(
        current,
        supersedes=prior.logical_key,
        version=max(current.version, prior.version + 1),
    )
    _collection(client, deal_id).document(updated.document_id).set(
        {
            "document_id": updated.document_id,
            "deal_id": updated.deal_id,
            "logical_key": updated.logical_key,
            "checksum": updated.checksum,
            "version": updated.version,
            "supersedes": updated.supersedes,
            "ingested_at": updated.ingested_at.isoformat(),
            "status": updated.status.value,
        },
        merge=True,
    )
    return updated
