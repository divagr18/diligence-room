"""Negotiation core — confidence-gated drafts behind a human approval gate
(BUILD_PLAN D9-M4, vision §11).

For selected findings the room generates proposed response artifacts (clause
redlines, seller requests, clarification questions). Generation is
confidence-gated below the candidate threshold, and nothing external ever
leaves without human approval: the state machine is

    draft -> pending_approval -> approved -> send_logged

along no other edge. A send is only logged from the approved state (vision
§11: Negotiation Agent -> Gateway -> Human Approval -> External Channel).
This is the CUTLINE-1 minimal configuration: draft + approval gate + logged
send; the full spec (redline templates, counterparty question banks) is the
Day-12 target.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Protocol, cast

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from opentelemetry.trace import Tracer

from agents.tools.finding_create import EVIDENCE_CANDIDATE_THRESHOLD
from memory.findings import Finding, FindingsStore
from observability.tracing import stage_span
from runtime.events import EventEnvelope, EventType, new_event

_COLLECTION: Final[str] = "negotiations"
_NEGOTIATION_ACTOR_TEMPLATE: Final[str] = "negotiation-agent@{deal_id}"


class NegotiationArtifactKind(StrEnum):
    REDLINE = "clause_redline"
    SELLER_REQUEST = "seller_request"
    CLARIFICATION_QUESTION = "clarification_question"


class NegotiationState(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SEND_LOGGED = "send_logged"


_ALLOWED_NEXT: Final[Mapping[NegotiationState, NegotiationState]] = {
    NegotiationState.DRAFT: NegotiationState.PENDING_APPROVAL,
    NegotiationState.PENDING_APPROVAL: NegotiationState.APPROVED,
    NegotiationState.APPROVED: NegotiationState.SEND_LOGGED,
}


class DraftNotFound(KeyError):
    """Raised when a negotiation draft does not exist in Firestore."""


class DraftRefused(Exception):
    """Raised when draft generation is refused by the confidence gate."""


class InvalidNegotiationTransition(Exception):
    """Raised on any transition outside the approval state machine."""


@dataclass(frozen=True, slots=True)
class NegotiationDraft:
    """One negotiation artifact bound to one finding."""

    draft_id: str
    deal_id: str
    finding_id: str
    kind: NegotiationArtifactKind
    state: NegotiationState
    body: str
    approved_by: str | None
    created_at: datetime
    updated_at: datetime


def _draft_to_doc(draft: NegotiationDraft) -> dict[str, object]:
    return {
        "draft_id": draft.draft_id,
        "deal_id": draft.deal_id,
        "finding_id": draft.finding_id,
        "kind": draft.kind.value,
        "state": draft.state.value,
        "body": draft.body,
        "approved_by": draft.approved_by,
        "created_at": draft.created_at.isoformat(),
        "updated_at": draft.updated_at.isoformat(),
    }


def _draft_from_doc(doc: dict[str, object]) -> NegotiationDraft:
    raw_approved_by = doc.get("approved_by")
    return NegotiationDraft(
        draft_id=str(doc["draft_id"]),
        deal_id=str(doc["deal_id"]),
        finding_id=str(doc["finding_id"]),
        kind=NegotiationArtifactKind(str(doc["kind"])),
        state=NegotiationState(str(doc["state"])),
        body=str(doc["body"]),
        approved_by=raw_approved_by if isinstance(raw_approved_by, str) else None,
        created_at=datetime.fromisoformat(str(doc["created_at"])),
        updated_at=datetime.fromisoformat(str(doc["updated_at"])),
    )


class NegotiationStore:
    """Firestore-backed drafts at deals/{deal_id}/negotiations/{draft_id}."""

    def __init__(self, client: firestore.Client) -> None:
        self._client = client

    def _collection(self, deal_id: str) -> firestore.CollectionReference:
        return cast(
            firestore.CollectionReference,
            self._client.collection("deals").document(deal_id).collection(_COLLECTION),
        )

    def create(self, draft: NegotiationDraft) -> None:
        self._collection(draft.deal_id).document(draft.draft_id).set(_draft_to_doc(draft))

    def update(self, draft: NegotiationDraft) -> None:
        ref = self._collection(draft.deal_id).document(draft.draft_id)
        if not ref.get().exists:
            raise DraftNotFound(draft.draft_id)
        ref.set(_draft_to_doc(draft))

    def get(self, deal_id: str, draft_id: str) -> NegotiationDraft:
        snapshot = self._collection(deal_id).document(draft_id).get()
        data = snapshot.to_dict()
        if data is None:
            raise DraftNotFound(draft_id)
        return _draft_from_doc(data)

    def list_for_finding(self, deal_id: str, finding_id: str) -> list[NegotiationDraft]:
        docs = (
            self._collection(deal_id)
            .where(filter=FieldFilter("finding_id", "==", finding_id))
            .stream()
        )
        drafts: list[NegotiationDraft] = []
        for doc in docs:
            data = doc.to_dict()
            if data is None:
                continue
            drafts.append(_draft_from_doc(data))
        return drafts


class _Publisher(Protocol):
    def publish(self, event: EventEnvelope) -> str: ...


def _stable_draft_id(deal_id: str, finding_id: str, kind: NegotiationArtifactKind) -> str:
    digest_input = "|".join((deal_id, finding_id, kind.value))
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:12]


def _draft_body(finding: Finding, kind: NegotiationArtifactKind) -> str:
    evidence_lines = tuple(
        f"- {entry.document_id}: \u201c{entry.verbatim_span}\u201d" for entry in finding.evidence
    )
    return "\n".join(
        (
            f"Artifact kind: {kind.value}",
            f"Finding: {finding.finding_id} \u2014 {finding.title}",
            f"Rationale: {finding.summary}",
            "Evidence:",
            *evidence_lines,
        )
    )


def _emit_transition(
    publisher: _Publisher | None,
    draft: NegotiationDraft,
    from_state: NegotiationState | None,
    to_state: NegotiationState,
    actor: str,
    now: datetime | None,
) -> None:
    if publisher is None:
        return
    publisher.publish(
        new_event(
            draft.deal_id,
            actor,
            EventType.NEGOTIATION_TRANSITION,
            {
                "draft_id": draft.draft_id,
                "finding_id": draft.finding_id,
                "kind": draft.kind.value,
                "from_state": from_state.value if from_state is not None else None,
                "to_state": to_state.value,
                "actor": actor,
            },
            now=now,
        )
    )


def generate_draft(
    client: firestore.Client,
    deal_id: str,
    finding_id: str,
    kind: NegotiationArtifactKind,
    publisher: _Publisher | None = None,
    now: datetime | None = None,
    tracer: Tracer | None = None,
) -> NegotiationDraft:
    """Generate (or return) the draft artifact for *finding_id*.

    Refused below the candidate-confidence threshold: a finding the evidence
    gate would cap at candidate cannot drive material sent outside the room.
    Regeneration is idempotent — the stable draft id returns the stored draft.
    """
    finding = FindingsStore(client).get(deal_id, finding_id)
    if finding.confidence < EVIDENCE_CANDIDATE_THRESHOLD:
        raise DraftRefused(
            f"finding {finding_id} confidence {finding.confidence} is below the "
            f"candidate threshold {EVIDENCE_CANDIDATE_THRESHOLD}; refusing to draft"
        )
    stamp = now if now is not None else datetime.now(UTC)
    actor = _NEGOTIATION_ACTOR_TEMPLATE.format(deal_id=deal_id)
    draft_id = _stable_draft_id(deal_id, finding_id, kind)
    store = NegotiationStore(client)
    try:
        return store.get(deal_id, draft_id)
    except DraftNotFound:
        pass
    draft = NegotiationDraft(
        draft_id=draft_id,
        deal_id=deal_id,
        finding_id=finding_id,
        kind=kind,
        state=NegotiationState.DRAFT,
        body=_draft_body(finding, kind),
        approved_by=None,
        created_at=stamp,
        updated_at=stamp,
    )
    with stage_span(
        tracer,
        "negotiation.transition",
        **{
            "negotiation.kind": kind.value,
            "negotiation.from_state": "none",
            "negotiation.to_state": NegotiationState.DRAFT.value,
            "negotiation.draft_id": draft_id,
        },
    ):
        store.create(draft)
        _emit_transition(publisher, draft, None, NegotiationState.DRAFT, actor, stamp)
    return draft


def _transition(
    client: firestore.Client,
    deal_id: str,
    draft_id: str,
    target: NegotiationState,
    approver: str | None,
    publisher: _Publisher | None,
    now: datetime | None,
    tracer: Tracer | None = None,
) -> NegotiationDraft:
    store = NegotiationStore(client)
    draft = store.get(deal_id, draft_id)
    if _ALLOWED_NEXT.get(draft.state) is not target:
        raise InvalidNegotiationTransition(
            f"draft {draft_id} cannot move from {draft.state.value} to {target.value}"
        )
    stamp = now if now is not None else datetime.now(UTC)
    actor = (
        approver if approver is not None else _NEGOTIATION_ACTOR_TEMPLATE.format(deal_id=deal_id)
    )
    updated = replace(
        draft,
        state=target,
        approved_by=approver if approver is not None else draft.approved_by,
        updated_at=stamp,
    )
    with stage_span(
        tracer,
        "negotiation.transition",
        **{
            "negotiation.kind": draft.kind.value,
            "negotiation.from_state": draft.state.value,
            "negotiation.to_state": target.value,
            "negotiation.draft_id": draft_id,
        },
    ):
        store.update(updated)
        _emit_transition(publisher, updated, draft.state, target, actor, stamp)
    return updated


def submit_for_approval(
    client: firestore.Client,
    deal_id: str,
    draft_id: str,
    publisher: _Publisher | None = None,
    now: datetime | None = None,
    tracer: Tracer | None = None,
) -> NegotiationDraft:
    """draft -> pending_approval."""
    return _transition(
        client, deal_id, draft_id, NegotiationState.PENDING_APPROVAL, None, publisher, now, tracer
    )


def approve_draft(
    client: firestore.Client,
    deal_id: str,
    draft_id: str,
    approver: str,
    publisher: _Publisher | None = None,
    now: datetime | None = None,
    tracer: Tracer | None = None,
) -> NegotiationDraft:
    """pending_approval -> approved; records the approving human."""
    return _transition(
        client, deal_id, draft_id, NegotiationState.APPROVED, approver, publisher, now, tracer
    )


def record_send(
    client: firestore.Client,
    deal_id: str,
    draft_id: str,
    publisher: _Publisher | None = None,
    now: datetime | None = None,
    tracer: Tracer | None = None,
) -> NegotiationDraft:
    """approved -> send_logged; the only state from which a send may leave."""
    return _transition(
        client, deal_id, draft_id, NegotiationState.SEND_LOGGED, None, publisher, now, tracer
    )
