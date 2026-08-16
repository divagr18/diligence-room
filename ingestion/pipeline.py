"""Day-4 ingestion pipeline assembly (BUILD_PLAN D4-M7).

detect -> lineage (dup suppression) -> parse -> sentinel tripwire ->
PII mark -> classify -> route event. Every decision is emitted to the
canonical event log and the publisher; poisoned documents stop at the
tripwire (SECURITY_EVENT) and never reach the classifier (cost gate).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from google.cloud import firestore
from opentelemetry.trace import Tracer

from ingestion.chunking import chunk
from ingestion.classifier import Classifier
from ingestion.lineage import register_document
from ingestion.models import LineageStatus, RouteDecision, SentinelDecision
from ingestion.parsing import LocalParser, Parser
from ingestion.sentinel import (
    GEMMA_MODEL_ID,
    SentinelModel,
    heavy_pii,
    run_sentinel,
)
from memory.event_log import EventLog
from observability.tracing import parse_span, route_span, sentinel_span, tripwire_span
from runtime.bucket_notify import parse_notification
from runtime.events import EventEnvelope, EventType, new_event

_PIPELINE_ACTOR = "ingestion-pipeline"

STATUS_ROUTED = "routed"
STATUS_TRIPWIRED = "tripwired"
STATUS_SUPPRESSED = "suppressed"
STATUS_NEEDS_OCR = "needs_ocr"


class _Publisher(Protocol):
    def publish(self, event: EventEnvelope) -> str: ...


@dataclass(frozen=True, slots=True)
class IngestContext:
    client: firestore.Client
    publisher: _Publisher
    sentinel: SentinelModel
    classifier: Classifier
    parser: Parser = field(default_factory=LocalParser)
    tracer: Tracer | None = None


@dataclass(frozen=True, slots=True)
class IngestResult:
    document_id: str
    deal_id: str
    status: str
    route: RouteDecision | None
    dlp_required: bool
    needs_ocr: bool
    events: tuple[EventEnvelope, ...]


def ingest_blob(
    context: IngestContext,
    deal_id: str,
    document_id: str,
    blob: bytes,
    bucket: str | None = None,
) -> IngestResult:
    """Run the full Day-4 chain over one document; emit events as it goes."""
    emitted: list[EventEnvelope] = []
    event_log = EventLog(context.client)
    tracer = context.tracer

    def emit(event: EventEnvelope) -> None:
        context.publisher.publish(event)
        event_log.append(event)
        emitted.append(event)

    record = register_document(context.client, deal_id, document_id, document_id, blob)
    if record.status is LineageStatus.SUPPRESSED:
        return IngestResult(document_id, deal_id, STATUS_SUPPRESSED, None, False, False, ())

    if tracer is not None:
        with parse_span(tracer):
            parsed = context.parser.parse(blob, document_id, deal_id)
    else:
        parsed = context.parser.parse(blob, document_id, deal_id)

    parsed_payload: dict[str, object] = {
        "document_id": document_id,
        "checksum": record.checksum,
        "format": parsed.format.kind.value,
        "needs_ocr": parsed.format.needs_ocr,
        "logical_key": record.logical_key,
        "version": record.version,
        "lineage_status": record.status.value,
        "chunks": len(chunk(parsed)),
    }
    if bucket is not None:
        parsed_payload["bucket"] = bucket
    emit(new_event(deal_id, _PIPELINE_ACTOR, EventType.DOCUMENT_PARSED, parsed_payload))

    if parsed.text is None:
        return IngestResult(
            document_id, deal_id, STATUS_NEEDS_OCR, None, False, True, tuple(emitted)
        )

    if tracer is not None:
        with sentinel_span(tracer, decision="pending", model=GEMMA_MODEL_ID) as span:
            report = run_sentinel(context.sentinel, parsed.text)
            span.set_attribute("sentinel.decision", report.decision.value)
            span.set_attribute("sentinel.pii_count", len(report.pii_spans))
    else:
        report = run_sentinel(context.sentinel, parsed.text)

    if report.decision is SentinelDecision.TRIPWIRE:
        if tracer is not None:
            with tripwire_span(tracer) as span:
                span.set_attribute("tripwire.reason", report.tripwire.reason)
        emit(
            new_event(
                deal_id,
                _PIPELINE_ACTOR,
                EventType.SECURITY_EVENT,
                {
                    "document_id": document_id,
                    "reason": "injection_tripwire",
                    "patterns": list(report.tripwire.patterns),
                    "checksum": record.checksum,
                    "version": record.version,
                },
            )
        )
        return IngestResult(
            document_id, deal_id, STATUS_TRIPWIRED, None, False, False, tuple(emitted)
        )

    if tracer is not None:
        with route_span(tracer, workstream=None) as span:
            decision = context.classifier.classify(document_id, parsed.text, report.class_hint)
            span.set_attribute("route.workstream", decision.workstream or "unrouted")
    else:
        decision = context.classifier.classify(document_id, parsed.text, report.class_hint)

    dlp_required = heavy_pii(report.pii_spans)
    emit(
        new_event(
            deal_id,
            _PIPELINE_ACTOR,
            EventType.DOCUMENT_ROUTED,
            {
                "document_id": document_id,
                "doc_type": decision.doc_type,
                "workstream": decision.workstream,
                "confidence": decision.confidence,
                "reasons": list(decision.reasons),
                "dlp_required": dlp_required,
                "checksum": record.checksum,
                "version": record.version,
            },
        )
    )
    return IngestResult(
        document_id, deal_id, STATUS_ROUTED, decision, dlp_required, False, tuple(emitted)
    )


def ingest_notification(
    context: IngestContext, payload: Mapping[str, object], blob: bytes
) -> IngestResult:
    """Bucket-notification entry point: derive the deal, then run the chain."""
    envelope = parse_notification(payload)
    document_id = str(envelope.payload["document_id"])
    raw_bucket = envelope.payload.get("bucket")
    bucket = raw_bucket if isinstance(raw_bucket, str) else None
    return ingest_blob(context, envelope.deal_id, document_id, blob, bucket=bucket)
