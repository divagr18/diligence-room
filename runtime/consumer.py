"""Day-2 live consumer: bucket notifications -> audit log, hello agent, deal state.

Implements the live counterpart of the Day-2 gate chain (BUILD_PLAN
checklist: bucket notification -> event -> hello agent consumes -> deal-state
doc written), per vision §7.2-7.3:

    Pub/Sub pull (live) or JSON feed (offline)
        -> bucket_notify.parse_notification (document.ingested envelope)
        -> duplicate check on the envelope dedupe_key
        -> DealEventAuditLog.append (seq assignment)
        -> AgentInvoker (deployed hello agent live, echo offline)
        -> deals/{deal_id} counters (documents_ingested / last_*)

Guards: live mode (``--confirm-live``) refuses while FIRESTORE_EMULATOR_HOST
is set; offline feed mode refuses without it, so tests and local runs never
reach live GCP.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import sys
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from google.cloud import firestore

from gateway.audit import DealEventAuditLog
from infra.data_room import PROJECT_ID, SUBSCRIPTION
from infra.deploy.agent_engine import invoke_text, load_resource_name
from runtime.bucket_notify import BucketNotificationError, parse_notification
from runtime.events import EventEnvelope

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 0.5


class ProcessStatus(StrEnum):
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ProcessResult:
    status: ProcessStatus
    seq: int | None
    event_id: str | None


class MessageSource(Protocol):
    def messages(self) -> Iterable[tuple[str, Mapping[str, object]]]:
        """Yield (message_id, notification payload) pairs."""


class FeedSource:
    """In-memory notification feed for tests and --feed-file offline mode."""

    def __init__(self, payloads: Sequence[Mapping[str, object]]) -> None:
        self._payloads = list(payloads)

    def messages(self) -> Iterable[tuple[str, Mapping[str, object]]]:
        for index, payload in enumerate(self._payloads):
            yield f"feed-{index}", payload


class PubSubPullSource:
    """Live pull source for the deal-events subscription (never used in tests).

    Each ``messages()`` call drains pull batches until one returns nothing,
    acknowledging each batch once it has been fully consumed. A failure
    mid-batch leaves it unacked, so Pub/Sub redelivers and the idempotent
    dedupe path replays it safely.
    """

    def __init__(self, project: str, batch_size: int = 16) -> None:
        self._subscription = f"projects/{project}/subscriptions/{SUBSCRIPTION}"
        self._batch_size = batch_size

    def messages(self) -> Iterable[tuple[str, Mapping[str, object]]]:
        from importlib import import_module

        pubsub_v1 = import_module("google.cloud.pubsub_v1")
        with contextlib.closing(pubsub_v1.SubscriberClient()) as client:
            while True:
                response = client.pull(
                    request={
                        "subscription": self._subscription,
                        "max_messages": self._batch_size,
                    }
                )
                received = list(response.received_messages)
                if not received:
                    return
                ack_ids: list[str] = []
                for received_message in received:
                    payload = _normalize_gcs_notification(received_message.message)
                    yield str(received_message.ack_id), payload
                    ack_ids.append(str(received_message.ack_id))
                client.acknowledge(request={"subscription": self._subscription, "ack_ids": ack_ids})


def _normalize_gcs_notification(message: Any) -> dict[str, object]:
    """Merge the live GCS notification into the flat payload contract.

    Live GCS bucket notifications deliver the storage-object resource JSON in
    ``message.data`` (has ``name``/``bucket``/``contentType``) but carry
    ``eventType`` in ``message.attributes``. The offline fixtures and
    ``bucket_notify.parse_notification`` expect a single flat mapping, so the
    attribute is folded in here.
    """
    data = json.loads(bytes(message.data).decode("utf-8"))
    attributes = dict(message.attributes or {})
    payload = dict(data)
    event_type = attributes.get("eventType")
    if event_type is not None and "eventType" not in payload:
        payload["eventType"] = event_type
    return payload


class AgentInvoker(Protocol):
    def invoke(self, deal_id: str, message: str) -> str:
        """Send the ingestion message to the deal's hello agent; return its text."""


class IngestionHook(Protocol):
    def ingest(self, envelope: EventEnvelope) -> None:
        """Run the Day-4 ingestion pipeline for an ingested document."""


class EchoInvoker:
    """Offline default: echoes the message back."""

    def invoke(self, deal_id: str, message: str) -> str:
        del deal_id
        return message


class AgentEngineInvoker:
    """Live invoker: routes messages to the deployed Agent Engine hello agent."""

    def __init__(self, resource_name: str) -> None:
        self._resource_name = resource_name

    def invoke(self, deal_id: str, message: str) -> str:
        del deal_id
        return asyncio.run(invoke_text(self._resource_name, message))


class DealEventConsumer:
    """Turns bucket notifications into audit entries, agent calls, deal state.

    Duplicate detection keys on the envelope ``dedupe_key`` (content hash of
    deal/actor/type/payload): ``parse_notification`` mints a fresh event_id
    on every call, so only the dedupe key is stable across redeliveries of
    the same notification. A duplicate returns before the agent is invoked
    or the deal document is touched.
    """

    def __init__(
        self,
        client: firestore.Client,
        source: MessageSource,
        invoker: AgentInvoker,
        audit: DealEventAuditLog,
        ingestion_hook: IngestionHook | None = None,
    ) -> None:
        self._client = client
        self.source = source
        self._invoker = invoker
        self._audit = audit
        self._ingestion_hook = ingestion_hook

    def process_notification(self, payload: Mapping[str, object]) -> ProcessResult:
        try:
            envelope = parse_notification(payload)
        except BucketNotificationError as exc:
            logger.info("skipping bucket notification: %s", exc)
            return ProcessResult(status=ProcessStatus.SKIPPED, seq=None, event_id=None)

        existing = self._find_duplicate(envelope)
        if existing is not None:
            data = existing.to_dict() or {}
            logger.info("duplicate notification for deal %s", envelope.deal_id)
            return ProcessResult(
                status=ProcessStatus.DUPLICATE,
                seq=int(data["seq"]),
                event_id=str(data["event_id"]),
            )

        seq = self._audit.append(envelope)
        document_id = str(envelope.payload["document_id"])
        if self._ingestion_hook is not None:
            self._ingestion_hook.ingest(envelope)
        self._invoker.invoke(
            envelope.deal_id,
            f"Document ingested: {document_id} in deal {envelope.deal_id}. Echo to confirm.",
        )
        self._client.collection("deals").document(envelope.deal_id).update(
            {
                "documents_ingested": firestore.Increment(1),
                "last_document_id": document_id,
                "last_ingested_at": envelope.ts,
            }
        )
        return ProcessResult(status=ProcessStatus.PROCESSED, seq=seq, event_id=envelope.event_id)

    def _find_duplicate(self, envelope: EventEnvelope) -> firestore.DocumentSnapshot | None:
        docs = (
            self._client.collection("deals")
            .document(envelope.deal_id)
            .collection("events")
            .where(filter=firestore.FieldFilter("dedupe_key", "==", envelope.dedupe_key))
            .limit(1)
            .stream()
        )
        return next(docs, None)


def run(source: MessageSource, consumer: DealEventConsumer, timeout_seconds: float | None) -> int:
    """Drain the source once (timeout None) or poll until the deadline.

    Returns the processed count and prints a summary line
    ``processed=N duplicates=M skipped=K``.
    """
    tally: Counter[ProcessStatus] = Counter()
    deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
    while True:
        for _message_id, payload in source.messages():
            tally[consumer.process_notification(payload).status] += 1
        if deadline is None or time.monotonic() >= deadline:
            break
        time.sleep(min(_POLL_INTERVAL_SECONDS, deadline - time.monotonic()))
    processed = tally[ProcessStatus.PROCESSED]
    print(
        f"processed={processed} "
        f"duplicates={tally[ProcessStatus.DUPLICATE]} "
        f"skipped={tally[ProcessStatus.SKIPPED]}"
    )
    return processed


def _load_feed(path: Path) -> list[Mapping[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"feed file {path} must contain a JSON array of notification objects")
    payloads: list[Mapping[str, object]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"feed file {path}: entry {index} is not a JSON object")
        payloads.append(item)
    return payloads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Consume GCS bucket notifications for deals.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--once",
        action="store_true",
        help="drain currently available messages and exit (default)",
    )
    mode.add_argument(
        "--watch",
        action="store_true",
        help="poll the source until --timeout-seconds elapses",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="watch-mode deadline in seconds (ignored with --once)",
    )
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="consume live Pub/Sub with the deployed agent (refuses under the emulator)",
    )
    parser.add_argument(
        "--feed-file",
        type=Path,
        default=None,
        help="offline JSON array of bucket-notification payloads",
    )
    args = parser.parse_args(argv)

    if bool(args.confirm_live):
        if "FIRESTORE_EMULATOR_HOST" in os.environ:
            sys.exit(
                "Refusing live --confirm-live consumer: FIRESTORE_EMULATOR_HOST is set; "
                "unset it to consume real Pub/Sub notifications."
            )
        source: MessageSource = PubSubPullSource(PROJECT_ID)
        invoker: AgentInvoker = AgentEngineInvoker(load_resource_name(None))
    else:
        if "FIRESTORE_EMULATOR_HOST" not in os.environ:
            sys.exit(
                "Refusing offline consumer: FIRESTORE_EMULATOR_HOST is not set; "
                "start the Firestore emulator (offline mode targets the emulator only)."
            )
        try:
            payloads = _load_feed(args.feed_file) if args.feed_file else []
        except ValueError as exc:
            sys.exit(str(exc))
        source = FeedSource(payloads)
        invoker = EchoInvoker()

    client = firestore.Client(project=PROJECT_ID)
    consumer = DealEventConsumer(
        client=client, source=source, invoker=invoker, audit=DealEventAuditLog(client)
    )
    timeout = args.timeout_seconds if args.watch else None
    run(source, consumer, timeout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
