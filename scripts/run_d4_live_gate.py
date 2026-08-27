"""Day-4 live evidence window runner (BUILD_PLAN D4-M8, scenario S7).

Runs the mixed bundle through the REAL pipeline â€” hosted Gemma sentinel +
gemini-3.5-flash classifier (location=global) â€” with spans exported to Cloud
Trace, guarded write-only: refuses without --confirm-live, refuses under the
emulator, refuses with an incomplete env contract. Events land in the deal's
canonical Firestore event log. See docs/deal_provisioning.md (Day-4 appendix).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_BUNDLE: tuple[tuple[str, str], ...] = (
    ("contract_meridian_logistics.pdf", "data/vantage_robotics/contract_meridian_logistics.pdf"),
    ("financials_fy27.xlsx", "data/vantage_robotics/financials_fy27.xlsx"),
    ("hr_roster_vantage.xlsx", "data/vantage_robotics/hr_roster_vantage.xlsx"),
    ("tech_inventory.pdf", "data/vantage_robotics/tech_inventory.pdf"),
    ("vendor_agreement_2027.pdf", "data/vantage_robotics/vendor_agreement_2027.pdf"),
    ("memo_fleet_operations.docx", "data/scenarios/memo_fleet_operations.docx"),
    ("scanned_invoice.pdf", "data/scenarios/scanned_invoice.pdf"),
    ("injection_probe.docx", "data/scenarios/injection_probe.docx"),
)

_REQUIRED_ENV: tuple[str, ...] = (
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "DILIGENCE_FLASH_CLASSIFIER_ENABLED",
    "DILIGENCE_GEMMA_ENABLED",
    "GOOGLE_API_KEY",
)


def required_env(offline_sentinel: bool = False) -> tuple[str, ...]:
    if offline_sentinel:
        return tuple(
            name
            for name in _REQUIRED_ENV
            if name not in ("GOOGLE_API_KEY", "DILIGENCE_GEMMA_ENABLED")
        )
    return _REQUIRED_ENV


def validate_live_env(offline_sentinel: bool = False) -> tuple[str, ...]:
    return tuple(name for name in required_env(offline_sentinel) if not os.environ.get(name))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Day-4 live gate: mixed bundle through Flash + Gemma with Cloud Trace."
    )
    parser.add_argument("--deal-id", required=True)
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="required: run against real GCP (models, Firestore, Cloud Trace)",
    )
    parser.add_argument(
        "--offline-sentinel",
        action="store_true",
        help=(
            "red path: sentinel tier on the deterministic fake when the Gemini "
            "Developer API key is unavailable (disclosed in the evidence file)"
        ),
    )
    args = parser.parse_args(argv)

    if not args.confirm_live:
        print("Refusing: pass --confirm-live to open the Day-4 live window.", file=sys.stderr)
        sys.exit(1)
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        print(
            "Refusing: FIRESTORE_EMULATOR_HOST is set; live window targets real GCP.",
            file=sys.stderr,
        )
        sys.exit(1)
    missing = validate_live_env(offline_sentinel=args.offline_sentinel)
    if missing:
        print("Refusing: missing live-window env: " + ", ".join(missing), file=sys.stderr)
        sys.exit(1)

    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

    from ingestion.classifier import FlashClassifier
    from ingestion.pipeline import IngestContext, ingest_blob
    from ingestion.sentinel import FakeSentinel, GemmaSentinel, SentinelModel
    from memory.db import make_client
    from observability.tracing import setup_tracing, tracer_from
    from runtime.events import InMemoryPublisher

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    # The gcp-trace exporter ships untyped; behavior is exercised in the live window.
    exporter = CloudTraceSpanExporter(project_id=project)  # type: ignore[no-untyped-call]
    provider = setup_tracing(service_name="diligence-room-day4-live", exporter=exporter)
    sentinel: SentinelModel
    if args.offline_sentinel:
        sentinel = FakeSentinel()
        print(
            "sentinel_mode=fake (RED PATH: Gemini Developer API rejected the "
            "project-created API key with API_KEY_INVALID; disclosed in evidence)"
        )
    else:
        sentinel = GemmaSentinel()
        print("sentinel_mode=gemma-live (hosted Gemini Developer API)")
    context = IngestContext(
        client=make_client(project),
        publisher=InMemoryPublisher(),
        sentinel=sentinel,
        classifier=FlashClassifier(),
        tracer=tracer_from(provider),
    )
    bucket = f"diligence-room-dataroom-{args.deal_id}-us"

    print(f"deal={args.deal_id} project={project} bundle={len(_BUNDLE)} documents")
    for document_id, relative in _BUNDLE:
        blob = (_ROOT / relative).read_bytes()
        result = ingest_blob(context, args.deal_id, document_id, blob, bucket=bucket)
        route = result.route
        workstream = route.workstream if route is not None else "-"
        doc_type = route.doc_type if route is not None else "-"
        print(
            f"{document_id}: status={result.status} workstream={workstream} "
            f"doc_type={doc_type} dlp_required={result.dlp_required} "
            f"needs_ocr={result.needs_ocr} events={len(result.events)}"
        )

    provider.shutdown()
    print(f"trace-console: https://console.cloud.google.com/traces/list?project={project}")
    print(f"events: gcloud firestore query deals/{args.deal_id}/events (15 expected)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
