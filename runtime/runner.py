"""Dispatch runner: bounded retries + idempotency (BUILD_PLAN D6-M2).

Dispatches one event envelope to a handler with:
- **idempotency keyed on the envelope dedupe key** (the event hash): a
  completed dispatch is never re-run on redelivery; only the dedupe key is
  stable across redeliveries, so state is stored under it;
- **bounded retries** with exponential backoff capped at ``backoff_max_s``;
- **dead-letter handoff** to the DLQ sink after ``max_attempts`` failures,
  leaving a ``dead_lettered`` state marker so replays do not reprocess.

Dispatch state lives at ``deals/{deal_id}/runner_state/{dedupe_key}`` with
terminal statuses ``completed`` / ``dead_lettered`` (crash-resume build-out
arrives Day 9).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, cast

from google.cloud import firestore

from runtime.dlq import FirestoreDeadLetterSink
from runtime.events import EventEnvelope

_STATE_COLLECTION = "runner_state"
_STATUS_COMPLETED = "completed"
_STATUS_DEAD_LETTERED = "dead_lettered"


class DispatchStatus(StrEnum):
    PROCESSED = "processed"
    ALREADY_PROCESSED = "already_processed"
    DEAD_LETTERED = "dead_lettered"


@dataclass(frozen=True, slots=True)
class RunnerConfig:
    max_attempts: int = 3
    backoff_base_s: float = 0.05
    backoff_max_s: float = 1.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be >= 1, got {self.max_attempts}")
        if self.backoff_base_s <= 0 or self.backoff_max_s < self.backoff_base_s:
            raise ValueError("backoff bounds must satisfy 0 < base <= max")


@dataclass(frozen=True, slots=True)
class DispatchResult:
    status: DispatchStatus
    attempts: int
    last_error: str | None


class DispatchHandler(Protocol):
    def handle(self, envelope: EventEnvelope) -> None: ...


def _backoff_seconds(config: RunnerConfig, attempt: int) -> float:
    multiplier = 2.0 ** (attempt - 1)
    return min(config.backoff_base_s * multiplier, config.backoff_max_s)


def _state_ref(client: firestore.Client, envelope: EventEnvelope) -> firestore.DocumentReference:
    return cast(
        firestore.DocumentReference,
        client.collection("deals")
        .document(envelope.deal_id)
        .collection(_STATE_COLLECTION)
        .document(envelope.dedupe_key),
    )


def _write_state(
    client: firestore.Client,
    envelope: EventEnvelope,
    *,
    status: str,
    attempts: int,
    last_error: str | None,
    now: datetime,
) -> None:
    _state_ref(client, envelope).set(
        {
            "dedupe_key": envelope.dedupe_key,
            "event_id": envelope.event_id,
            "event_type": envelope.type.value,
            "status": status,
            "attempts": attempts,
            "last_error": last_error,
            "updated_at": now.isoformat(),
        }
    )


def dispatch_event(
    client: firestore.Client,
    envelope: EventEnvelope,
    handler: DispatchHandler,
    config: RunnerConfig | None = None,
    sink: FirestoreDeadLetterSink | None = None,
    now: datetime | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> DispatchResult:
    """Dispatch *envelope* through *handler* with retry/idempotency/DLQ."""
    settings = config if config is not None else RunnerConfig()
    stamp = now if now is not None else datetime.now(UTC)

    state_snapshot = _state_ref(client, envelope).get()
    if state_snapshot.exists:
        state = state_snapshot.to_dict()
        assert state is not None
        if state["status"] == _STATUS_COMPLETED:
            return DispatchResult(
                DispatchStatus.ALREADY_PROCESSED, int(str(state["attempts"])), None
            )
        return DispatchResult(
            DispatchStatus.DEAD_LETTERED,
            int(str(state["attempts"])),
            state["last_error"] if isinstance(state["last_error"], str) else None,
        )

    dlq = sink if sink is not None else FirestoreDeadLetterSink(client)
    last_error: str | None = None
    for attempt in range(1, settings.max_attempts + 1):
        try:
            handler.handle(envelope)
        except Exception as exc:  # noqa: BLE001 — the runner must survive any handler error
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt == settings.max_attempts:
                dlq.dead_letter(
                    envelope,
                    reason="max_retries_exceeded",
                    last_error=last_error,
                    attempts=attempt,
                    now=stamp,
                )
                _write_state(
                    client,
                    envelope,
                    status=_STATUS_DEAD_LETTERED,
                    attempts=attempt,
                    last_error=last_error,
                    now=stamp,
                )
                return DispatchResult(DispatchStatus.DEAD_LETTERED, attempt, last_error)
            sleep(_backoff_seconds(settings, attempt))
            continue
        _write_state(
            client,
            envelope,
            status=_STATUS_COMPLETED,
            attempts=attempt,
            last_error=None,
            now=stamp,
        )
        return DispatchResult(DispatchStatus.PROCESSED, attempt, None)
    raise AssertionError("unreachable: attempt loop always returns")  # pragma: no cover
