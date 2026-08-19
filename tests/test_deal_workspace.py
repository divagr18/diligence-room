"""Project Falcon deal-workspace provisioning tests (BUILD_PLAN D2-M6, S6)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from google.cloud import firestore

from runtime.deal import Deal, DealStatus
from runtime.deal_workspace import (
    FALCON_DEAL_ID,
    DealAlreadyProvisionedError,
    build_falcon_deal,
    provision_deal,
)

NOW = datetime(2026, 8, 15, 9, 0, tzinfo=UTC)


class TestFalconDealConstants:
    def test_falcon_contract(self) -> None:
        deal = build_falcon_deal(NOW)
        assert deal.deal_id == FALCON_DEAL_ID == "deal-falcon"
        assert deal.name == "Project Falcon"
        assert deal.target == "Vantage Robotics"
        assert deal.deal_type == "Acquisition"
        assert deal.regions == ("US", "EU")
        assert deal.expected_window_days == 90
        assert deal.policy_profile_id == "falcon-standard-v1"
        assert deal.status is DealStatus.ACTIVE
        assert deal.created_at == NOW


class TestProvisionDeal:
    def test_provision_writes_fields_per_layout(self, firestore_client: firestore.Client) -> None:
        deal = build_falcon_deal(NOW)
        provision_deal(firestore_client, deal)
        snapshot = firestore_client.collection("deals").document(deal.deal_id).get()
        assert snapshot.exists
        data = snapshot.to_dict()
        assert data is not None
        assert data["deal_id"] == "deal-falcon"
        assert data["name"] == "Project Falcon"
        assert data["target"] == "Vantage Robotics"
        assert data["deal_type"] == "Acquisition"
        assert data["regions"] == ["US", "EU"]
        assert data["expected_window_days"] == 90
        assert data["policy_profile_id"] == "falcon-standard-v1"
        assert data["status"] == "active"
        assert isinstance(data["created_at"], datetime)

    def test_double_provision_raises(self, firestore_client: firestore.Client) -> None:
        deal = build_falcon_deal(NOW)
        provision_deal(firestore_client, deal)
        with pytest.raises(DealAlreadyProvisionedError, match="deal-falcon"):
            provision_deal(firestore_client, deal)

    def test_independent_deals_coexist(self, firestore_client: firestore.Client) -> None:
        provision_deal(firestore_client, build_falcon_deal(NOW))
        other = Deal(
            deal_id="deal-osprey",
            name="Project Osprey",
            target="Beta Manufacturing",
            deal_type="Acquisition",
            regions=("US",),
            expected_window_days=30,
            policy_profile_id="osprey-standard-v1",
            created_at=NOW,
        )
        provision_deal(firestore_client, other)
        deals = list(firestore_client.collection("deals").stream())
        assert sorted(doc.id for doc in deals) == ["deal-falcon", "deal-osprey"]
