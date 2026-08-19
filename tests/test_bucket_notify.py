"""Bucket-notification parsing tests (Wave-3 gate piece, S8)."""

from __future__ import annotations

import pytest

from infra.data_room import plan_bucket_pair
from runtime.bucket_notify import (
    BucketNotificationError,
    deal_id_from_bucket,
    parse_notification,
)
from runtime.events import EventType


class TestParseNotification:
    def test_finalize_notification_yields_document_ingested(self) -> None:
        envelope = parse_notification(
            {
                "bucket": "diligence-room-dataroom-deal-falcon-us",
                "name": "contract_meridian_logistics.pdf",
                "eventType": "OBJECT_FINALIZE",
                "contentType": "application/pdf",
            }
        )
        assert envelope.type is EventType.DOCUMENT_INGESTED
        assert envelope.deal_id == "deal-falcon"
        assert envelope.actor == "bucket-notification"
        assert envelope.payload["document_id"] == "contract_meridian_logistics.pdf"
        assert envelope.payload["bucket"] == "diligence-room-dataroom-deal-falcon-us"
        assert envelope.payload["content_type"] == "application/pdf"

    def test_non_finalize_event_rejected(self) -> None:
        with pytest.raises(BucketNotificationError, match="OBJECT_FINALIZE"):
            parse_notification(
                {
                    "bucket": "diligence-room-dataroom-deal-falcon-us",
                    "name": "x.pdf",
                    "eventType": "OBJECT_DELETE",
                }
            )

    def test_missing_name_rejected(self) -> None:
        with pytest.raises(BucketNotificationError, match="name"):
            parse_notification(
                {
                    "bucket": "diligence-room-dataroom-deal-falcon-us",
                    "eventType": "OBJECT_FINALIZE",
                }
            )

    def test_unknown_bucket_rejected(self) -> None:
        with pytest.raises(BucketNotificationError, match="data-room"):
            parse_notification(
                {
                    "bucket": "some-other-bucket",
                    "name": "x.pdf",
                    "eventType": "OBJECT_FINALIZE",
                }
            )


class TestBucketNamingInverse:
    @pytest.mark.parametrize("deal_id", ["deal-falcon", "a", "deal-x1"])
    def test_roundtrip_for_both_regions(self, deal_id: str) -> None:
        us_bucket, eu_bucket = plan_bucket_pair(deal_id)
        assert deal_id_from_bucket(us_bucket) == deal_id
        assert deal_id_from_bucket(eu_bucket) == deal_id

    def test_prefix_without_deal_id_rejected(self) -> None:
        with pytest.raises(BucketNotificationError, match="deal id"):
            deal_id_from_bucket("diligence-room-dataroom--us")
