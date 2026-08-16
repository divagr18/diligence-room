"""Gateway policy rules (BUILD_PLAN D5-M1, vision §7.5).

Firestore-backed policy objects governing cross-workstream communication:
who may ask whom, for which purposes, in which response shape, and how
often. Posture is deny-default: a missing rule denies (see gateway.decide).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from google.cloud import firestore

from registry.models import Workstream

_POLICY_COLLECTION = "gateway_policy"


class ResponseShape(StrEnum):
    """What a target workstream may return through the gateway."""

    AGGREGATE_ONLY = "aggregate_only"
    NONE = "none"


def policy_rule_id(subject: Workstream, target: Workstream) -> str:
    return f"{subject.value}->{target.value}"


@dataclass(frozen=True, slots=True)
class PolicyRule:
    """One governed communication corridor between two workstreams."""

    rule_id: str
    subject_workstream: Workstream
    target_workstream: Workstream
    purposes: tuple[str, ...]
    response_shape: ResponseShape
    rate_limit: int

    def __post_init__(self) -> None:
        if self.subject_workstream is self.target_workstream:
            raise ValueError("policy rule must not reference self (subject == target)")
        if self.rate_limit < 0:
            raise ValueError(f"rate_limit must be >= 0, got {self.rate_limit}")
        for purpose in self.purposes:
            if not purpose:
                raise ValueError("policy purposes must be non-empty strings")


def _rule_to_doc(rule: PolicyRule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "subject_workstream": rule.subject_workstream.value,
        "target_workstream": rule.target_workstream.value,
        "purposes": list(rule.purposes),
        "response_shape": rule.response_shape.value,
        "rate_limit": rule.rate_limit,
    }


def _rule_from_doc(doc: dict[str, Any]) -> PolicyRule:
    return PolicyRule(
        rule_id=str(doc["rule_id"]),
        subject_workstream=Workstream(doc["subject_workstream"]),
        target_workstream=Workstream(doc["target_workstream"]),
        purposes=tuple(str(purpose) for purpose in doc["purposes"]),
        response_shape=ResponseShape(doc["response_shape"]),
        rate_limit=int(doc["rate_limit"]),
    )


class PolicyStore:
    """CRUD for gateway policy rules at deals/{deal_id}/gateway_policy/{rule_id}."""

    def __init__(self, client: firestore.Client) -> None:
        self._client = client

    def _collection(self, deal_id: str) -> firestore.CollectionReference:
        return cast(
            firestore.CollectionReference,
            self._client.collection("deals").document(deal_id).collection(_POLICY_COLLECTION),
        )

    def upsert(self, deal_id: str, rule: PolicyRule) -> None:
        self._collection(deal_id).document(rule.rule_id).set(_rule_to_doc(rule))

    def get(self, deal_id: str, subject: Workstream, target: Workstream) -> PolicyRule | None:
        snapshot = self._collection(deal_id).document(policy_rule_id(subject, target)).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        assert data is not None
        return _rule_from_doc(data)

    def rules_for_deal(self, deal_id: str) -> list[PolicyRule]:
        rules: list[PolicyRule] = []
        for snapshot in self._collection(deal_id).stream():
            data = snapshot.to_dict()
            if data:
                rules.append(_rule_from_doc(data))
        return rules

    def seed_defaults(self, deal_id: str) -> None:
        """Plant the Day-5 corridor (idempotent): legal may query finance.

        Aggregate-only signals for revenue concentration and change-of-control
        exposure, capped at 10 ALLOWs per rolling hour. All other corridors
        stay deny-default until explicitly granted.
        """
        corridor = PolicyRule(
            rule_id=policy_rule_id(Workstream.LEGAL, Workstream.FINANCE),
            subject_workstream=Workstream.LEGAL,
            target_workstream=Workstream.FINANCE,
            purposes=("revenue_concentration", "change_of_control_exposure"),
            response_shape=ResponseShape.AGGREGATE_ONLY,
            rate_limit=10,
        )
        self.upsert(deal_id, corridor)
