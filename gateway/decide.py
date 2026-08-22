"""Gateway decision engine (BUILD_PLAN D5-M3, vision §7.5).

Evaluates a cross-workstream request against the deal's policy rules and
records EVERY verdict (ALLOW or DENY) as a gateway.decision event with a
machine-readable reason. Evaluation order is locked: cross-deal -> rule
lookup (deny-default) -> purpose allow-list -> response shape -> rolling-hour
rate limit -> ALLOW.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, cast

from google.cloud import firestore
from opentelemetry.trace import Tracer

from gateway.policy import PolicyRule, PolicyStore, ResponseShape
from identity.principals import Principal
from memory.event_log import EventLog
from observability.tracing import stage_span
from registry.models import Workstream
from runtime.events import EventType, new_event

_RATE_COLLECTION = "gateway_rate"


class Verdict(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class DecisionReason(StrEnum):
    """Machine-readable verdict vocabulary (audit + dashboard Security view)."""

    AGGREGATE_PERMITTED = "aggregate_permitted"
    PURPOSE_NOT_ALLOWED = "purpose_not_allowed"
    NO_POLICY = "no_policy"
    RATE_LIMITED = "rate_limited"
    CROSS_DEAL = "cross_deal"
    RAW_MODEL_PROHIBITED = "raw_model_prohibited"


@dataclass(frozen=True, slots=True)
class GatewayRequest:
    """One cross-workstream question submitted through the gateway."""

    request_id: str
    deal_id: str
    sender: Principal
    target_workstream: Workstream
    question: str
    purpose: str
    ts: datetime

    def __post_init__(self) -> None:
        if self.ts.tzinfo is None:
            raise ValueError("ts must be timezone-aware (UTC)")


@dataclass(frozen=True, slots=True)
class Decision:
    verdict: Verdict
    reason: DecisionReason
    rule_id: str | None
    request_id: str


def _audit(client: firestore.Client, request: GatewayRequest, decision: Decision) -> None:
    event = new_event(
        deal_id=request.deal_id,
        actor=request.sender.name,
        event_type=EventType.GATEWAY_DECISION,
        payload={
            "decision": decision.verdict.value,
            "reason": decision.reason.value,
            "subject": request.sender.name,
            "target": request.target_workstream.value,
            "purpose": request.purpose,
            "request_id": request.request_id,
        },
        now=request.ts,
    )
    EventLog(client).append(event)


def _window_start(now: datetime) -> datetime:
    return now.replace(minute=0, second=0, microsecond=0)


def _consume_rate_budget(
    client: firestore.Client, deal_id: str, rule: PolicyRule, now: datetime
) -> bool:
    """Atomically consume one ALLOW slot in the rule's rolling-hour window."""
    if rule.rate_limit == 0:
        return True
    counter_ref = cast(
        Any,
        client.collection("deals")
        .document(deal_id)
        .collection(_RATE_COLLECTION)
        .document(rule.rule_id),
    )
    window = _window_start(now).isoformat()

    @firestore.transactional
    def _txn(txn: Any) -> bool:
        snapshot = counter_ref.get(transaction=txn)
        data = snapshot.to_dict() or {}
        current = int(data.get("count", 0)) if data.get("window_start") == window else 0
        if current >= rule.rate_limit:
            return False
        txn.set(counter_ref, {"window_start": window, "count": current + 1})
        return True

    return bool(_txn(client.transaction()))


def decide(
    client: firestore.Client,
    request: GatewayRequest,
    now: datetime | None = None,
    tracer: Tracer | None = None,
) -> Decision:
    """Evaluate *request*; always audits; returns the reasoned verdict."""
    with stage_span(tracer, "gateway.decide") as span:
        decision = _evaluate(client, request, now)
        if span is not None:
            span.set_attribute("gateway.verdict", decision.verdict.value)
            span.set_attribute("gateway.reason", decision.reason.value)
        return decision


def _evaluate(
    client: firestore.Client, request: GatewayRequest, now: datetime | None = None
) -> Decision:
    stamp = now if now is not None else request.ts

    def _finish(verdict: Verdict, reason: DecisionReason, rule_id: str | None) -> Decision:
        decision = Decision(
            verdict=verdict, reason=reason, rule_id=rule_id, request_id=request.request_id
        )
        _audit(client, request, decision)
        return decision

    if request.sender.deal_id != request.deal_id:
        return _finish(Verdict.DENY, DecisionReason.CROSS_DEAL, None)

    rule = PolicyStore(client).get(
        request.deal_id, request.sender.workstream, request.target_workstream
    )
    if rule is None:
        return _finish(Verdict.DENY, DecisionReason.NO_POLICY, None)
    if request.purpose not in rule.purposes:
        return _finish(Verdict.DENY, DecisionReason.PURPOSE_NOT_ALLOWED, rule.rule_id)
    if rule.response_shape is ResponseShape.NONE:
        return _finish(Verdict.DENY, DecisionReason.RAW_MODEL_PROHIBITED, rule.rule_id)
    if not _consume_rate_budget(client, request.deal_id, rule, stamp):
        return _finish(Verdict.DENY, DecisionReason.RATE_LIMITED, rule.rule_id)
    return _finish(Verdict.ALLOW, DecisionReason.AGGREGATE_PERMITTED, rule.rule_id)


def decisions_for_deal(client: firestore.Client, deal_id: str) -> list[dict[str, Any]]:
    """Debug listing of gateway decisions (seeds the dashboard Security view)."""
    docs = client.collection("deals").document(deal_id).collection("events").stream()
    listing: list[dict[str, Any]] = []
    for snapshot in docs:
        data = snapshot.to_dict()
        if data and data.get("type") == EventType.GATEWAY_DECISION.value:
            listing.append(data)
    listing.sort(key=lambda item: int(item.get("seq", 0)))
    return listing
