"""Cross-workstream synthesis — the Day-8 keystone (BUILD_PLAN D8-M3, vision §6).

The coordinator is an aggregation principal over findings: it reads the
contributor findings already created by the deep workstreams (each one
evidence-gated at write time), requires a convergence entity independently
flagged by every required contributor, inherits the contributors' verified
evidence, re-verifies every inherited span against its source document
(vision §19.3, defense in depth), and writes ONE escalating CRITICAL finding
to the canonical FindingsStore.

It deliberately does not write through finding_create: that tool enforces a
single-workstream AuthZ that would deny cross-workstream evidence. The
synthesis finding is anchored to the triggering workstream and links every
contributor via related_findings. Without every required contributor the
synthesis refuses — the keystone removal-proof.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Final, Protocol

from google.cloud import firestore

from agents.tools.data_room_read import DatasetDocSource, DocSource
from coordination.escalation import escalate_if_critical
from ingestion.parsing import LocalParser
from memory.findings import (
    DuplicateFindingError,
    Evidence,
    Finding,
    FindingSeverity,
    FindingsStore,
    FindingStatus,
)
from memory.partitions import partition_collection
from registry.models import Workstream
from runtime.events import EventEnvelope, EventType, new_event

REQUIRED_CONTRIBUTORS: Final[tuple[Workstream, ...]] = (
    Workstream.LEGAL,
    Workstream.FINANCE,
    Workstream.HR,
    Workstream.IP_TECH,
)

_ANCHOR_WORKSTREAM: Final[Workstream] = Workstream.LEGAL
_COORDINATOR_ACTOR: Final[str] = "coordinator"
_COORDINATOR_OWNER_PREFIX: Final[str] = f"{_COORDINATOR_ACTOR}@"


class _Publisher(Protocol):
    def publish(self, event: EventEnvelope) -> str: ...


def _stable_synthesis_id(deal_id: str, entity: str, contributor_ids: tuple[str, ...]) -> str:
    digest_input = "|".join((deal_id, "synthesis", entity, *sorted(contributor_ids)))
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:12]


def _convergence_entity(store: FindingsStore, deal_id: str) -> str | None:
    common: set[str] | None = None
    for workstream in REQUIRED_CONTRIBUTORS:
        entities = {
            entity
            for finding in store.list_for_workstream(deal_id, workstream)
            for entity in finding.affected_entities
        }
        if not entities:
            return None
        common = entities if common is None else common & entities
        if not common:
            return None
    return min(common) if common else None


def synthesize_critical(
    client: firestore.Client,
    deal_id: str,
    publisher: _Publisher | None = None,
    doc_source: DocSource | None = None,
    now: datetime | None = None,
) -> str | None:
    """Write the CRITICAL synthesis finding for *deal_id*; None when refused.

    Refusal conditions: a required contributor workstream has no finding, no
    entity is flagged by every contributor, or an inherited evidence span no
    longer resolves against its source document. A rerun returns the existing
    finding id unchanged (duplicate guard).
    """
    store = FindingsStore(client)
    entity = _convergence_entity(store, deal_id)
    if entity is None:
        return None

    source = doc_source if doc_source is not None else DatasetDocSource()
    parser = LocalParser()

    contributors: list[Finding] = []
    evidence: list[Evidence] = []
    source_documents: list[str] = []
    for workstream in REQUIRED_CONTRIBUTORS:
        convergent = sorted(
            (
                finding
                for finding in store.list_for_workstream(deal_id, workstream)
                if entity in finding.affected_entities
                and not finding.owner.startswith(_COORDINATOR_OWNER_PREFIX)
            ),
            key=lambda f: f.finding_id,
        )
        if not convergent:
            return None
        for finding in convergent:
            contributors.append(finding)
            evidence.extend(finding.evidence)
            source_documents.extend(finding.source_documents)

    if not evidence:
        return None
    for entry in evidence:
        blob = source.read(entry.document_id)
        if blob is None:
            return None
        parsed = parser.parse(blob, entry.document_id, deal_id)
        if parsed.text is None or entry.verbatim_span not in parsed.text:
            return None

    contributor_ids = tuple(f.finding_id for f in contributors)
    finding_id = _stable_synthesis_id(deal_id, entity, contributor_ids)
    stamp = now if now is not None else datetime.now(UTC)
    finding = Finding(
        finding_id=finding_id,
        deal_id=deal_id,
        workstream=_ANCHOR_WORKSTREAM,
        title="Compound customer-exit exposure threatens deal economics",
        summary=(
            f"{len(REQUIRED_CONTRIBUTORS)} workstreams independently converge on {entity}: "
            + "; ".join(f.title for f in contributors)
            + ". None of these findings alone establishes the full business impact."
        ),
        severity=FindingSeverity.CRITICAL,
        confidence=min(f.confidence for f in contributors),
        status=FindingStatus.OPEN,
        evidence=tuple(evidence),
        owner=f"{_COORDINATOR_ACTOR}@{deal_id}",
        created_at=stamp,
        updated_at=stamp,
        source_documents=tuple(dict.fromkeys(source_documents)),
        related_findings=contributor_ids,
        affected_entities=(entity,),
    )
    try:
        store.create(finding)
    except DuplicateFindingError:
        return finding_id

    if publisher is not None:
        publisher.publish(
            new_event(
                deal_id,
                _COORDINATOR_ACTOR,
                EventType.FINDING_CREATED,
                {
                    "finding_id": finding_id,
                    "title": finding.title,
                    "severity": finding.severity.value,
                    "workstream": finding.workstream.value,
                    "contributing_findings": list(contributor_ids),
                    "affected_entity": entity,
                },
                now=stamp,
            )
        )
    partition_collection(client, deal_id, _ANCHOR_WORKSTREAM).document(finding_id).set(
        {
            "finding_id": finding_id,
            "title": finding.title,
            "severity": finding.severity.value,
            "status": finding.status.value,
            "created_at": stamp.isoformat(),
        }
    )
    escalate_if_critical(client, publisher, finding, now=stamp)
    return finding_id
