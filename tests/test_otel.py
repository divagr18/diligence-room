"""OTel backbone tests (BUILD_PLAN D10-M1, vision §7.7)."""

from __future__ import annotations

import sys

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from observability.otel import ServiceName, build_provider, trace_id_of
from observability.tracing import tracer_from


class TestServiceNames:
    def test_every_component_has_a_stable_service_name(self) -> None:
        assert ServiceName.INGESTION_PIPELINE.value == "diligence-room-ingestion"
        assert ServiceName.GATEWAY.value == "diligence-room-gateway"
        assert ServiceName.COORDINATOR.value == "diligence-room-coordinator"
        assert ServiceName.NEGOTIATION.value == "diligence-room-negotiation"
        assert ServiceName.DASHBOARD_API.value == "diligence-room-dashboard-api"
        assert ServiceName.REDTEAM_RUNNER.value == "diligence-room-redteam-runner"


class TestBuildProvider:
    def test_offline_provider_carries_the_service_name(self) -> None:
        provider = build_provider(ServiceName.GATEWAY)
        assert provider.resource.attributes["service.name"] == "diligence-room-gateway"

    def test_providers_are_isolated_per_call(self) -> None:
        assert build_provider(ServiceName.GATEWAY) is not build_provider(ServiceName.GATEWAY)

    def test_offline_build_never_imports_the_cloud_trace_exporter(self) -> None:
        sys.modules.pop("opentelemetry.exporter.cloud_trace", None)
        build_provider(ServiceName.INGESTION_PIPELINE)
        assert "opentelemetry.exporter.cloud_trace" not in sys.modules

    def test_live_seam_batches_into_the_injected_exporter(self) -> None:
        exporter = InMemorySpanExporter()
        provider = build_provider(ServiceName.COORDINATOR, live=True, exporter=exporter)
        with tracer_from(provider).start_as_current_span("probe"):
            pass
        provider.force_flush()
        spans = list(exporter.get_finished_spans())
        assert [span.name for span in spans] == ["probe"]

    def test_trace_id_is_32_lowercase_hex_matching_the_span_context(self) -> None:
        exporter = InMemorySpanExporter()
        provider = build_provider(ServiceName.REDTEAM_RUNNER, live=True, exporter=exporter)
        with tracer_from(provider).start_as_current_span("probe") as span:
            trace_id = trace_id_of(span)
        provider.force_flush()
        assert len(trace_id) == 32
        assert all(char in "0123456789abcdef" for char in trace_id)
        exported = list(exporter.get_finished_spans())[0]
        assert trace_id == format(exported.context.trace_id, "032x")
