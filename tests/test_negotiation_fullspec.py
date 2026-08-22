"""Full-spec negotiation tests (BUILD_PLAN D12-M6, vision §11).

CUTLINE-1 minimal stays the floor: the 4-state machine and the 0.75
candidate gate must survive untouched. On top of it, the kind-branched
deterministic templates render every evidence verbatim_span and every
affected entity into redlines, seller requests, and the three-question
counterparty bank — no LLM anywhere.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from google.cloud import firestore

from agents.negotiation.drafts import (
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
from agents.negotiation.templates import (
    render_clarification_questions,
    render_redline,
    render_seller_request,
)
from memory.findings import Evidence, Finding, FindingSeverity, FindingsStore, FindingStatus
from registry.models import Workstream
from runtime.events import EventEnvelope, EventType, InMemoryPublisher

DEAL = "deal-falcon"

_SPAN_COC = "either party may terminate this agreement within 90 days of a change of control"
_SPAN_NOTICE = "written notice must be delivered to the counterparty no later than 10 business days"
_SPAN_FIN = "Meridian Logistics, Inc. represented 18.3% of projected FY27 revenue"


def _finding(
    *,
    confidence: float = 0.9,
    questions: tuple[str, ...] = (),
    affected_entities: tuple[str, ...] = ("Meridian Logistics, Inc.", "Project Falcon"),
) -> Finding:
    stamp = datetime(2026, 8, 23, 12, 0, 0, tzinfo=UTC)
    return Finding(
        finding_id=f"FS-{confidence:.2f}".replace("0.", ""),
        deal_id=DEAL,
        workstream=Workstream.LEGAL,
        title="Meridian Logistics change-of-control termination right",
        summary="Termination right within 90 days of a change of control.",
        severity=FindingSeverity.CRITICAL,
        confidence=confidence,
        status=FindingStatus.OPEN,
        evidence=(
            Evidence(
                verbatim_span=_SPAN_COC,
                document_id="contract_meridian_logistics.pdf",
                chunk_ref="clause:11.3",
            ),
            Evidence(
                verbatim_span=_SPAN_NOTICE,
                document_id="contract_meridian_logistics.pdf",
                chunk_ref="clause:11.4",
            ),
        ),
        source_documents=("contract_meridian_logistics.pdf",),
        affected_entities=affected_entities,
        questions=questions,
        owner="legal-agent@deal-falcon",
        created_at=stamp,
        updated_at=stamp,
    )


def _seed(client: firestore.Client, finding: Finding) -> str:
    FindingsStore(client).create(finding)
    return finding.finding_id


def _quoted(span: str) -> str:
    return f"“{span}”"


class TestTemplateRendering:
    """Each renderer quotes every evidence span, names every affected entity,
    and is deterministic (same finding -> identical body)."""

    @pytest.mark.parametrize(
        "renderer",
        [render_redline, render_seller_request, render_clarification_questions],
        ids=["redline", "seller_request", "clarification_questions"],
    )
    def test_quotes_every_evidence_span(self, renderer: Callable[[Finding], str]) -> None:
        finding = _finding()
        body = renderer(finding)
        assert _quoted(_SPAN_COC) in body
        assert _quoted(_SPAN_NOTICE) in body
        assert "contract_meridian_logistics.pdf" in body

    @pytest.mark.parametrize(
        "renderer",
        [render_redline, render_seller_request, render_clarification_questions],
        ids=["redline", "seller_request", "clarification_questions"],
    )
    def test_names_affected_entities(self, renderer: Callable[[Finding], str]) -> None:
        finding = _finding()
        body = renderer(finding)
        for entity in finding.affected_entities:
            assert entity in body

    @pytest.mark.parametrize(
        "renderer",
        [render_redline, render_seller_request, render_clarification_questions],
        ids=["redline", "seller_request", "clarification_questions"],
    )
    def test_rendering_is_deterministic_with_no_llm(
        self, renderer: Callable[[Finding], str]
    ) -> None:
        finding = _finding()
        assert renderer(finding) == renderer(finding)

    def test_redline_carries_a_proposed_frame(self) -> None:
        body = render_redline(_finding())
        assert "PROPOSED CLAUSE REDLINE" in body
        assert "Proposed frame:" in body
        assert "Qualify or strike the provision" in body

    def test_seller_request_carries_a_request_frame(self) -> None:
        body = render_seller_request(_finding())
        assert "SELLER REQUEST" in body
        assert "Request to seller:" in body
        assert "written confirmation" in body

    def test_clarification_renders_the_three_question_bank(self) -> None:
        body = render_clarification_questions(_finding())
        assert "Q1." in body
        assert "Q2." in body
        assert "Q3." in body
        assert "Q4." not in body

    def test_empty_entities_render_honestly(self) -> None:
        body = render_redline(_finding(affected_entities=()))
        assert "none recorded" in body


class TestKindBranchedDrafts:
    """drafts._draft_body dispatches on NegotiationArtifactKind."""

    @pytest.mark.parametrize(
        ("kind", "renderer"),
        [
            (NegotiationArtifactKind.REDLINE, render_redline),
            (NegotiationArtifactKind.SELLER_REQUEST, render_seller_request),
            (NegotiationArtifactKind.CLARIFICATION_QUESTION, render_clarification_questions),
        ],
        ids=["redline", "seller_request", "clarification_question"],
    )
    def test_draft_body_matches_the_kind_template(
        self,
        firestore_client: firestore.Client,
        kind: NegotiationArtifactKind,
        renderer: Callable[[Finding], str],
    ) -> None:
        finding = _finding()
        _seed(firestore_client, finding)
        draft = generate_draft(firestore_client, DEAL, finding_id=finding.finding_id, kind=kind)
        assert draft.body == renderer(finding)
        for entry in finding.evidence:
            assert _quoted(entry.verbatim_span) in draft.body

    def test_confidence_gate_refuses_below_candidate_threshold(
        self, firestore_client: firestore.Client
    ) -> None:
        finding = _finding(confidence=0.74)
        _seed(firestore_client, finding)
        for kind in NegotiationArtifactKind:
            with pytest.raises(DraftRefused, match="candidate threshold"):
                generate_draft(firestore_client, DEAL, finding_id=finding.finding_id, kind=kind)

    def test_generation_stays_idempotent_per_kind(self, firestore_client: firestore.Client) -> None:
        finding = _finding()
        _seed(firestore_client, finding)
        first = generate_draft(
            firestore_client,
            DEAL,
            finding_id=finding.finding_id,
            kind=NegotiationArtifactKind.REDLINE,
        )
        second = generate_draft(
            firestore_client,
            DEAL,
            finding_id=finding.finding_id,
            kind=NegotiationArtifactKind.REDLINE,
        )
        assert first == second
        assert (
            len(NegotiationStore(firestore_client).list_for_finding(DEAL, finding.finding_id)) == 1
        )


class TestFullSpecHappyPath:
    """draft -> submit -> approve -> send via the store, with auditable
    negotiation.transition events ending at send_logged."""

    def test_full_chain_with_event_shape(self, firestore_client: firestore.Client) -> None:
        publisher = InMemoryPublisher()
        finding = _finding()
        _seed(firestore_client, finding)
        draft = generate_draft(
            firestore_client,
            DEAL,
            finding_id=finding.finding_id,
            kind=NegotiationArtifactKind.REDLINE,
            publisher=publisher,
        )
        submit_for_approval(firestore_client, DEAL, draft.draft_id, publisher=publisher)
        approved = approve_draft(
            firestore_client,
            DEAL,
            draft.draft_id,
            approver="deal-lead@deal-falcon",
            publisher=publisher,
        )
        sent = record_send(firestore_client, DEAL, draft.draft_id, publisher=publisher)
        assert sent.state is NegotiationState.SEND_LOGGED
        assert approved.approved_by == "deal-lead@deal-falcon"

        events = [
            EventEnvelope.from_json(raw)
            for raw in publisher.published
            if EventEnvelope.from_json(raw).type is EventType.NEGOTIATION_TRANSITION
        ]
        chain = [(e.payload["from_state"], e.payload["to_state"]) for e in events]
        assert chain == [
            (None, NegotiationState.DRAFT.value),
            (NegotiationState.DRAFT.value, NegotiationState.PENDING_APPROVAL.value),
            (NegotiationState.PENDING_APPROVAL.value, NegotiationState.APPROVED.value),
            (NegotiationState.APPROVED.value, NegotiationState.SEND_LOGGED.value),
        ]
        final = events[-1]
        assert final.payload["to_state"] == "send_logged"
        assert final.payload["draft_id"] == draft.draft_id
        assert final.payload["finding_id"] == finding.finding_id
        assert final.payload["kind"] == NegotiationArtifactKind.REDLINE.value
        assert final.deal_id == DEAL

    def test_machine_still_refuses_invalid_edges(self, firestore_client: firestore.Client) -> None:
        finding = _finding()
        _seed(firestore_client, finding)
        draft = generate_draft(
            firestore_client,
            DEAL,
            finding_id=finding.finding_id,
            kind=NegotiationArtifactKind.SELLER_REQUEST,
        )
        with pytest.raises(InvalidNegotiationTransition):
            approve_draft(firestore_client, DEAL, draft.draft_id, approver="deal-lead@deal-falcon")
        with pytest.raises(InvalidNegotiationTransition):
            record_send(firestore_client, DEAL, draft.draft_id)
        submit_for_approval(firestore_client, DEAL, draft.draft_id)
        approve_draft(firestore_client, DEAL, draft.draft_id, approver="deal-lead@deal-falcon")
        record_send(firestore_client, DEAL, draft.draft_id)
        with pytest.raises(InvalidNegotiationTransition):
            record_send(firestore_client, DEAL, draft.draft_id)
        with pytest.raises(InvalidNegotiationTransition):
            submit_for_approval(firestore_client, DEAL, draft.draft_id)
