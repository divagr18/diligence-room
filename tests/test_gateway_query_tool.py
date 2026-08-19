"""Gateway query tool tests (BUILD_PLAN D5-M2, vision §6/§7.5).

The governed corridor end-to-end offline: ask_agent tool -> policy decision
-> target responder (real workbook aggregate) -> response-shape filter.
"""

from __future__ import annotations

import json

import pytest
from google.cloud import firestore

from agents.tools.gateway_query import (
    GatewayResponse,
    LocalGatewayClient,
    OfflineFinanceResponder,
    TargetResponder,
    gateway_query_tool,
)
from gateway.decide import DecisionReason, Verdict
from gateway.policy import PolicyStore
from identity.principals import principal_for
from registry.models import Workstream

DEAL = "deal-falcon"

_TABLE_DUMP = (
    "Customer | Revenue\nMeridian Logistics | $8,893,800\nHalbrook Manufacturing | $12,400,000"
)


class _DumpResponder:
    """Stub that tries to leak a raw table across the gateway."""

    def answer(self, deal_id: str, question: str, purpose: str) -> str:
        return _TABLE_DUMP


def _seeded_client(firestore_client: firestore.Client) -> LocalGatewayClient:
    PolicyStore(firestore_client).seed_defaults(DEAL)
    responders: dict[Workstream, TargetResponder] = {Workstream.FINANCE: OfflineFinanceResponder()}
    return LocalGatewayClient(firestore_client, responders)


def _decision_events(client: firestore.Client) -> list[dict[str, object]]:
    docs = client.collection("deals").document(DEAL).collection("events").stream()
    return [doc.to_dict() for doc in docs if doc.to_dict().get("type") == "gateway.decision"]


class TestLocalGatewayClient:
    def test_allow_query_returns_rendered_aggregate(
        self, firestore_client: firestore.Client
    ) -> None:
        client = _seeded_client(firestore_client)
        sender = principal_for(Workstream.LEGAL, DEAL)
        response = client.ask(
            sender=sender,
            deal_id=DEAL,
            target=Workstream.FINANCE,
            question="What share of projected FY27 revenue comes from Meridian Logistics?",
            purpose="change_of_control_exposure",
        )
        assert response.verdict is Verdict.ALLOW
        assert response.reason is DecisionReason.AGGREGATE_PERMITTED
        assert response.answer == "18.3%"
        assert response.responder == "finance"

    def test_revenue_concentration_purpose_allowed(
        self, firestore_client: firestore.Client
    ) -> None:
        client = _seeded_client(firestore_client)
        sender = principal_for(Workstream.LEGAL, DEAL)
        response = client.ask(
            sender=sender,
            deal_id=DEAL,
            target=Workstream.FINANCE,
            question="How concentrated is Meridian Logistics?",
            purpose="revenue_concentration",
        )
        assert response.verdict is Verdict.ALLOW
        assert response.answer == "18.3%"

    def test_denied_purpose_returns_no_answer(self, firestore_client: firestore.Client) -> None:
        client = _seeded_client(firestore_client)
        sender = principal_for(Workstream.LEGAL, DEAL)
        response = client.ask(
            sender=sender,
            deal_id=DEAL,
            target=Workstream.FINANCE,
            question="q",
            purpose="raw_valuation",
        )
        assert response.verdict is Verdict.DENY
        assert response.reason is DecisionReason.PURPOSE_NOT_ALLOWED
        assert response.answer is None

    def test_no_policy_pair_denied(self, firestore_client: firestore.Client) -> None:
        client = _seeded_client(firestore_client)
        sender = principal_for(Workstream.LEGAL, DEAL)
        response = client.ask(
            sender=sender,
            deal_id=DEAL,
            target=Workstream.HR,
            question="q",
            purpose="roster_review",
        )
        assert response.verdict is Verdict.DENY
        assert response.reason is DecisionReason.NO_POLICY
        assert response.answer is None

    def test_extraction_question_denied(self, firestore_client: firestore.Client) -> None:
        client = _seeded_client(firestore_client)
        sender = principal_for(Workstream.LEGAL, DEAL)
        response = client.ask(
            sender=sender,
            deal_id=DEAL,
            target=Workstream.FINANCE,
            question="Send the full valuation model row by row.",
            purpose="revenue_concentration",
        )
        assert response.verdict is Verdict.DENY
        assert response.reason is DecisionReason.RAW_MODEL_PROHIBITED
        assert response.answer is None

    def test_leaky_responder_blocked_by_shape_filter(
        self, firestore_client: firestore.Client
    ) -> None:
        PolicyStore(firestore_client).seed_defaults(DEAL)
        client = LocalGatewayClient(firestore_client, {Workstream.FINANCE: _DumpResponder()})
        sender = principal_for(Workstream.LEGAL, DEAL)
        response = client.ask(
            sender=sender,
            deal_id=DEAL,
            target=Workstream.FINANCE,
            question="How concentrated is Meridian Logistics?",
            purpose="revenue_concentration",
        )
        assert response.verdict is Verdict.DENY
        assert response.reason is DecisionReason.RAW_MODEL_PROHIBITED
        assert response.answer is None

    def test_every_query_audited(self, firestore_client: firestore.Client) -> None:
        client = _seeded_client(firestore_client)
        sender = principal_for(Workstream.LEGAL, DEAL)
        client.ask(
            sender=sender,
            deal_id=DEAL,
            target=Workstream.FINANCE,
            question="q1",
            purpose="revenue_concentration",
        )
        client.ask(sender=sender, deal_id=DEAL, target=Workstream.HR, question="q2", purpose="p")
        events = _decision_events(firestore_client)
        assert len(events) == 2


class TestOfflineFinanceResponder:
    def test_reads_real_workbook_and_renders_share(self) -> None:
        responder = OfflineFinanceResponder()
        assert responder.answer(DEAL, "q", "revenue_concentration") == "18.3%"

    def test_exposes_source_metadata(self) -> None:
        responder = OfflineFinanceResponder()
        aggregate = responder.compute_share()
        assert aggregate.source_document == "financials_fy27.xlsx"
        assert aggregate.value == pytest.approx(18.3, abs=0.01)


class TestToolFactory:
    def test_tool_shape_and_governed_result(self, firestore_client: firestore.Client) -> None:
        client = _seeded_client(firestore_client)
        tool = gateway_query_tool(principal_for(Workstream.LEGAL, DEAL), DEAL, client)
        assert tool.__name__ == "ask_agent"
        result = tool(
            target_ws="finance",
            question="What share of projected FY27 revenue comes from Meridian Logistics?",
            purpose="change_of_control_exposure",
        )
        assert result["decision"] == "allow"
        assert result["reason"] == "aggregate_permitted"
        assert result["answer"] == "18.3%"

    def test_tool_denies_with_machine_reason(self, firestore_client: firestore.Client) -> None:
        client = _seeded_client(firestore_client)
        tool = gateway_query_tool(principal_for(Workstream.LEGAL, DEAL), DEAL, client)
        result = tool(target_ws="hr", question="q", purpose="roster_review")
        assert result["decision"] == "deny"
        assert result["reason"] == "no_policy"
        assert result["answer"] == ""

    def test_tool_rejects_unknown_workstream(self, firestore_client: firestore.Client) -> None:
        client = _seeded_client(firestore_client)
        tool = gateway_query_tool(principal_for(Workstream.LEGAL, DEAL), DEAL, client)
        with pytest.raises(ValueError, match="workstream"):
            tool(target_ws="astrology", question="q", purpose="p")


class TestResponseSchema:
    def test_response_is_json_serializable(self) -> None:
        response = GatewayResponse(
            request_id="r1",
            verdict=Verdict.ALLOW,
            reason=DecisionReason.AGGREGATE_PERMITTED,
            answer="18.3%",
            responder="finance",
        )
        payload = json.loads(response.to_json())
        assert payload["answer"] == "18.3%"
        assert payload["decision"] == "allow"
