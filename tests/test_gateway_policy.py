"""Gateway policy model tests (BUILD_PLAN D5-M1, vision §7.5)."""

from __future__ import annotations

import pytest
from google.cloud import firestore

from gateway.policy import (
    PolicyRule,
    PolicyStore,
    ResponseShape,
    policy_rule_id,
)
from registry.models import Workstream


def _rule(
    subject: Workstream = Workstream.LEGAL,
    target: Workstream = Workstream.FINANCE,
    purposes: tuple[str, ...] = ("revenue_concentration",),
    response_shape: ResponseShape = ResponseShape.AGGREGATE_ONLY,
    rate_limit: int = 10,
) -> PolicyRule:
    return PolicyRule(
        rule_id=policy_rule_id(subject, target),
        subject_workstream=subject,
        target_workstream=target,
        purposes=purposes,
        response_shape=response_shape,
        rate_limit=rate_limit,
    )


class TestPolicyRule:
    def test_rejects_self_reference(self) -> None:
        with pytest.raises(ValueError, match="self"):
            _rule(subject=Workstream.LEGAL, target=Workstream.LEGAL)

    def test_rejects_negative_rate_limit(self) -> None:
        with pytest.raises(ValueError, match="rate_limit"):
            _rule(rate_limit=-1)

    def test_rejects_empty_purpose_strings(self) -> None:
        with pytest.raises(ValueError, match="purpose"):
            _rule(purposes=("revenue_concentration", ""))

    def test_rule_id_derivation(self) -> None:
        assert policy_rule_id(Workstream.LEGAL, Workstream.FINANCE) == "legal->finance"


class TestPolicyStore:
    def test_upsert_and_get_roundtrip(self, firestore_client: firestore.Client) -> None:
        store = PolicyStore(firestore_client)
        rule = _rule()
        store.upsert("deal-falcon", rule)
        fetched = store.get("deal-falcon", Workstream.LEGAL, Workstream.FINANCE)
        assert fetched == rule

    def test_get_missing_returns_none(self, firestore_client: firestore.Client) -> None:
        store = PolicyStore(firestore_client)
        assert store.get("deal-falcon", Workstream.HR, Workstream.TAX) is None

    def test_upsert_overwrites_existing(self, firestore_client: firestore.Client) -> None:
        store = PolicyStore(firestore_client)
        store.upsert("deal-falcon", _rule(rate_limit=10))
        store.upsert("deal-falcon", _rule(rate_limit=3))
        fetched = store.get("deal-falcon", Workstream.LEGAL, Workstream.FINANCE)
        assert fetched is not None
        assert fetched.rate_limit == 3

    def test_rules_for_deal_lists_all(self, firestore_client: firestore.Client) -> None:
        store = PolicyStore(firestore_client)
        store.upsert("deal-falcon", _rule())
        store.upsert(
            "deal-falcon",
            _rule(subject=Workstream.FINANCE, target=Workstream.LEGAL),
        )
        rules = store.rules_for_deal("deal-falcon")
        assert {rule.rule_id for rule in rules} == {"legal->finance", "finance->legal"}

    def test_deal_isolation(self, firestore_client: firestore.Client) -> None:
        store = PolicyStore(firestore_client)
        store.upsert("deal-falcon", _rule())
        assert store.get("deal-osprey", Workstream.LEGAL, Workstream.FINANCE) is None


class TestSeedDefaults:
    def test_plants_legal_to_finance_rule(self, firestore_client: firestore.Client) -> None:
        store = PolicyStore(firestore_client)
        store.seed_defaults("deal-falcon")
        rule = store.get("deal-falcon", Workstream.LEGAL, Workstream.FINANCE)
        assert rule is not None
        assert rule.response_shape is ResponseShape.AGGREGATE_ONLY
        assert rule.purposes == ("revenue_concentration", "change_of_control_exposure")
        assert rule.rate_limit == 10

    def test_seed_is_idempotent(self, firestore_client: firestore.Client) -> None:
        store = PolicyStore(firestore_client)
        store.seed_defaults("deal-falcon")
        store.seed_defaults("deal-falcon")
        assert len(store.rules_for_deal("deal-falcon")) == 1

    def test_deny_default_posture(self, firestore_client: firestore.Client) -> None:
        store = PolicyStore(firestore_client)
        store.seed_defaults("deal-falcon")
        assert store.get("deal-falcon", Workstream.LEGAL, Workstream.HR) is None
        assert store.get("deal-falcon", Workstream.HR, Workstream.FINANCE) is None
