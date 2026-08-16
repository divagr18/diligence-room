"""Tracing span-helper tests (vision §7.7; Day-4 phase exit, scenario S6)."""

from __future__ import annotations

from observability.tracing import (
    install_in_memory_exporter,
    parse_span,
    route_span,
    sentinel_span,
    set_genai_attributes,
    tracer_from,
    tripwire_span,
)

_FAKE_MODEL = "gemma-4-26b-a4b-it"


def _spans(exporter: object) -> list[object]:
    spans = exporter.get_finished_spans()  # type: ignore[attr-defined]
    return list(spans)


def _span_by_name(exporter: object, name: str) -> object:
    matches = [span for span in _spans(exporter) if span.name == name]  # type: ignore[attr-defined]
    assert matches, f"span {name!r} not captured"
    return matches[0]


def _attributes(span: object) -> dict[str, object]:
    return dict(span.attributes)  # type: ignore[attr-defined]


class TestSpans:
    def test_parse_span_emitted_with_name(self) -> None:
        provider, exporter = install_in_memory_exporter()
        with parse_span(tracer_from(provider)):
            pass
        assert _span_by_name(exporter, "ingestion.parse")

    def test_sentinel_span_carries_genai_system_and_model(self) -> None:
        provider, exporter = install_in_memory_exporter()
        with sentinel_span(tracer_from(provider), decision="clear", model=_FAKE_MODEL):
            pass
        attributes = _attributes(_span_by_name(exporter, "sentinel.pre_classify"))
        assert attributes["gen_ai.system"] == "gemma"
        assert attributes["gen_ai.request.model"] == _FAKE_MODEL
        assert attributes["sentinel.decision"] == "clear"

    def test_tripwire_span_name(self) -> None:
        provider, exporter = install_in_memory_exporter()
        with tripwire_span(tracer_from(provider)):
            pass
        assert _span_by_name(exporter, "sentinel.tripwire")

    def test_route_span_carries_workstream_attribute(self) -> None:
        provider, exporter = install_in_memory_exporter()
        tracer = tracer_from(provider)
        with route_span(tracer, workstream="legal"):
            pass
        with route_span(tracer, workstream=None):
            pass
        routes = [span for span in _spans(exporter) if span.name == "classifier.route"]  # type: ignore[attr-defined]
        assert len(routes) == 2
        assert _attributes(routes[0])["route.workstream"] == "legal"
        assert _attributes(routes[1])["route.workstream"] == "unrouted"

    def test_in_memory_exporter_sees_sentinel_model_label(self) -> None:
        provider, exporter = install_in_memory_exporter("ingest-window")
        with sentinel_span(tracer_from(provider), decision="tripwire", model=_FAKE_MODEL):
            pass
        labels = [_attributes(span).get("gen_ai.request.model") for span in _spans(exporter)]
        assert _FAKE_MODEL in labels

    def test_providers_isolated_between_setups(self) -> None:
        provider_a, exporter_a = install_in_memory_exporter("svc-a")
        provider_b, exporter_b = install_in_memory_exporter("svc-b")
        assert provider_a is not provider_b
        with parse_span(tracer_from(provider_a)):
            pass
        assert _spans(exporter_a)
        assert not _spans(exporter_b)

    def test_set_genai_attributes_appends_extras(self) -> None:
        provider, exporter = install_in_memory_exporter()
        with tracer_from(provider).start_as_current_span("custom") as span:
            set_genai_attributes(span, system="gemma", model=_FAKE_MODEL, pii_count=2)
        assert _attributes(_span_by_name(exporter, "custom"))["pii_count"] == 2
