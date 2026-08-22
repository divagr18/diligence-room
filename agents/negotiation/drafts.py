"""Negotiation core — confidence-gated drafts behind a human approval gate
(BUILD_PLAN D9-M4, vision §11).

For selected findings the room generates proposed response artifacts (clause
redlines, seller requests, clarification questions). Generation is
confidence-gated below the candidate threshold, and nothing external ever
leaves without human approval: the state machine is

    draft -> pending_approval -> approved -> send_logged

along no other edge. A send is only logged from the approved state (vision
§11: Negotiation Agent -> Gateway -> Human Approval -> External Channel).
D12-M6 delivers the full spec on top of that machine: kind-branched,
deterministic templates (agents/negotiation/templates.py) render clause
redlines, seller requests, and counterparty clarification questions from
the finding's verified evidence; the generic header remains as fallback.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Final, Protocol

from google.cloud import firestore
from opentelemetry.trace import Tracer

from agents.negotiation.store import (
    DraftNotFound,
    NegotiationArtifactKind,
    NegotiationDraft,
    NegotiationState,
    NegotiationStore,
)
from agents.negotiation.templates import (
    render_clarification_questions,
    render_redline,
    render_seller_request,
)
from agents.tools.finding_create import EVIDENCE_CANDIDATE_THRESHOLD
from memory.findings import Finding, FindingsStore
from observability.tracing import stage_span
from runtime.events import EventEnvelope, EventType, new_event

__all__ = [
    "DraftNotFound",
    "DraftRefused",
    "InvalidNegotiationTransition",
    "NegotiationArtifactKind",
    "NegotiationDraft",
    "NegotiationState",
    "NegotiationStore",
    "approve_draft",
    "generate_draft",
    "record_send",
    "submit_for_approval",
]

_NEGOTIATION_ACTOR_TEMPLATE: Final[str] = "negotiation-agent@{deal_id}"


_ALLOWED_NEXT: Final[Mapping[NegotiationState, NegotiationState]] = {
    NegotiationState.DRAFT: NegotiationState.PENDING_APPROVAL,
    NegotiationState.PENDING_APPROVAL: NegotiationState.APPROVED,
    NegotiationState.APPROVED: NegotiationState.SEND_LOGGED,
}


class DraftRefused(Exception):
    """Raised when draft generation is refused by the confidence gate."""


class InvalidNegotiationTransition(Exception):
    """Raised on any transition outside the approval state machine."""


class _Publisher(Protocol):
    def publish(self, event: EventEnvelope) -> str: ...


def _stable_draft_id(deal_id: str, finding_id: str, kind: NegotiationArtifactKind) -> str:
    digest_input = "|".join((deal_id, finding_id, kind.value))
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:12]


def _generic_draft_body(finding: Finding, kind: NegotiationArtifactKind) -> str:
    """Header-style fallback for kinds without a dedicated template."""
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


_RENDERERS: Final[Mapping[NegotiationArtifactKind, Callable[[Finding], str]]] = {
    NegotiationArtifactKind.REDLINE: render_redline,
    NegotiationArtifactKind.SELLER_REQUEST: render_seller_request,
    NegotiationArtifactKind.CLARIFICATION_QUESTION: render_clarification_questions,
}


def _draft_body(finding: Finding, kind: NegotiationArtifactKind) -> str:
    """Kind-branched body (D12-M6 full spec): dedicated templates for the
    three known artifact kinds, generic header for any future kind."""
    renderer = _RENDERERS.get(kind)
    if renderer is not None:
        return renderer(finding)
    return _generic_draft_body(finding, kind)


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
        links=None,
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
        links=None,
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
