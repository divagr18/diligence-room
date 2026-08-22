"""OTel span helpers with GenAI semantic conventions (vision §7.7).

Offline half of "sentinel visible in traces": providers are returned per
call (never global state) so tests compose isolated in-memory exporters;
the live window swaps in a Cloud Trace exporter at the same seam.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Link, Span, Tracer

_TRACER_NAME = "diligence-room.ingestion"


def setup_tracing(
    service_name: str = "diligence-room-ingestion", exporter: SpanExporter | None = None
) -> TracerProvider:
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


def tracer_from(provider: TracerProvider) -> Tracer:
    return provider.get_tracer(_TRACER_NAME)


def set_genai_attributes(
    span: Span, *, system: str, model: str, **extra: str | int | float | bool
) -> None:
    span.set_attribute("gen_ai.system", system)
    span.set_attribute("gen_ai.request.model", model)
    for key, value in extra.items():
        span.set_attribute(key, value)


@contextmanager
def parse_span(tracer: Tracer) -> Iterator[Span]:
    with tracer.start_as_current_span("ingestion.parse") as span:
        yield span


@contextmanager
def sentinel_span(tracer: Tracer, *, decision: str, model: str) -> Iterator[Span]:
    with tracer.start_as_current_span("sentinel.pre_classify") as span:
        set_genai_attributes(span, system="gemma", model=model)
        span.set_attribute("sentinel.decision", decision)
        yield span


@contextmanager
def tripwire_span(tracer: Tracer) -> Iterator[Span]:
    with tracer.start_as_current_span("sentinel.tripwire") as span:
        yield span


@contextmanager
def route_span(tracer: Tracer, *, workstream: str | None) -> Iterator[Span]:
    with tracer.start_as_current_span("classifier.route") as span:
        span.set_attribute("route.workstream", workstream if workstream is not None else "unrouted")
        yield span


@contextmanager
def stage_span(
    tracer: Tracer | None,
    name: str,
    *,
    links: Sequence[Link] | None = None,
    **attributes: str | int | float | bool,
) -> Iterator[Span | None]:
    """Open *name* when *tracer* is present; tracer-less call sites yield None."""
    if tracer is None:
        yield None
        return
    with tracer.start_as_current_span(
        name, links=list(links) if links is not None else None
    ) as span:
        for key, value in attributes.items():
            span.set_attribute(key, value)
        yield span


def install_in_memory_exporter(
    service_name: str = "test",
) -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    return setup_tracing(service_name=service_name, exporter=exporter), exporter
