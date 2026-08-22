"""Stage instrumentation tests (BUILD_PLAN D10-M2, vision §7.7).

Every meaningful stage — armor screen, agent tool executions, gateway
decisions, coordinator synthesis, negotiation transitions — emits a span
through an injected tracer with the attributes the Security/Trace views need.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from google.cloud import firestore
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agents.coordinator.synthesize import synthesize_critical
from agents.fleet import run_workstream_offline
from agents.negotiation.drafts import (
    NegotiationArtifactKind,
    approve_draft,
    generate_draft,
    record_send,
    submit_for_approval,
)
from agents.tools.data_room_read import DatasetDocSource, make_data_room_read
from agents.tools.finding_create import make_finding_create
from gateway.decide import GatewayRequest, decide
from gateway.policy import PolicyStore
from identity.principals import principal_for
from ingestion.chunking import chunk
from ingestion.classifier import FakeClassifier
from ingestion.parsing import LocalParser
from ingestion.pipeline import IngestContext, ingest_blob
from ingestion.sentinel import FakeSentinel
from observability.tracing import install_in_memory_exporter, stage_span, tracer_from
from registry.models import Workstream
from runtime.events import InMemoryPublisher

DEAL = "deal-falcon"
_NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
_DEEP = (Workstream.LEGAL, Workstream.FINANCE, Workstream.HR, Workstream.IP_TECH)


def _spans(exporter: InMemorySpanExporter, name: str) -> list[ReadableSpan]:
    return [span for span in exporter.get_finished_spans() if span.name == name]


def _attrs(span: ReadableSpan) -> dict[str, object]:
    attributes = span.attributes
    return dict(attributes) if attributes is not None else {}


def _contract_coc_span() -> str:
    blob = DatasetDocSource().read("contract_meridian_logistics.pdf")
    assert blob is not None
    parsed = LocalParser().parse(blob, "contract_meridian_logistics.pdf", DEAL)
    return next(c.text for c in chunk(parsed) if c.locator == "clause:11.3")


def _finding_json() -> dict[str, object]:
    return {
        "title": "Stage-probe CoC termination right",
        "summary": (
            "The Meridian agreement grants a termination right within 90 days of change of control."
        ),
        "severity": "high",
        "confidence": 0.9,
        "evidence": [
            {
                "verbatim_span": _contract_coc_span(),
                "document_id": "contract_meridian_logistics.pdf",
                "category": "contracts",
                "chunk_ref": "clause:11.3",
            }
        ],
        "source_documents": ["contract_meridian_logistics.pdf"],
        "affected_entities": ["Meridian Logistics, Inc."],
        "questions": [],
    }


class TestStageSpanHelper:
    def test_none_tracer_yields_none_and_emits_nothing(self) -> None:
        _, exporter = install_in_memory_exporter("none-stage")
        with stage_span(None, "never.emitted") as span:
            assert span is None
        assert exporter.get_finished_spans() == ()

    def test_tracer_opens_the_span_with_attributes(self) -> None:
        provider, exporter = install_in_memory_exporter("attr-stage")
        with stage_span(tracer_from(provider), "stage.probe", stage="armor", blocked=True) as span:
            assert span is not None
        attributes = _attrs(exporter.get_finished_spans()[0])
        assert attributes["stage"] == "armor"
        assert attributes["blocked"] is True


class TestArmorScreenSpan:
    def test_armored_document_emits_screen_span(self, firestore_client: firestore.Client) -> None:
        provider, exporter = install_in_memory_exporter("ingest-stage")
        context = IngestContext(
            client=firestore_client,
            publisher=InMemoryPublisher(),
            sentinel=FakeSentinel(),
            classifier=FakeClassifier(),
            tracer=tracer_from(provider),
        )
        blob = (Path("redteam") / "attacks" / "injection" / "authority_forgery_a.pdf").read_bytes()
        result = ingest_blob(context, "deal-redteam", "stage-probe.pdf", blob)
        assert result.status == "quarantined"
        spans = _spans(exporter, "armor.screen")
        assert len(spans) == 1
        attributes = _attrs(spans[0])
        assert attributes["armor.blocked"] is True
        assert int(str(attributes["armor.rule_count"])) >= 1


class TestAgentToolSpans:
    def test_data_room_read_emits_agent_tool_span(self, firestore_client: firestore.Client) -> None:
        provider, exporter = install_in_memory_exporter("tool-stage")
        principal = principal_for(Workstream.LEGAL, DEAL)
        reader = make_data_room_read(
            principal, InMemoryPublisher(), DatasetDocSource(), tracer=tracer_from(provider)
        )
        result = reader(category="contracts", name="contract_meridian_logistics.pdf")
        assert result["decision"] == "allow"
        spans = _spans(exporter, "agent.tool")
        assert len(spans) == 1
        attributes = _attrs(spans[0])
        assert attributes["agent.tool"] == "data_room_read"
        assert attributes["agent.principal"] == principal.name
        assert attributes["agent.workstream"] == Workstream.LEGAL.value
        assert attributes["agent.decision"] == "allow"

    def test_finding_create_emits_agent_tool_span(self, firestore_client: firestore.Client) -> None:
        provider, exporter = install_in_memory_exporter("tool-stage-2")
        principal = principal_for(Workstream.LEGAL, DEAL)
        tool = make_finding_create(
            principal, firestore_client, DatasetDocSource(), tracer=tracer_from(provider)
        )
        result = tool(finding_json=json.dumps(_finding_json()))
        assert result["decision"] == "created"
        spans = _spans(exporter, "agent.tool")
        assert len(spans) == 1
        attributes = _attrs(spans[0])
        assert attributes["agent.tool"] == "finding_create"
        assert attributes["agent.decision"] == "created"


class TestGatewaySpan:
    def test_allow_decision_emits_gateway_span(self, firestore_client: firestore.Client) -> None:
        PolicyStore(firestore_client).seed_defaults(DEAL)
        provider, exporter = install_in_memory_exporter("gateway-stage")
        request = GatewayRequest(
            request_id="req-stage",
            deal_id=DEAL,
            sender=principal_for(Workstream.LEGAL, DEAL),
            target_workstream=Workstream.FINANCE,
            question="What share of projected revenue comes from Meridian Logistics?",
            purpose="revenue_concentration",
            ts=_NOW,
        )
        decision = decide(firestore_client, request, tracer=tracer_from(provider))
        assert decision.verdict.value == "allow"
        spans = _spans(exporter, "gateway.decide")
        assert len(spans) == 1
        attributes = _attrs(spans[0])
        assert attributes["gateway.verdict"] == "allow"
        assert attributes["gateway.reason"] == decision.reason.value


class TestCoordinatorSpan:
    def test_accepted_synthesis_emits_coordinator_span(
        self, firestore_client: firestore.Client
    ) -> None:
        for workstream in _DEEP:
            run_workstream_offline(firestore_client, DEAL, workstream, now=_NOW)
        provider, exporter = install_in_memory_exporter("coordinator-stage")
        finding_id = synthesize_critical(
            firestore_client,
            DEAL,
            publisher=InMemoryPublisher(),
            now=_NOW,
            tracer=tracer_from(provider),
        )
        assert finding_id is not None
        spans = _spans(exporter, "coordinator.synthesize")
        assert len(spans) == 1
        attributes = _attrs(spans[0])
        assert attributes["coordinator.accepted"] is True
        assert attributes["coordinator.contributors"] == 4
        assert attributes["coordinator.entity"] == "Meridian Logistics, Inc."

    def test_refused_synthesis_marks_the_span_not_accepted(
        self, firestore_client: firestore.Client
    ) -> None:
        run_workstream_offline(firestore_client, DEAL, Workstream.LEGAL, now=_NOW)
        provider, exporter = install_in_memory_exporter("coordinator-stage-2")
        finding_id = synthesize_critical(
            firestore_client, DEAL, now=_NOW, tracer=tracer_from(provider)
        )
        assert finding_id is None
        spans = _spans(exporter, "coordinator.synthesize")
        assert len(spans) == 1
        assert _attrs(spans[0])["coordinator.accepted"] is False


class TestNegotiationSpans:
    def test_full_chain_emits_one_span_per_transition(
        self, firestore_client: firestore.Client
    ) -> None:
        tool = make_finding_create(
            principal_for(Workstream.LEGAL, DEAL), firestore_client, DatasetDocSource()
        )
        finding_id = str(tool(finding_json=json.dumps(_finding_json()))["finding_id"])
        provider, exporter = install_in_memory_exporter("negotiation-stage")
        tracer = tracer_from(provider)
        draft = generate_draft(
            firestore_client, DEAL, finding_id, NegotiationArtifactKind.REDLINE, tracer=tracer
        )
        submit_for_approval(firestore_client, DEAL, draft.draft_id, tracer=tracer)
        approve_draft(
            firestore_client, DEAL, draft.draft_id, approver="deal-lead@human", tracer=tracer
        )
        record_send(firestore_client, DEAL, draft.draft_id, tracer=tracer)
        spans = _spans(exporter, "negotiation.transition")
        assert len(spans) == 4
        to_states = [str(_attrs(span)["negotiation.to_state"]) for span in spans]
        assert to_states == ["draft", "pending_approval", "approved", "send_logged"]
