"""Day-2 live consumer tests (BUILD_PLAN D2-M9).

Emulator-backed: FeedSource + EchoInvoker drive DealEventConsumer against the
Firestore emulator; run() covers once/watch drains; CLI guards refuse
mis-wired live/offline modes. The live PubSubPullSource is never
instantiated in tests — only FeedSource is exercised.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest
from google.cloud import firestore

from gateway.audit import DealEventAuditLog
from infra.data_room import PROJECT_ID
from runtime.consumer import (
    DealEventConsumer,
    EchoInvoker,
    FeedSource,
    ProcessStatus,
    main,
    run,
)
from runtime.deal_workspace import FALCON_DEAL_ID, build_falcon_deal, provision_deal

NOW = datetime(2026, 8, 15, 9, 0, tzinfo=UTC)

FALCON_US_NOTIFICATION: dict[str, object] = {
    "bucket": "diligence-room-dataroom-deal-falcon-us",
    "name": "contract_meridian_logistics.pdf",
    "eventType": "OBJECT_FINALIZE",
    "contentType": "application/pdf",
}


class RecordingInvoker:
    """Test double: behaves like EchoInvoker but records every call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def invoke(self, deal_id: str, message: str) -> str:
        self.calls.append((deal_id, message))
        return message


class DrainCountingSource:
    """Yields one payload per drain call so watch-mode polling is observable."""

    def __init__(self, payload: Mapping[str, object]) -> None:
        self._payload = payload
        self.drains = 0

    def messages(self) -> Iterable[tuple[str, Mapping[str, object]]]:
        self.drains += 1
        yield "counted-1", self._payload


@pytest.fixture()
def falcon_client(firestore_client: firestore.Client) -> firestore.Client:
    provision_deal(firestore_client, build_falcon_deal(NOW))
    return firestore_client


def _make_consumer(
    client: firestore.Client,
    source: FeedSource,
    invoker: RecordingInvoker,
) -> DealEventConsumer:
    return DealEventConsumer(
        client=client,
        source=source,
        invoker=invoker,
        audit=DealEventAuditLog(client),
    )


class TestProcessNotification:
    def test_object_finalize_is_processed_with_audit_and_deal_state(
        self, falcon_client: firestore.Client
    ) -> None:
        invoker = RecordingInvoker()
        consumer = _make_consumer(falcon_client, FeedSource([FALCON_US_NOTIFICATION]), invoker)

        result = consumer.process_notification(FALCON_US_NOTIFICATION)

        assert result.status == ProcessStatus.PROCESSED
        assert result.seq == 1
        assert result.event_id

        records = DealEventAuditLog(falcon_client).events(FALCON_DEAL_ID)
        assert len(records) == 1
        first = records[0]
        assert first.type == "document.ingested"
        assert first.actor == "bucket-notification"
        payload = json.loads(first.payload_json)
        assert payload["document_id"] == "contract_meridian_logistics.pdf"

        deal_data = falcon_client.collection("deals").document(FALCON_DEAL_ID).get().to_dict()
        assert deal_data is not None
        assert deal_data["documents_ingested"] == 1
        assert deal_data["last_document_id"] == "contract_meridian_logistics.pdf"
        last_ingested_at = deal_data["last_ingested_at"]
        assert isinstance(last_ingested_at, datetime)
        assert last_ingested_at.tzinfo is not None

        assert len(invoker.calls) == 1
        deal_id, message = invoker.calls[0]
        assert deal_id == FALCON_DEAL_ID
        assert "contract_meridian_logistics.pdf" in message
        assert FALCON_DEAL_ID in message

    def test_duplicate_payload_is_not_reprocessed(self, falcon_client: firestore.Client) -> None:
        invoker = RecordingInvoker()
        consumer = _make_consumer(falcon_client, FeedSource([FALCON_US_NOTIFICATION]), invoker)

        first = consumer.process_notification(FALCON_US_NOTIFICATION)
        second = consumer.process_notification(FALCON_US_NOTIFICATION)

        assert first.status == ProcessStatus.PROCESSED
        assert second.status == ProcessStatus.DUPLICATE
        assert second.seq == first.seq == 1

        deal_data = falcon_client.collection("deals").document(FALCON_DEAL_ID).get().to_dict()
        assert deal_data is not None
        assert deal_data["documents_ingested"] == 1
        assert len(invoker.calls) == 1
        assert len(DealEventAuditLog(falcon_client).events(FALCON_DEAL_ID)) == 1

    def test_non_object_finalize_is_skipped(self, falcon_client: firestore.Client) -> None:
        invoker = RecordingInvoker()
        consumer = _make_consumer(falcon_client, FeedSource([]), invoker)
        payload = {**FALCON_US_NOTIFICATION, "eventType": "OBJECT_DELETE"}

        result = consumer.process_notification(payload)

        assert result.status == ProcessStatus.SKIPPED
        assert result.seq is None
        assert result.event_id is None
        assert DealEventAuditLog(falcon_client).events(FALCON_DEAL_ID) == []
        assert invoker.calls == []

    def test_missing_name_is_skipped(self, falcon_client: firestore.Client) -> None:
        invoker = RecordingInvoker()
        consumer = _make_consumer(falcon_client, FeedSource([]), invoker)
        payload = {
            "bucket": "diligence-room-dataroom-deal-falcon-us",
            "eventType": "OBJECT_FINALIZE",
        }

        result = consumer.process_notification(payload)

        assert result.status == ProcessStatus.SKIPPED
        assert result.seq is None
        assert DealEventAuditLog(falcon_client).events(FALCON_DEAL_ID) == []
        assert invoker.calls == []

    def test_unknown_bucket_is_skipped(self, falcon_client: firestore.Client) -> None:
        invoker = RecordingInvoker()
        consumer = _make_consumer(falcon_client, FeedSource([]), invoker)
        payload = {
            "bucket": "some-other-bucket",
            "name": "contract_meridian_logistics.pdf",
            "eventType": "OBJECT_FINALIZE",
        }

        result = consumer.process_notification(payload)

        assert result.status == ProcessStatus.SKIPPED
        assert result.seq is None
        assert DealEventAuditLog(falcon_client).events(FALCON_DEAL_ID) == []
        assert invoker.calls == []


class TestRun:
    def test_once_drains_feed_and_prints_summary(
        self, falcon_client: firestore.Client, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payloads: list[Mapping[str, object]] = [
            dict(FALCON_US_NOTIFICATION),
            dict(FALCON_US_NOTIFICATION),
            {"bucket": "unrelated-bucket"},
        ]
        source = FeedSource(payloads)
        consumer = _make_consumer(falcon_client, source, RecordingInvoker())

        processed = run(source, consumer, timeout_seconds=None)

        assert processed == 1
        out = capsys.readouterr().out
        assert "processed=1 duplicates=1 skipped=1" in out

    def test_watch_polls_until_deadline(self, falcon_client: firestore.Client) -> None:
        source = DrainCountingSource(FALCON_US_NOTIFICATION)
        consumer = DealEventConsumer(
            client=falcon_client,
            source=source,
            invoker=EchoInvoker(),
            audit=DealEventAuditLog(falcon_client),
        )

        processed = run(source, consumer, timeout_seconds=2.0)

        assert processed == 1
        assert source.drains >= 2


class TestMainGuards:
    def test_live_mode_refuses_when_emulator_env_is_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:9999")
        with pytest.raises(SystemExit, match="confirm"):
            main(["--confirm-live"])

    def test_offline_mode_refuses_without_emulator_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
        feed = tmp_path / "feed.json"
        feed.write_text("[]", encoding="utf-8")
        with pytest.raises(SystemExit, match="emulator"):
            main(["--feed-file", str(feed)])


class TestMainOfflineFeed:
    def test_feed_file_runs_against_emulator(
        self, firestore_emulator: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        del firestore_emulator  # fixture side effect: FIRESTORE_EMULATOR_HOST is set
        client = firestore.Client(project=PROJECT_ID)
        provision_deal(client, build_falcon_deal(NOW))
        feed = tmp_path / "feed.json"
        feed.write_text(json.dumps([FALCON_US_NOTIFICATION]), encoding="utf-8")

        exit_code = main(["--feed-file", str(feed)])

        assert exit_code == 0
        assert "processed=1 duplicates=0 skipped=0" in capsys.readouterr().out
