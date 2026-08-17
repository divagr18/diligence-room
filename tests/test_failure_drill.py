"""Failure drill (BUILD_PLAN D6-M7, scenario S8).

A malformed document event pushed through the runner must exhaust retries and
land in the DLQ without crashing the consumer and without leaving partial
deal state behind.
"""

from __future__ import annotations

import json

from google.cloud import firestore

from ingestion.parsing import LocalParser, UnsupportedFormatError
from runtime.dlq import FirestoreDeadLetterSink
from runtime.events import EventEnvelope, EventType, new_event
from runtime.runner import DispatchStatus, RunnerConfig, dispatch_event

DEAL = "deal-falcon"
MALFORMED_BYTES = b"\x00\x01\x02not-a-real-document"


class IngestingHandler:
    """Mimics the ingestion pipeline entry: parse then route.

    Raises for malformed content exactly as the real parser does, so the
    runner's retry/DLQ machinery is exercised with a genuine failure.
    """

    def __init__(self) -> None:
        self.calls = 0

    def handle(self, envelope: EventEnvelope) -> None:
        self.calls += 1
        document_id = str(envelope.payload["document_id"])
        LocalParser().parse(MALFORMED_BYTES, document_id, DEAL)


def _malformed_event() -> EventEnvelope:
    return new_event(
        deal_id=DEAL,
        actor="bucket-notification",
        event_type=EventType.DOCUMENT_INGESTED,
        payload={
            "document_id": "corrupted_upload.bin",
            "bucket": "diligence-room-dataroom-deal-falcon-us",
        },
    )


class TestFailureDrill:
    def test_malformed_event_lands_in_dlq_without_crash(
        self, firestore_client: firestore.Client
    ) -> None:
        handler = IngestingHandler()
        config = RunnerConfig(max_attempts=3, backoff_base_s=0.001, backoff_max_s=0.002)
        result = dispatch_event(
            firestore_client,
            _malformed_event(),
            handler,
            config=config,
            sleep=lambda seconds: None,
        )
        assert result.status is DispatchStatus.DEAD_LETTERED
        assert result.attempts == 3
        assert handler.calls == 3
        assert isinstance(result.last_error, str)
        records = FirestoreDeadLetterSink(firestore_client).list_dead_letters(DEAL)
        assert len(records) == 1
        assert records[0].reason == "max_retries_exceeded"
        envelope = json.loads(records[0].envelope_json)
        assert envelope["payload"]["document_id"] == "corrupted_upload.bin"

    def test_failure_leaves_no_partial_deal_state(self, firestore_client: firestore.Client) -> None:
        handler = IngestingHandler()
        config = RunnerConfig(max_attempts=2, backoff_base_s=0.001, backoff_max_s=0.002)
        dispatch_event(
            firestore_client,
            _malformed_event(),
            handler,
            config=config,
            sleep=lambda seconds: None,
        )
        deal_doc = firestore_client.collection("deals").document(DEAL).get()
        if deal_doc.exists:
            data = deal_doc.to_dict() or {}
            assert "documents_ingested" not in data
        docs = firestore_client.collection("deals").document(DEAL).collection("documents").stream()
        assert list(docs) == [], "malformed event must not register lineage"

    def test_only_dead_letter_event_in_audit_log(self, firestore_client: firestore.Client) -> None:
        handler = IngestingHandler()
        config = RunnerConfig(max_attempts=2, backoff_base_s=0.001, backoff_max_s=0.002)
        dispatch_event(
            firestore_client,
            _malformed_event(),
            handler,
            config=config,
            sleep=lambda seconds: None,
        )
        events = [
            event.to_dict()
            for event in firestore_client.collection("deals")
            .document(DEAL)
            .collection("events")
            .stream()
        ]
        types = [event["type"] for event in events if event.get("type")]
        assert types == [EventType.DEAD_LETTERED.value]

    def test_handler_failure_mode_is_the_real_parser_error(
        self, firestore_client: firestore.Client
    ) -> None:
        """The drill must fail for the RIGHT reason: unsupported format."""
        try:
            LocalParser().parse(MALFORMED_BYTES, "corrupted_upload.bin", DEAL)
        except UnsupportedFormatError:
            pass
        else:
            raise AssertionError("malformed bytes unexpectedly parsed")
