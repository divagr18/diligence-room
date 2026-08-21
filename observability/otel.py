"""OTel backbone — provider construction and exporter seams (BUILD_PLAN D10-M1).

One service name per fleet component and a single seam for exporter choice:
offline builds a bare provider (tests compose in-memory exporters on top via
``observability.tracing``); ``live=True`` attaches the Cloud Trace exporter
behind a ``BatchSpanProcessor`` — imported lazily so the offline path can
never touch it.
"""

from __future__ import annotations

from enum import StrEnum

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import Span

from observability.tracing import setup_tracing


class ServiceName(StrEnum):
    """One stable ``service.name`` per fleet component (vision §7.7)."""

    INGESTION_PIPELINE = "diligence-room-ingestion"
    GATEWAY = "diligence-room-gateway"
    COORDINATOR = "diligence-room-coordinator"
    NEGOTIATION = "diligence-room-negotiation"
    DASHBOARD_API = "diligence-room-dashboard-api"
    REDTEAM_RUNNER = "diligence-room-redteam-runner"


def _cloud_trace_exporter() -> SpanExporter:
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

    # Untyped GCP exporter constructor (module is import-ignored in pyproject);
    # same pattern as the untyped Pub/Sub publish in runtime/events.py.
    return CloudTraceSpanExporter()  # type: ignore[no-untyped-call]


def build_provider(
    service: ServiceName, *, live: bool = False, exporter: SpanExporter | None = None
) -> TracerProvider:
    """Build a ``TracerProvider`` for *service*; live attaches a Cloud Trace sink.

    ``exporter`` overrides the live sink (test injection seam); offline it
    forwards an optional exporter through the existing tracing helper.
    """
    if live:
        provider = TracerProvider(resource=Resource.create({"service.name": service.value}))
        sink = exporter if exporter is not None else _cloud_trace_exporter()
        provider.add_span_processor(BatchSpanProcessor(sink))
        return provider
    return setup_tracing(service_name=service.value, exporter=exporter)


def trace_id_of(span: Span) -> str:
    """Return the span's trace id as 32 lowercase hex chars (Cloud Trace form)."""
    return format(span.get_span_context().trace_id, "032x")
