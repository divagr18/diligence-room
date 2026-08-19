"""Mixed-bundle end-to-end gate (BUILD_PLAN D4-M8; scenarios S1-S3, S6).

The Day-4 acceptance contract: a realistic bundle â€” native PDFs, XLSX, DOCX,
a scanned image-only PDF, and an injection probe â€” moves through the full
chain (detect -> lineage -> parse -> sentinel -> classify -> route events),
offline against the Firestore emulator, with the sentinel model labeled on
captured spans. This file is what the live window must reproduce.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from google.cloud import firestore
from opentelemetry.sdk.trace import ReadableSpan

from ingestion.classifier import FakeClassifier
from ingestion.pipeline import (
    IngestContext,
    IngestResult,
    ingest_blob,
)
from ingestion.sentinel import GEMMA_MODEL_ID, FakeSentinel
from observability.tracing import install_in_memory_exporter, tracer_from
from runtime.events import EventEnvelope, EventType, InMemoryPublisher

BundleRun = tuple[dict[str, IngestResult], list[EventEnvelope], list[ReadableSpan]]

_DATA = Path(__file__).resolve().parent.parent / "data" / "vantage_robotics"
_SCENARIOS = Path(__file__).resolve().parent.parent / "data" / "scenarios"

_BUNDLE: tuple[tuple[str, Path], ...] = (
    ("contract_meridian_logistics.pdf", _DATA / "contract_meridian_logistics.pdf"),
    ("financials_fy27.xlsx", _DATA / "financials_fy27.xlsx"),
    ("hr_roster_vantage.xlsx", _DATA / "hr_roster_vantage.xlsx"),
    ("tech_inventory.pdf", _DATA / "tech_inventory.pdf"),
    ("vendor_agreement_2027.pdf", _DATA / "vendor_agreement_2027.pdf"),
    ("memo_fleet_operations.docx", _SCENARIOS / "memo_fleet_operations.docx"),
    ("scanned_invoice.pdf", _SCENARIOS / "scanned_invoice.pdf"),
    ("injection_probe.docx", _SCENARIOS / "injection_probe.docx"),
)

_EXPECTED_ROUTES: dict[str, str] = {
    "contract_meridian_logistics.pdf": "legal",
    "financials_fy27.xlsx": "finance",
    "hr_roster_vantage.xlsx": "hr",
    "tech_inventory.pdf": "ip_tech",
    "vendor_agreement_2027.pdf": "legal",
    "memo_fleet_operations.docx": "ip_tech",
}


@pytest.fixture()
def bundle_run(firestore_client: firestore.Client) -> BundleRun:
    publisher = InMemoryPublisher()
    provider, exporter = install_in_memory_exporter("mixed-bundle")
    context = IngestContext(
        client=firestore_client,
        publisher=publisher,
        sentinel=FakeSentinel(),
        classifier=FakeClassifier(),
        tracer=tracer_from(provider),
    )
    results: dict[str, IngestResult] = {}
    for document_id, path in _BUNDLE:
        results[document_id] = ingest_blob(context, "deal-falcon", document_id, path.read_bytes())
    duplicate = ingest_blob(
        context,
        "deal-falcon",
        "contract_meridian_logistics.pdf",
        (_DATA / "contract_meridian_logistics.pdf").read_bytes(),
    )
    results["contract_meridian_logistics.pdf (resubmit)"] = duplicate
    envelopes = [EventEnvelope.from_json(raw) for raw in publisher.published]
    return results, envelopes, list(exporter.get_finished_spans())


class TestMixedBundleGate:
    def test_full_bundle_routes_to_expected_workstreams(self, bundle_run: BundleRun) -> None:
        results, envelopes, _spans = bundle_run
        routed = {
            event.payload["document_id"]: event.payload["workstream"]
            for event in envelopes
            if event.type is EventType.DOCUMENT_ROUTED
        }
        assert routed == _EXPECTED_ROUTES
        for document_id in _EXPECTED_ROUTES:
            assert results[document_id].status == "routed"

    def test_scanned_invoice_honest_needs_ocr_no_route(self, bundle_run: BundleRun) -> None:
        results, envelopes, _spans = bundle_run
        assert results["scanned_invoice.pdf"].status == "needs_ocr"
        assert results["scanned_invoice.pdf"].needs_ocr is True
        parsed = [
            event
            for event in envelopes
            if event.type is EventType.DOCUMENT_PARSED
            and event.payload["document_id"] == "scanned_invoice.pdf"
        ]
        assert len(parsed) == 1
        assert parsed[0].payload["needs_ocr"] is True

    def test_injection_probe_tripwired_never_routed(self, bundle_run: BundleRun) -> None:
        results, envelopes, _spans = bundle_run
        assert results["injection_probe.docx"].status == "tripwired"
        security = [event for event in envelopes if event.type is EventType.SECURITY_EVENT]
        assert len(security) == 1
        assert security[0].payload["document_id"] == "injection_probe.docx"
        assert security[0].payload["reason"] == "injection_tripwire"
        routed_ids = {
            event.payload["document_id"]
            for event in envelopes
            if event.type is EventType.DOCUMENT_ROUTED
        }
        assert "injection_probe.docx" not in routed_ids

    def test_duplicate_contract_suppressed_on_resubmit(self, bundle_run: BundleRun) -> None:
        results, envelopes, _spans = bundle_run
        assert results["contract_meridian_logistics.pdf (resubmit)"].status == "suppressed"
        contract_events = [
            event
            for event in envelopes
            if event.payload.get("document_id") == "contract_meridian_logistics.pdf"
        ]
        assert len(contract_events) == 2, "resubmit must add no events"

    def test_sentinel_model_labeled_in_spans(self, bundle_run: BundleRun) -> None:
        _results, _envelopes, spans = bundle_run
        sentinel_spans = [span for span in spans if span.name == "sentinel.pre_classify"]
        assert len(sentinel_spans) == 7, "every text-bearing doc passes the sentinel"
        for span in sentinel_spans:
            attributes = dict(span.attributes or {})
            assert attributes["gen_ai.system"] == "gemma"
            assert attributes["gen_ai.request.model"] == GEMMA_MODEL_ID
        parse_spans = [span for span in spans if span.name == "ingestion.parse"]
        assert len(parse_spans) == 8
        tripwire_spans = [span for span in spans if span.name == "sentinel.tripwire"]
        assert len(tripwire_spans) == 1
        route_spans = [span for span in spans if span.name == "classifier.route"]
        assert len(route_spans) == 6

    def test_events_recorded_in_canonical_log(
        self, bundle_run: BundleRun, firestore_client: firestore.Client
    ) -> None:
        _results, envelopes, _spans = bundle_run
        assert len(envelopes) == 15
        stored = list(
            firestore_client.collection("deals")
            .document("deal-falcon")
            .collection("events")
            .stream()
        )
        assert len(stored) == 15
        types = sorted(snapshot.to_dict()["type"] for snapshot in stored)
        assert types.count("document.parsed") == 8
        assert types.count("document.routed") == 6
        assert types.count("security.event") == 1
