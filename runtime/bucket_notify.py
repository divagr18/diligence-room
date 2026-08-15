"""GCS bucket-notification parsing (Wave-3 gate piece, S8).

Pure functions: validate an ``OBJECT_FINALIZE`` bucket notification, invert
the data-room bucket naming to the deal id, and build the
``document.ingested`` envelope that enters the event bus.
"""

from __future__ import annotations

from collections.abc import Mapping

from runtime.events import EventEnvelope, EventType, new_event

BUCKET_PREFIX = "diligence-room-dataroom-"
REGION_SUFFIXES: tuple[str, ...] = ("-us", "-eu")
_NOTIFICATION_ACTOR = "bucket-notification"


class BucketNotificationError(ValueError):
    """Raised for malformed or unsupported bucket notifications."""


def deal_id_from_bucket(bucket: str) -> str:
    """Invert the data-room bucket naming used by infra.data_room."""
    if not bucket.startswith(BUCKET_PREFIX):
        raise BucketNotificationError(f"bucket {bucket!r} is not a diligence-room data-room bucket")
    remainder = bucket[len(BUCKET_PREFIX) :]
    for suffix in REGION_SUFFIXES:
        if remainder.endswith(suffix):
            deal_id = remainder[: -len(suffix)]
            if deal_id:
                return deal_id
    raise BucketNotificationError(f"cannot derive deal id from bucket {bucket!r}")


def parse_notification(payload: Mapping[str, object]) -> EventEnvelope:
    """Build a document.ingested envelope from an OBJECT_FINALIZE notification."""
    bucket = payload.get("bucket")
    name = payload.get("name")
    event_type = payload.get("eventType")
    if not isinstance(bucket, str) or not bucket:
        raise BucketNotificationError("notification missing 'bucket'")
    if not isinstance(name, str) or not name:
        raise BucketNotificationError("notification missing 'name'")
    if event_type != "OBJECT_FINALIZE":
        raise BucketNotificationError(
            f"unsupported eventType {event_type!r}; only OBJECT_FINALIZE is routed"
        )
    deal_id = deal_id_from_bucket(bucket)
    event_payload: dict[str, object] = {"document_id": name, "bucket": bucket}
    content_type = payload.get("contentType")
    if isinstance(content_type, str) and content_type:
        event_payload["content_type"] = content_type
    return new_event(
        deal_id=deal_id,
        actor=_NOTIFICATION_ACTOR,
        event_type=EventType.DOCUMENT_INGESTED,
        payload=event_payload,
    )
