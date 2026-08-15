"""Memory partition key and Firestore path tests (BUILD_PLAN D3-M3, vision §7.3)."""

from __future__ import annotations

import pytest
from google.cloud import firestore

from memory.partitions import (
    ORG,
    get_partition,
    partition_collection,
    partition_key,
)
from registry.models import Workstream


class TestPartitionKeyFormat:
    def test_org_deal_workstream_triple(self) -> None:
        assert partition_key("deal-falcon", Workstream.LEGAL) == f"{ORG}/deal-falcon/legal"

    def test_string_workstream_accepted(self) -> None:
        assert partition_key("deal-falcon", "finance") == f"{ORG}/deal-falcon/finance"

    def test_custom_org_override(self) -> None:
        assert partition_key("deal-falcon", Workstream.LEGAL, org="acme-corp") == (
            "acme-corp/deal-falcon/legal"
        )

    def test_default_org_value(self) -> None:
        assert ORG == "diligence-room"


class TestPartitionKeyValidation:
    def test_rejects_uppercase_deal_id(self) -> None:
        with pytest.raises(ValueError, match="invalid deal_id"):
            partition_key("Deal-Falcon", Workstream.LEGAL)

    def test_rejects_deal_id_starting_with_digit(self) -> None:
        with pytest.raises(ValueError, match="invalid deal_id"):
            partition_key("1deal", Workstream.LEGAL)

    def test_rejects_empty_deal_id(self) -> None:
        with pytest.raises(ValueError, match="invalid deal_id"):
            partition_key("", Workstream.LEGAL)

    def test_rejects_deal_id_with_underscore(self) -> None:
        with pytest.raises(ValueError, match="invalid deal_id"):
            partition_key("deal_falcon", Workstream.LEGAL)

    def test_rejects_unknown_workstream_string(self) -> None:
        with pytest.raises(ValueError, match="invalid workstream"):
            partition_key("deal-falcon", "bogus-workstream")


class TestGetPartition:
    def test_returns_deals_workstreams_path(self) -> None:
        assert get_partition("deal-falcon", Workstream.LEGAL) == (
            "deals/deal-falcon/workstreams/legal"
        )

    def test_string_workstream_resolves_to_value(self) -> None:
        assert get_partition("deal-falcon", "ip_tech") == ("deals/deal-falcon/workstreams/ip_tech")

    def test_validates_deal_id(self) -> None:
        with pytest.raises(ValueError, match="invalid deal_id"):
            get_partition("INVALID", Workstream.LEGAL)

    def test_validates_workstream(self) -> None:
        with pytest.raises(ValueError, match="invalid workstream"):
            get_partition("deal-falcon", "nonexistent")


class TestPartitionCollectionRoundTrip:
    def test_write_and_read_via_partition_collection(
        self, firestore_client: firestore.Client
    ) -> None:
        col = partition_collection(firestore_client, "deal-falcon", Workstream.LEGAL)
        col.document("finding-1").set({"title": "IP indemnity gap"})
        snapshot = col.document("finding-1").get()
        assert snapshot.exists
        assert snapshot.to_dict() == {"title": "IP indemnity gap"}


class TestDistinctPartitionsDisjoint:
    def test_workstream_partitions_isolated(self, firestore_client: firestore.Client) -> None:
        legal_col = partition_collection(firestore_client, "deal-falcon", Workstream.LEGAL)
        finance_col = partition_collection(firestore_client, "deal-falcon", Workstream.FINANCE)
        legal_col.document("doc-1").set({"kind": "legal"})
        assert list(finance_col.stream()) == []

    def test_deal_partitions_isolated(self, firestore_client: firestore.Client) -> None:
        deal_a = partition_collection(firestore_client, "deal-alpha", Workstream.LEGAL)
        deal_b = partition_collection(firestore_client, "deal-beta", Workstream.LEGAL)
        deal_a.document("doc-1").set({"kind": "alpha"})
        assert list(deal_b.stream()) == []
