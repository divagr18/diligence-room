"""Finding <-> trace resolution (BUILD_PLAN D10-M4, vision §7.7).

The durable carrier is the data plane itself: each ingested document's lineage
record holds the ingestion span context, and each evidence-gated finding holds
the trace it was created under (``audit_trace_id``). Resolution therefore
works fully offline against Firestore; Cloud Trace is the live view of the
same identifiers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from google.cloud import firestore
from opentelemetry.trace import Link, SpanContext, TraceFlags

from ingestion.lineage import span_context_for
from memory.findings import FindingNotFoundError, FindingsStore


@dataclass(frozen=True, slots=True)
class LinkedSource:
    """One evidence source document plus the ingestion span that parsed it."""

    document_id: str
    trace_id: str | None
    span_id: str | None


@dataclass(frozen=True, slots=True)
class TraceResolution:
    """A finding's audit trace plus its linked ingestion sources."""

    finding_id: str
    audit_trace_id: str | None
    sources: tuple[LinkedSource, ...]


def _link(trace_id: str, span_id: str) -> Link:
    context = SpanContext(
        trace_id=int(trace_id, 16),
        span_id=int(span_id, 16),
        is_remote=True,
        trace_flags=TraceFlags(0),
    )
    return Link(context)


def ingestion_links(
    client: firestore.Client, deal_id: str, document_ids: Sequence[str]
) -> list[Link]:
    """OTel links from a finding span back to each document's ingestion span.

    Documents without a recorded span context (tracer-less ingest) contribute
    no link — a missing carrier must never break finding creation.
    """
    links: list[Link] = []
    for document_id in dict.fromkeys(document_ids):
        recorded = span_context_for(client, deal_id, document_id)
        if recorded is not None:
            links.append(_link(recorded[0], recorded[1]))
    return links


def resolve(client: firestore.Client, deal_id: str, finding_id: str) -> TraceResolution | None:
    """Resolve *finding_id* to its audit trace and linked ingestion sources."""
    try:
        finding = FindingsStore(client).get(deal_id, finding_id)
    except FindingNotFoundError:
        return None
    sources: list[LinkedSource] = []
    for document_id in dict.fromkeys(entry.document_id for entry in finding.evidence):
        recorded = span_context_for(client, deal_id, document_id)
        trace_id, span_id = recorded if recorded is not None else (None, None)
        sources.append(LinkedSource(document_id, trace_id, span_id))
    return TraceResolution(
        finding_id=finding.finding_id,
        audit_trace_id=finding.audit_trace_id,
        sources=tuple(sources),
    )
