"""Negotiation core tests (BUILD_PLAN D9-M4, vision §11).

Confidence-gated draft generation behind a human approval gate: drafts move
draft -> pending_approval -> approved -> send_logged and along no other edge;
an external send is only ever logged from the approved state (vision §11:
Negotiation Agent -> Gateway -> Human Approval -> External Channel).
"""

from __future__ import annotations

import json

import pytest
from google.cloud import firestore

from agents.negotiation.drafts import (
    DraftNotFound,
    DraftRefused,
    InvalidNegotiationTransition,
    NegotiationArtifactKind,
    NegotiationState,
    NegotiationStore,
    approve_draft,
    generate_draft,
    record_send,
    submit_for_approval,
)
from agents.tools.data_room_read import DatasetDocSource
from agents.tools.finding_create import make_finding_create
from identity.principals import principal_for
from ingestion.chunking import chunk
from ingestion.parsing import LocalParser
from registry.models import Workstream
from runtime.events import EventEnvelope, EventType, InMemoryPublisher

DEAL = "deal-falcon"


def _coc_span() -> str:
    path = DatasetDocSource().read("contract_meridian_logistics.pdf")
    assert path is not None
    doc = LocalParser().parse(path, "contract_meridian_logistics.pdf", DEAL)
    return next(c.text for c in chunk(doc) if c.locator == "clause:11.3")


def _create_finding(
    client: firestore.Client, *, confidence: float, severity: str = "critical"
) -> str:
    tool = make_finding_create(principal_for(Workstream.LEGAL, DEAL), client, DatasetDocSource())
    payload = {
        "title": "Meridian Logistics change-of-control termination right",
        "summary": "Termination right within 90 days of a change of control.",
        "severity": severity,
        "confidence": confidence,
        "evidence": [
            {
                "verbatim_span": _coc_span(),
                "document_id": "contract_meridian_logistics.pdf",
                "category": "contracts",
                "chunk_ref": "clause:11.3",
            }
        ],
        "source_documents": ["contract_meridian_logistics.pdf"],
        "affected_entities": ["Meridian Logistics, Inc."],
        "questions": [],
    }
    result = tool(finding_json=json.dumps(payload))
    assert result["decision"] == "created"
    return str(result["finding_id"])


def _negotiation_events(publisher: InMemoryPublisher) -> list[EventEnvelope]:
    envelopes = [EventEnvelope.from_json(raw) for raw in publisher.published]
    return [e for e in envelopes if e.type is EventType.NEGOTIATION_TRANSITION]


class TestDraftGeneration:
    def test_confident_finding_yields_a_draft(self, firestore_client: firestore.Client) -> None:
        publisher = InMemoryPublisher()
        finding_id = _create_finding(firestore_client, confidence=0.9)
        draft = generate_draft(
            firestore_client,
            DEAL,
            finding_id=finding_id,
            kind=NegotiationArtifactKind.REDLINE,
            publisher=publisher,
        )
        assert draft.state is NegotiationState.DRAFT
        stored = NegotiationStore(firestore_client).get(DEAL, draft.draft_id)
        assert stored.finding_id == finding_id
        assert stored.kind is NegotiationArtifactKind.REDLINE
        assert "Meridian Logistics change-of-control" in stored.body
        assert "contract_meridian_logistics.pdf" in stored.body
        events = _negotiation_events(publisher)
        assert len(events) == 1
        assert events[0].payload["to_state"] == NegotiationState.DRAFT.value

    def test_low_confidence_finding_is_refused(self, firestore_client: firestore.Client) -> None:
        finding_id = _create_finding(firestore_client, confidence=0.5)
        with pytest.raises(DraftRefused, match="confidence"):
            generate_draft(
                firestore_client,
                DEAL,
                finding_id=finding_id,
                kind=NegotiationArtifactKind.REDLINE,
            )

    def test_unknown_finding_is_rejected(self, firestore_client: firestore.Client) -> None:
        with pytest.raises(KeyError):
            generate_draft(
                firestore_client,
                DEAL,
                finding_id="no-such-finding",
                kind=NegotiationArtifactKind.REDLINE,
            )

    def test_generation_is_idempotent(self, firestore_client: firestore.Client) -> None:
        finding_id = _create_finding(firestore_client, confidence=0.9)
        first = generate_draft(
            firestore_client,
            DEAL,
            finding_id=finding_id,
            kind=NegotiationArtifactKind.REDLINE,
        )
        second = generate_draft(
            firestore_client,
            DEAL,
            finding_id=finding_id,
            kind=NegotiationArtifactKind.REDLINE,
        )
        assert first.draft_id == second.draft_id
        assert first == second
        assert len(NegotiationStore(firestore_client).list_for_finding(DEAL, finding_id)) == 1

    def test_distinct_kinds_are_distinct_drafts(self, firestore_client: firestore.Client) -> None:
        finding_id = _create_finding(firestore_client, confidence=0.9)
        redline = generate_draft(
            firestore_client,
            DEAL,
            finding_id=finding_id,
            kind=NegotiationArtifactKind.REDLINE,
        )
        question = generate_draft(
            firestore_client,
            DEAL,
            finding_id=finding_id,
            kind=NegotiationArtifactKind.CLARIFICATION_QUESTION,
        )
        assert redline.draft_id != question.draft_id
        assert len(NegotiationStore(firestore_client).list_for_finding(DEAL, finding_id)) == 2


class TestApprovalStateMachine:
    def _draft_id(
        self, client: firestore.Client, publisher: InMemoryPublisher | None = None
    ) -> str:
        finding_id = _create_finding(client, confidence=0.9)
        draft = generate_draft(
            client,
            DEAL,
            finding_id=finding_id,
            kind=NegotiationArtifactKind.SELLER_REQUEST,
            publisher=publisher,
        )
        return draft.draft_id

    def test_full_chain_to_send_logged(self, firestore_client: firestore.Client) -> None:
        publisher = InMemoryPublisher()
        draft_id = self._draft_id(firestore_client, publisher)
        store = NegotiationStore(firestore_client)

        submit_for_approval(firestore_client, DEAL, draft_id, publisher=publisher)
        assert store.get(DEAL, draft_id).state is NegotiationState.PENDING_APPROVAL

        approve_draft(
            firestore_client,
            DEAL,
            draft_id,
            approver="deal-lead@deal-falcon",
            publisher=publisher,
        )
        approved = store.get(DEAL, draft_id)
        assert approved.state is NegotiationState.APPROVED
        assert approved.approved_by == "deal-lead@deal-falcon"

        record_send(firestore_client, DEAL, draft_id, publisher=publisher)
        assert store.get(DEAL, draft_id).state is NegotiationState.SEND_LOGGED

        chain = [
            (e.payload["from_state"], e.payload["to_state"]) for e in _negotiation_events(publisher)
        ]
        assert (None, NegotiationState.DRAFT.value) in chain
        assert (NegotiationState.DRAFT.value, NegotiationState.PENDING_APPROVAL.value) in chain
        assert (
            NegotiationState.PENDING_APPROVAL.value,
            NegotiationState.APPROVED.value,
        ) in chain
        assert (NegotiationState.APPROVED.value, NegotiationState.SEND_LOGGED.value) in chain

    def test_human_approval_cannot_be_skipped(self, firestore_client: firestore.Client) -> None:
        draft_id = self._draft_id(firestore_client)
        with pytest.raises(InvalidNegotiationTransition, match="approved"):
            approve_draft(firestore_client, DEAL, draft_id, approver="deal-lead@deal-falcon")
        with pytest.raises(InvalidNegotiationTransition, match="send_logged"):
            record_send(firestore_client, DEAL, draft_id)

    def test_send_logged_is_terminal(self, firestore_client: firestore.Client) -> None:
        draft_id = self._draft_id(firestore_client)
        submit_for_approval(firestore_client, DEAL, draft_id)
        approve_draft(firestore_client, DEAL, draft_id, approver="deal-lead@deal-falcon")
        record_send(firestore_client, DEAL, draft_id)
        with pytest.raises(InvalidNegotiationTransition, match="send_logged"):
            record_send(firestore_client, DEAL, draft_id)
        with pytest.raises(InvalidNegotiationTransition, match="pending_approval"):
            submit_for_approval(firestore_client, DEAL, draft_id)

    def test_transitions_on_missing_draft_rejected(
        self, firestore_client: firestore.Client
    ) -> None:
        with pytest.raises(DraftNotFound):
            submit_for_approval(firestore_client, DEAL, "no-such-draft")


class TestEventPayloads:
    def test_transition_payload_is_auditable(self, firestore_client: firestore.Client) -> None:
        publisher = InMemoryPublisher()
        finding_id = _create_finding(firestore_client, confidence=0.9)
        draft = generate_draft(
            firestore_client,
            DEAL,
            finding_id=finding_id,
            kind=NegotiationArtifactKind.REDLINE,
            publisher=publisher,
        )
        submit_for_approval(firestore_client, DEAL, draft.draft_id, publisher=publisher)
        events = _negotiation_events(publisher)
        payload = events[-1].payload
        assert payload["draft_id"] == draft.draft_id
        assert payload["finding_id"] == finding_id
        assert json.dumps(payload, sort_keys=True)
        assert events[-1].deal_id == DEAL
