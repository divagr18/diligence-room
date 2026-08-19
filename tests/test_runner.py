"""Retry/idempotency runner tests (BUILD_PLAN D6-M2, scenarios S1/S2/S3)."""

from __future__ import annotations

from datetime import UTC, datetime

from google.cloud import firestore

from runtime.dlq import FirestoreDeadLetterSink
from runtime.events import EventEnvelope, EventType, new_event
from runtime.runner import DispatchStatus, RunnerConfig, dispatch_event

DEAL = "deal-falcon"
T0 = datetime(2026, 8, 19, 10, 0, tzinfo=UTC)


class RecordingHandler:
    """Fails a configured number of times, then succeeds; counts every call."""

    def __init__(self, fail_times: int = 0, always_fail: bool = False) -> None:
        self.fail_times = fail_times
        self.always_fail = always_fail
        self.calls = 0
        self.seen: list[EventEnvelope] = []

    def handle(self, envelope: EventEnvelope) -> None:
        self.calls += 1
        self.seen.append(envelope)
        if self.always_fail:
            raise ValueError("handler crashed")
        if self.calls <= self.fail_times:
            raise ValueError(f"transient failure #{self.calls}")


class FakeSleep:
    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def _envelope(document_id: str) -> EventEnvelope:
    return new_event(
        deal_id=DEAL,
        actor="ingestion-pipeline",
        event_type=EventType.DOCUMENT_INGESTED,
        payload={"document_id": document_id, "bucket": "diligence-room-dataroom-deal-falcon-us"},
    )


def _runner_state(client: firestore.Client, envelope: EventEnvelope) -> dict[str, object] | None:
    doc = (
        client.collection("deals")
        .document(DEAL)
        .collection("runner_state")
        .document(envelope.dedupe_key)
        .get()
    )
    return doc.to_dict() if doc.exists else None


class TestDispatch:
    def test_success_first_try(self, firestore_client: firestore.Client) -> None:
        handler = RecordingHandler()
        envelope = _envelope("contract_meridian_logistics.pdf")
        result = dispatch_event(firestore_client, envelope, handler, now=T0, sleep=FakeSleep())
        assert result.status is DispatchStatus.PROCESSED
        assert result.attempts == 1
        assert handler.calls == 1
        state = _runner_state(firestore_client, envelope)
        assert state is not None
        assert state["status"] == "completed"
        assert state["attempts"] == 1

    def test_retry_then_success(self, firestore_client: firestore.Client) -> None:
        handler = RecordingHandler(fail_times=2)
        config = RunnerConfig(max_attempts=3)
        result = dispatch_event(
            firestore_client,
            _envelope("financials_fy27.xlsx"),
            handler,
            config=config,
            now=T0,
            sleep=FakeSleep(),
        )
        assert result.status is DispatchStatus.PROCESSED
        assert result.attempts == 3
        assert handler.calls == 3

    def test_exhaust_dead_letters(self, firestore_client: firestore.Client) -> None:
        handler = RecordingHandler(always_fail=True)
        config = RunnerConfig(max_attempts=3)
        envelope = _envelope("broken.pdf")
        result = dispatch_event(
            firestore_client, envelope, handler, config=config, now=T0, sleep=FakeSleep()
        )
        assert result.status is DispatchStatus.DEAD_LETTERED
        assert result.attempts == 3
        assert result.last_error is not None
        assert "handler crashed" in result.last_error
        assert handler.calls == 3
        sink = FirestoreDeadLetterSink(firestore_client)
        records = sink.list_dead_letters(DEAL)
        assert len(records) == 1
        assert records[0].event_id == envelope.event_id
        state = _runner_state(firestore_client, envelope)
        assert state is not None and state["status"] == "dead_lettered"

    def test_backoff_is_exponential_and_capped(self, firestore_client: firestore.Client) -> None:
        handler = RecordingHandler(always_fail=True)
        config = RunnerConfig(max_attempts=4, backoff_base_s=1.0, backoff_max_s=2.0)
        fake_sleep = FakeSleep()
        result = dispatch_event(
            firestore_client,
            _envelope("backoff.pdf"),
            handler,
            config=config,
            now=T0,
            sleep=fake_sleep,
        )
        assert result.status is DispatchStatus.DEAD_LETTERED
        assert fake_sleep.delays == [1.0, 2.0, 2.0]


class TestIdempotency:
    def test_replay_skips_handler(self, firestore_client: firestore.Client) -> None:
        handler = RecordingHandler()
        envelope = _envelope("contract_meridian_logistics.pdf")
        first = dispatch_event(firestore_client, envelope, handler, now=T0, sleep=FakeSleep())
        replay = dispatch_event(firestore_client, envelope, handler, now=T0, sleep=FakeSleep())
        assert first.status is DispatchStatus.PROCESSED
        assert replay.status is DispatchStatus.ALREADY_PROCESSED
        assert handler.calls == 1

    def test_replay_of_rebuilt_envelope_skips_handler(
        self, firestore_client: firestore.Client
    ) -> None:
        """Redeliveries mint a new event_id; only the dedupe key is stable."""
        handler = RecordingHandler()
        first_envelope = _envelope("contract_meridian_logistics.pdf")
        redelivered = _envelope("contract_meridian_logistics.pdf")
        assert first_envelope.event_id != redelivered.event_id
        assert first_envelope.dedupe_key == redelivered.dedupe_key
        dispatch_event(firestore_client, first_envelope, handler, now=T0, sleep=FakeSleep())
        replay = dispatch_event(firestore_client, redelivered, handler, now=T0, sleep=FakeSleep())
        assert replay.status is DispatchStatus.ALREADY_PROCESSED
        assert handler.calls == 1

    def test_dead_lettered_replay_is_not_reprocessed(
        self, firestore_client: firestore.Client
    ) -> None:
        handler = RecordingHandler(always_fail=True)
        config = RunnerConfig(max_attempts=2)
        envelope = _envelope("poison.pdf")
        first = dispatch_event(
            firestore_client, envelope, handler, config=config, now=T0, sleep=FakeSleep()
        )
        replay = dispatch_event(
            firestore_client, envelope, handler, config=config, now=T0, sleep=FakeSleep()
        )
        assert first.status is DispatchStatus.DEAD_LETTERED
        assert replay.status is DispatchStatus.DEAD_LETTERED
        assert handler.calls == 2

    def test_distinct_events_dispatch_independently(
        self, firestore_client: firestore.Client
    ) -> None:
        handler = RecordingHandler()
        first = dispatch_event(
            firestore_client, _envelope("a.pdf"), handler, now=T0, sleep=FakeSleep()
        )
        second = dispatch_event(
            firestore_client, _envelope("b.pdf"), handler, now=T0, sleep=FakeSleep()
        )
        assert first.status is DispatchStatus.PROCESSED
        assert second.status is DispatchStatus.PROCESSED
        assert handler.calls == 2
