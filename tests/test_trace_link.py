"""Finding <-> trace link tests (BUILD_PLAN D10-M4, vision §7.7).

The lineage record carries the ingestion span context; evidence-gated findings
carry the trace they were created under and link back to every source
document's ingestion span. Resolution works fully offline against Firestore.
"""

from __future__ import annotations

import json

from google.cloud import firestore
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agents.coordinator.synthesize import synthesize_critical
from agents.fleet import run_workstream_offline
from agents.tools.data_room_read import DatasetDocSource
from agents.tools.finding_create import make_finding_create
from identity.principals import principal_for
from ingestion.chunking import chunk
from ingestion.classifier import FakeClassifier
from ingestion.lineage import span_context_for
from ingestion.parsing import LocalParser
from ingestion.pipeline import IngestContext, ingest_blob
from ingestion.sentinel import FakeSentinel
from memory.findings import FindingsStore
from observability.trace_link import resolve
from observability.tracing import install_in_memory_exporter, tracer_from
from registry.models import Workstream
from runtime.events import InMemoryPublisher

DEAL = "deal-falcon"
_CONTRACT = "contract_meridian_logistics.pdf"


def _spans(exporter: InMemorySpanExporter, name: str) -> list[ReadableSpan]:
    return [span for span in exporter.get_finished_spans() if span.name == name]


def _ingest_contract(
    client: firestore.Client, provider: TracerProvider, exporter: InMemorySpanExporter
) -> ReadableSpan:
    context = IngestContext(
        client=client,
        publisher=InMemoryPublisher(),
        sentinel=FakeSentinel(),
        classifier=FakeClassifier(),
        tracer=tracer_from(provider),
    )
    blob = DatasetDocSource().read(_CONTRACT)
    assert blob is not None
    result = ingest_blob(context, DEAL, _CONTRACT, blob)
    assert result.status == "routed"
    parse_spans = _spans(exporter, "ingestion.parse")
    assert len(parse_spans) == 1
    return parse_spans[0]


def _contract_coc_span() -> str:
    blob = DatasetDocSource().read(_CONTRACT)
    assert blob is not None
    parsed = LocalParser().parse(blob, _CONTRACT, DEAL)
    return next(c.text for c in chunk(parsed) if c.locator == "clause:11.3")


def _finding_json() -> dict[str, object]:
    return {
        "title": "Trace-link probe CoC termination right",
        "summary": "Termination right within 90 days of a change of control.",
        "severity": "high",
        "confidence": 0.9,
        "evidence": [
            {
                "verbatim_span": _contract_coc_span(),
                "document_id": _CONTRACT,
                "category": "contracts",
                "chunk_ref": "clause:11.3",
            }
        ],
        "source_documents": [_CONTRACT],
        "affected_entities": ["Meridian Logistics, Inc."],
        "questions": [],
    }


class TestLineageCarrier:
    def test_ingest_records_the_parse_span_context(
        self, firestore_client: firestore.Client
    ) -> None:
        provider, exporter = install_in_memory_exporter("carrier")
        parse_span = _ingest_contract(firestore_client, provider, exporter)
        recorded = span_context_for(firestore_client, DEAL, _CONTRACT)
        assert recorded is not None
        assert recorded == (
            format(parse_span.context.trace_id, "032x"),
            format(parse_span.context.span_id, "016x"),
        )

    def test_tracerless_ingest_leaves_no_span_context(
        self, firestore_client: firestore.Client
    ) -> None:
        context = IngestContext(
            client=firestore_client,
            publisher=InMemoryPublisher(),
            sentinel=FakeSentinel(),
            classifier=FakeClassifier(),
        )
        blob = DatasetDocSource().read(_CONTRACT)
        assert blob is not None
        result = ingest_blob(context, DEAL, _CONTRACT, blob)
        assert result.status == "routed"
        assert span_context_for(firestore_client, DEAL, _CONTRACT) is None


class TestFindingTraceId:
    def test_finding_create_sets_audit_trace_and_links_ingestion(
        self, firestore_client: firestore.Client
    ) -> None:
        ingest_provider, ingest_exporter = install_in_memory_exporter("carrier-2")
        parse_span = _ingest_contract(firestore_client, ingest_provider, ingest_exporter)
        tool_provider, tool_exporter = install_in_memory_exporter("writer")
        tool = make_finding_create(
            principal_for(Workstream.LEGAL, DEAL),
            firestore_client,
            DatasetDocSource(),
            tracer=tracer_from(tool_provider),
        )
        result = tool(finding_json=json.dumps(_finding_json()))
        assert result["decision"] == "created"
        stored = FindingsStore(firestore_client).get(DEAL, str(result["finding_id"]))
        assert stored.audit_trace_id is not None
        assert len(stored.audit_trace_id) == 32
        create_spans = _spans(tool_exporter, "finding.create")
        assert len(create_spans) == 1
        links = list(create_spans[0].links)
        assert len(links) == 1
        assert links[0].context.trace_id == parse_span.context.trace_id

    def test_tracerless_finding_keeps_audit_trace_none(
        self, firestore_client: firestore.Client
    ) -> None:
        tool = make_finding_create(
            principal_for(Workstream.LEGAL, DEAL), firestore_client, DatasetDocSource()
        )
        result = tool(finding_json=json.dumps(_finding_json()))
        stored = FindingsStore(firestore_client).get(DEAL, str(result["finding_id"]))
        assert stored.audit_trace_id is None


class TestResolution:
    def test_resolve_links_finding_to_ingestion_sources(
        self, firestore_client: firestore.Client
    ) -> None:
        ingest_provider, ingest_exporter = install_in_memory_exporter("carrier-3")
        parse_span = _ingest_contract(firestore_client, ingest_provider, ingest_exporter)
        tool_provider, _ = install_in_memory_exporter("writer-2")
        tool = make_finding_create(
            principal_for(Workstream.LEGAL, DEAL),
            firestore_client,
            DatasetDocSource(),
            tracer=tracer_from(tool_provider),
        )
        finding_id = str(tool(finding_json=json.dumps(_finding_json()))["finding_id"])
        resolution = resolve(firestore_client, DEAL, finding_id)
        assert resolution is not None
        assert resolution.finding_id == finding_id
        assert resolution.audit_trace_id is not None
        assert [source.document_id for source in resolution.sources] == [_CONTRACT]
        assert resolution.sources[0].trace_id == format(parse_span.context.trace_id, "032x")

    def test_resolve_unknown_finding_returns_none(self, firestore_client: firestore.Client) -> None:
        assert resolve(firestore_client, DEAL, "no-such-finding") is None

    def test_synthesis_finding_carries_audit_trace(
        self, firestore_client: firestore.Client
    ) -> None:
        for workstream in (
            Workstream.LEGAL,
            Workstream.FINANCE,
            Workstream.HR,
            Workstream.IP_TECH,
        ):
            run_workstream_offline(firestore_client, DEAL, workstream)
        provider, exporter = install_in_memory_exporter("synthesis-writer")
        finding_id = synthesize_critical(
            firestore_client, DEAL, publisher=InMemoryPublisher(), tracer=tracer_from(provider)
        )
        assert finding_id is not None
        stored = FindingsStore(firestore_client).get(DEAL, finding_id)
        assert stored.audit_trace_id is not None
        resolution = resolve(firestore_client, DEAL, finding_id)
        assert resolution is not None
        assert resolution.audit_trace_id == stored.audit_trace_id
        assert len(resolution.sources) == len(stored.evidence)
        # Fleet seeding ran tracer-less: no ingestion context exists to link.
        assert all(source.trace_id is None for source in resolution.sources)
        assert len(_spans(exporter, "finding.create")) == 1
