"""Gateway decision engine tests (BUILD_PLAN D5-M3, vision §7.5).

Phase exit: decide() returns reasoned verdicts for six scripted requests
(3 ALLOW / 3 DENY), plus rate-limit window semantics and audit coverage.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from google.cloud import firestore

from gateway.decide import (
    Decision,
    DecisionReason,
    GatewayRequest,
    Verdict,
    decide,
)
from gateway.policy import PolicyRule, PolicyStore, ResponseShape, policy_rule_id
from identity.principals import principal_for
from registry.models import Workstream

T0 = datetime(2026, 8, 17, 10, 30, tzinfo=UTC)
T1 = datetime(2026, 8, 17, 10, 50, tzinfo=UTC)
T2 = datetime(2026, 8, 17, 11, 5, tzinfo=UTC)

DEAL = "deal-falcon"


def _seed(client: firestore.Client, deal: str = DEAL) -> None:
    PolicyStore(client).seed_defaults(deal)


def _request(
    purpose: str = "revenue_concentration",
    deal: str = DEAL,
    sender_deal: str | None = None,
    target: Workstream = Workstream.FINANCE,
    request_id: str = "req-1",
) -> GatewayRequest:
    sender = principal_for(Workstream.LEGAL, sender_deal or deal)
    return GatewayRequest(
        request_id=request_id,
        deal_id=deal,
        sender=sender,
        target_workstream=target,
        question="What share of projected revenue comes from Meridian Logistics?",
        purpose=purpose,
        ts=T0,
    )


def _decisions(client: firestore.Client, deal: str = DEAL) -> list[dict[str, Any]]:
    docs = client.collection("deals").document(deal).collection("events").stream()
    listing: list[dict[str, Any]] = []
    for doc in docs:
        event = doc.to_dict()
        if event and event.get("type") == "gateway.decision":
            parsed = dict(event)
            parsed["payload"] = json.loads(str(event["payload_json"]))
            listing.append(parsed)
    return listing


class TestScriptedVerdicts:
    """The six-vocabulary phase exit: 3 ALLOW / 3 DENY."""

    def test_allow_revenue_concentration(self, firestore_client: firestore.Client) -> None:
        _seed(firestore_client)
        decision = decide(firestore_client, _request("revenue_concentration"))
        assert decision.verdict is Verdict.ALLOW
        assert decision.reason is DecisionReason.AGGREGATE_PERMITTED
        assert decision.rule_id == "legal->finance"

    def test_allow_change_of_control_exposure(self, firestore_client: firestore.Client) -> None:
        _seed(firestore_client)
        decision = decide(firestore_client, _request("change_of_control_exposure"))
        assert decision.verdict is Verdict.ALLOW
        assert decision.reason is DecisionReason.AGGREGATE_PERMITTED

    def test_allow_repeat_within_window(self, firestore_client: firestore.Client) -> None:
        _seed(firestore_client)
        for index in range(3):
            decision = decide(
                firestore_client, _request("revenue_concentration", request_id=f"req-{index}")
            )
            assert decision.verdict is Verdict.ALLOW

    def test_deny_no_policy(self, firestore_client: firestore.Client) -> None:
        _seed(firestore_client)
        decision = decide(firestore_client, _request(target=Workstream.HR))
        assert decision.verdict is Verdict.DENY
        assert decision.reason is DecisionReason.NO_POLICY
        assert decision.rule_id is None

    def test_deny_purpose_not_allowed(self, firestore_client: firestore.Client) -> None:
        _seed(firestore_client)
        decision = decide(firestore_client, _request("raw_valuation"))
        assert decision.verdict is Verdict.DENY
        assert decision.reason is DecisionReason.PURPOSE_NOT_ALLOWED

    def test_deny_rate_limited(self, firestore_client: firestore.Client) -> None:
        store = PolicyStore(firestore_client)
        store.upsert(
            "deal-rate",
            PolicyRule(
                rule_id=policy_rule_id(Workstream.LEGAL, Workstream.FINANCE),
                subject_workstream=Workstream.LEGAL,
                target_workstream=Workstream.FINANCE,
                purposes=("revenue_concentration",),
                response_shape=ResponseShape.AGGREGATE_ONLY,
                rate_limit=2,
            ),
        )
        first = decide(firestore_client, _request(deal="deal-rate", request_id="a"))
        second = decide(firestore_client, _request(deal="deal-rate", request_id="b"))
        third = decide(firestore_client, _request(deal="deal-rate", request_id="c"))
        assert first.verdict is Verdict.ALLOW
        assert second.verdict is Verdict.ALLOW
        assert third.verdict is Verdict.DENY
        assert third.reason is DecisionReason.RATE_LIMITED


class TestRateWindow:
    def test_window_resets_on_the_hour(self, firestore_client: firestore.Client) -> None:
        store = PolicyStore(firestore_client)
        store.upsert(
            "deal-window",
            PolicyRule(
                rule_id=policy_rule_id(Workstream.LEGAL, Workstream.FINANCE),
                subject_workstream=Workstream.LEGAL,
                target_workstream=Workstream.FINANCE,
                purposes=("revenue_concentration",),
                response_shape=ResponseShape.AGGREGATE_ONLY,
                rate_limit=1,
            ),
        )

        def at(ts: datetime, request_id: str) -> Decision:
            sender = principal_for(Workstream.LEGAL, "deal-window")
            request = GatewayRequest(
                request_id=request_id,
                deal_id="deal-window",
                sender=sender,
                target_workstream=Workstream.FINANCE,
                question="q",
                purpose="revenue_concentration",
                ts=ts,
            )
            return decide(firestore_client, request, now=ts)

        assert at(T0, "w1").verdict is Verdict.ALLOW
        assert at(T1, "w2").verdict is Verdict.DENY
        assert at(T2, "w3").verdict is Verdict.ALLOW


class TestBoundaryCases:
    def test_deny_cross_deal(self, firestore_client: firestore.Client) -> None:
        _seed(firestore_client)
        decision = decide(firestore_client, _request(sender_deal="deal-osprey"))
        assert decision.verdict is Verdict.DENY
        assert decision.reason is DecisionReason.CROSS_DEAL

    def test_deny_none_shape_rule(self, firestore_client: firestore.Client) -> None:
        store = PolicyStore(firestore_client)
        store.upsert(
            DEAL,
            PolicyRule(
                rule_id=policy_rule_id(Workstream.FINANCE, Workstream.LEGAL),
                subject_workstream=Workstream.FINANCE,
                target_workstream=Workstream.LEGAL,
                purposes=("contract_clarification",),
                response_shape=ResponseShape.NONE,
                rate_limit=0,
            ),
        )
        sender = principal_for(Workstream.FINANCE, DEAL)
        request = GatewayRequest(
            request_id="none-shape",
            deal_id=DEAL,
            sender=sender,
            target_workstream=Workstream.LEGAL,
            question="q",
            purpose="contract_clarification",
            ts=T0,
        )
        decision = decide(firestore_client, request)
        assert decision.verdict is Verdict.DENY
        assert decision.reason is DecisionReason.RAW_MODEL_PROHIBITED

    def test_request_rejects_naive_timestamp(self) -> None:
        with pytest.raises(ValueError, match="timezone"):
            GatewayRequest(
                request_id="r",
                deal_id=DEAL,
                sender=principal_for(Workstream.LEGAL, DEAL),
                target_workstream=Workstream.FINANCE,
                question="q",
                purpose="revenue_concentration",
                ts=datetime(2026, 8, 17, 10, 30),
            )

    def test_unlimited_rate_when_zero(self, firestore_client: firestore.Client) -> None:
        store = PolicyStore(firestore_client)
        store.upsert(
            DEAL,
            PolicyRule(
                rule_id=policy_rule_id(Workstream.TAX, Workstream.FINANCE),
                subject_workstream=Workstream.TAX,
                target_workstream=Workstream.FINANCE,
                purposes=("revenue_concentration",),
                response_shape=ResponseShape.AGGREGATE_ONLY,
                rate_limit=0,
            ),
        )
        sender = principal_for(Workstream.TAX, DEAL)
        for index in range(12):
            request = GatewayRequest(
                request_id=f"u-{index}",
                deal_id=DEAL,
                sender=sender,
                target_workstream=Workstream.FINANCE,
                question="q",
                purpose="revenue_concentration",
                ts=T0,
            )
            assert decide(firestore_client, request).verdict is Verdict.ALLOW


class TestAuditTrail:
    def test_every_decision_audited_with_payload_contract(
        self, firestore_client: firestore.Client
    ) -> None:
        _seed(firestore_client)
        decide(firestore_client, _request("revenue_concentration", request_id="ok-1"))
        decide(firestore_client, _request("raw_valuation", request_id="bad-1"))
        decide(firestore_client, _request(target=Workstream.HR, request_id="bad-2"))
        events = _decisions(firestore_client)
        assert len(events) == 3
        payloads = [event["payload"] for event in events]
        allow = next(p for p in payloads if p["decision"] == "allow")
        assert set(allow) == {
            "decision",
            "reason",
            "subject",
            "target",
            "purpose",
            "request_id",
        }
        assert allow["reason"] == "aggregate_permitted"
        assert allow["subject"] == "legal-agent@deal-falcon"
        assert allow["target"] == "finance"
        assert allow["purpose"] == "revenue_concentration"
        assert allow["request_id"] == "ok-1"
        reasons = sorted(str(p["reason"]) for p in payloads if p["decision"] == "deny")
        assert reasons == ["no_policy", "purpose_not_allowed"]

    def test_audit_actor_is_sender_identity(self, firestore_client: firestore.Client) -> None:
        _seed(firestore_client)
        decide(firestore_client, _request("revenue_concentration"))
        events = _decisions(firestore_client)
        assert events[0]["actor"] == "legal-agent@deal-falcon"
