"""Day-10 live trace window (BUILD_PLAN D10-M1 live beat, vision §7.7).

Small live window against real GCP: builds a Cloud Trace span chain for one
ingestion -> finding creation -> resolution against live Firestore, using the
same Offline Fleet tracer seam (observability.otel) that Day-10 tests cover
with the in-memory exporter. Guards: --confirm-live, refuses under the
emulator, env contract (no import-time defaults). Cost: <= 50 spans, inside
the Cloud Trace 2.5M free tier. Teardown is none -- traces expire on their
own; the live Firestore deal is prefixed deal-trace-live for easy cleanup.
"""

from __future__ import annotations

import argparse
import os
import sys

from google.cloud import firestore

_REQUIRED_ENV: tuple[str, ...] = (
    "GOOGLE_CLOUD_PROJECT",
    "DILIGENCE_TRACE_ENABLED",
)

_DEAL_ID_DEFAULT = "deal-trace-live"


def required_env() -> tuple[str, ...]:
    return _REQUIRED_ENV


def validate_live_env() -> tuple[str, ...]:
    return tuple(name for name in _REQUIRED_ENV if not os.environ.get(name))


class _EventLogPublisher:
    def __init__(self, client: firestore.Client) -> None:
        from memory.event_log import EventLog

        self._log = EventLog(client)

    def publish(self, event: object) -> str:
        seq = self._log.append(event)  # type: ignore[arg-type]
        return str(seq)


def _run_live(deal_id: str) -> int:
    from agents.tools.data_room_read import DatasetDocSource
    from agents.tools.finding_create import make_finding_create
    from identity.principals import principal_for
    from ingestion.chunking import chunk
    from ingestion.classifier import FakeClassifier
    from ingestion.parsing import LocalParser
    from ingestion.pipeline import IngestContext, ingest_blob
    from ingestion.sentinel import FakeSentinel
    from observability.otel import ServiceName, build_provider
    from observability.trace_link import resolve
    from observability.tracing import tracer_from
    from registry.models import Workstream
    from runtime.events import InMemoryPublisher

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    client = firestore.Client(project=project)

    # Cloud Trace exporter behind BatchSpanProcessor; offline tests use the
    # in-memory seam, live swaps to the gcp exporter at the same interface.
    provider = build_provider(ServiceName.INGESTION_PIPELINE, live=True)
    tracer = tracer_from(provider)

    # Ingest one contract document with the live tracer -- carrier records the
    # parse span context to lineage for link construction.
    context = IngestContext(
        client=client,
        publisher=InMemoryPublisher(),
        sentinel=FakeSentinel(),
        classifier=FakeClassifier(),
        tracer=tracer,
    )
    blob = DatasetDocSource().read("contract_meridian_logistics.pdf")
    assert blob is not None
    result = ingest_blob(context, deal_id, "contract_meridian_logistics.pdf", blob)
    print(f"[trace] ingest status={result.status} route={result.route}")

    # Evidence-gated finding creation with links + audit_trace_id on the live trace.
    parsed = LocalParser().parse(blob, "contract_meridian_logistics.pdf", deal_id)
    coc_span = next(c.text for c in chunk(parsed) if c.locator == "clause:11.3")
    principal = principal_for(Workstream.LEGAL, deal_id)
    tool = make_finding_create(principal, client, DatasetDocSource(), tracer=tracer)
    import json

    finding_json = json.dumps(
        {
            "title": "Live trace probe CoC termination right",
            "summary": "Termination right within 90 days of a change of control.",
            "severity": "high",
            "confidence": 0.9,
            "evidence": [
                {
                    "verbatim_span": coc_span,
                    "document_id": "contract_meridian_logistics.pdf",
                    "category": "contracts",
                    "chunk_ref": "clause:11.3",
                }
            ],
            "source_documents": ["contract_meridian_logistics.pdf"],
            "affected_entities": ["Meridian Logistics, Inc."],
            "questions": [],
        }
    )
    created = tool(finding_json=finding_json)
    if created.get("decision") != "created":
        print(f"[trace] RED: finding_create returned {created}")
        provider.force_flush()
        provider.shutdown()
        return 1
    finding_id = str(created["finding_id"])
    print(f"[trace] finding created: {finding_id}")

    # Resolution fully offline via Firestore: proves the durable carrier.
    resolution = resolve(client, deal_id, finding_id)
    assert resolution is not None
    print(f"[trace] resolution audit_trace_id={resolution.audit_trace_id}")
    for source in resolution.sources:
        print(f"[trace] source {source.document_id} trace_id={source.trace_id}")

    # Flush the BatchSpanProcessor so the live spans reach Cloud Trace before exit.
    provider.force_flush(timeout_millis=10000)
    # The finding span is the durable trace id; also print via trace_id_of for
    # Cloud Trace console lookup.
    finding_span_trace = resolution.audit_trace_id
    if finding_span_trace:
        print(f"[trace] Cloud Trace trace_id: {finding_span_trace}")
        print(
            f"[trace] Console: https://console.cloud.google.com/traces/list"
            f"?project={project}&tid={finding_span_trace}"
        )
    provider.shutdown()
    print("[trace] PASS: live chain ingested, linked, and flushed to Cloud Trace")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Day-10 live window: Cloud Trace span chain for one ingestion + finding."
    )
    parser.add_argument("--deal-id", default=_DEAL_ID_DEFAULT)
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="required: run against real GCP (Cloud Trace + live Firestore)",
    )
    args = parser.parse_args(argv)

    if not args.confirm_live:
        print("Refusing: pass --confirm-live to open the Day-10 live window.", file=sys.stderr)
        sys.exit(1)
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        print(
            "Refusing: FIRESTORE_EMULATOR_HOST is set; live window targets real GCP.",
            file=sys.stderr,
        )
        sys.exit(1)
    missing = validate_live_env()
    if missing:
        print("Refusing: missing live-window env: " + ", ".join(missing), file=sys.stderr)
        sys.exit(1)

    return _run_live(args.deal_id)


if __name__ == "__main__":
    sys.exit(main())
