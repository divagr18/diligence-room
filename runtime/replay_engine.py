"""Scenario event injection into the real pipeline (BUILD_PLAN D13-M2).

Internal engine behind ``runtime.replay.run_replay``: one ``inject`` call per
scenario event, wrapped in a ``replay.event`` span stamped with the run id.
Every event type drives genuine machinery — ``ingest_blob`` for corpus
uploads, attack fixtures, and the amendment; the evidence-gated offline fleet
producers plus a coordinator synthesis attempt for findings;
``link_supersedes`` for the amendment chain (update, not duplicate); the
agent registry for upgrade/rollback; and the approval state machine for
negotiation. No processing here is simulated.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from google.cloud import firestore
from opentelemetry.trace import Tracer

from agents.coordinator.synthesize import synthesize_critical
from agents.fleet import run_workstream_offline
from agents.negotiation.drafts import (
    approve_draft,
    generate_draft,
    record_send,
    submit_for_approval,
)
from agents.negotiation.store import NegotiationArtifactKind, NegotiationState
from agents.tools.data_room_read import DatasetDocSource
from evals.golden_set import golden_path
from ingestion.classifier import FakeClassifier
from ingestion.lineage import link_supersedes
from ingestion.pipeline import IngestContext, ingest_blob
from ingestion.sentinel import FakeSentinel
from observability.tracing import stage_span
from registry.models import AgentVersion, Workstream
from registry.seed import seed_registry
from registry.store import AgentRegistryStore
from runtime.deal_workspace import FALCON_DEAL_ID, build_falcon_deal, provision_deal
from runtime.events import InMemoryPublisher

_ATTACKS_ROOT: Final = Path(__file__).resolve().parent.parent / "redteam" / "attacks"


def _payload_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"scenario payload key {key!r} must be a non-empty string")
    return value


class ReplayEngine:
    """Injects sorted scenario events into the real pipeline, one span each.

    Internal to ``runtime.replay`` — constructed by ``run_replay`` with the
    run's client, deal namespace, tracer, and seed-derived run id.
    """

    def __init__(self, client: firestore.Client, deal_id: str, tracer: Tracer, run_id: str) -> None:
        self._client = client
        self._deal_id = deal_id
        self._tracer = tracer
        self._run_id = run_id
        self._publisher = InMemoryPublisher()
        self._doc_source = DatasetDocSource()
        self._registry = AgentRegistryStore(client)
        self._context = IngestContext(
            client=client,
            publisher=self._publisher,
            sentinel=FakeSentinel(),
            classifier=FakeClassifier(),
            tracer=tracer,
        )
        self._finding_by_scenario_id: dict[str, str] = {}
        self._draft_ids: dict[tuple[str, str], str] = {}
        self._synthesis_ids: set[str] = set()
        self.findings_created = 0
        self.events_injected = 0

    def prepare(self, base_ts: datetime) -> None:
        """Seed the registry and provision the falcon deal when absent."""
        seed_registry(self._registry, now=base_ts)
        if self._deal_id != FALCON_DEAL_ID:
            return
        ref = self._client.collection("deals").document(FALCON_DEAL_ID)
        if not ref.get().exists:
            provision_deal(self._client, build_falcon_deal(base_ts))

    def inject(self, event: Mapping[str, Any], stamp: datetime) -> None:
        event_type = str(event["type"])
        payload = event["payload"]
        if not isinstance(payload, dict):
            raise ValueError(f"event {event_type!r} payload must be a JSON object")
        span_attributes: dict[str, str | int | float | bool] = {
            "replay.run_id": self._run_id,
            "replay.event.type": event_type,
            "replay.day": int(event["day"]),
            "replay.ts": str(event["ts"]),
        }
        with stage_span(self._tracer, "replay.event", links=None, **span_attributes):
            match event_type:
                case "upload":
                    self._upload(payload)
                case "attack":
                    self._attack(payload)
                case "finding":
                    self._finding(payload, stamp)
                case "amendment":
                    self._amendment(payload)
                case "upgrade":
                    self._upgrade(payload, stamp)
                case "rollback":
                    self._rollback(payload)
                case "negotiation":
                    self._negotiation(payload, stamp)
                case _:
                    raise ValueError(f"unknown scenario event type {event_type!r}")
        self.events_injected += 1

    def _ingest(self, document_id: str, blob: bytes) -> None:
        ingest_blob(self._context, self._deal_id, document_id, blob)

    def _upload(self, payload: Mapping[str, Any]) -> None:
        doc_id = _payload_str(payload, "doc_id")
        self._ingest(doc_id, golden_path(doc_id).read_bytes())

    def _attack(self, payload: Mapping[str, Any]) -> None:
        fixture = _payload_str(payload, "fixture")
        document_id = f"rt-{self._run_id}__{fixture.replace('/', '_')}"
        self._ingest(document_id, (_ATTACKS_ROOT / fixture).read_bytes())

    def _finding(self, payload: Mapping[str, Any], stamp: datetime) -> None:
        workstream = Workstream(_payload_str(payload, "workstream"))
        finding_id = run_workstream_offline(
            self._client, self._deal_id, workstream, doc_source=self._doc_source, now=stamp
        )
        self._finding_by_scenario_id[_payload_str(payload, "finding_id")] = finding_id
        self.findings_created += 1
        # The coordinator attempts after every contributor lands; it refuses
        # until all four converge, then writes the escalating critical finding.
        synthesis_id = synthesize_critical(
            self._client,
            self._deal_id,
            publisher=self._publisher,
            doc_source=self._doc_source,
            now=stamp,
            tracer=self._tracer,
        )
        if synthesis_id is not None and synthesis_id not in self._synthesis_ids:
            self._synthesis_ids.add(synthesis_id)
            self.findings_created += 1

    def _amendment(self, payload: Mapping[str, Any]) -> None:
        doc_id = _payload_str(payload, "doc_id")
        self._ingest(doc_id, golden_path(doc_id).read_bytes())
        supersedes = payload.get("supersedes")
        if isinstance(supersedes, str) and supersedes:
            link_supersedes(self._client, self._deal_id, doc_id, supersedes)

    def _upgrade(self, payload: Mapping[str, Any], stamp: datetime) -> None:
        agent_id = _payload_str(payload, "agent_id")
        prior = self._registry.get_version(agent_id, _payload_str(payload, "from_version"))
        self._registry.publish_version(
            agent_id,
            AgentVersion(
                version=_payload_str(payload, "to_version"),
                model_id=prior.model_id,
                prompt_ref=prior.prompt_ref,
                created_at=stamp,
                rollback_target=prior.version,
                changelog="replay scenario upgrade",
            ),
        )

    def _rollback(self, payload: Mapping[str, Any]) -> None:
        self._registry.rollback(
            _payload_str(payload, "agent_id"), _payload_str(payload, "to_version")
        )

    def _negotiation(self, payload: Mapping[str, Any], stamp: datetime) -> None:
        kind = NegotiationArtifactKind(_payload_str(payload, "kind"))
        finding_id = self._finding_by_scenario_id[_payload_str(payload, "finding_id")]
        state = NegotiationState(_payload_str(payload, "state"))
        if state is NegotiationState.DRAFT:
            draft = generate_draft(
                self._client,
                self._deal_id,
                finding_id,
                kind,
                publisher=self._publisher,
                now=stamp,
                tracer=self._tracer,
            )
            self._draft_ids[(finding_id, kind.value)] = draft.draft_id
            return
        draft_id = self._draft_ids[(finding_id, kind.value)]
        if state is NegotiationState.APPROVED:
            submit_for_approval(
                self._client,
                self._deal_id,
                draft_id,
                publisher=self._publisher,
                now=stamp,
                tracer=self._tracer,
            )
            approve_draft(
                self._client,
                self._deal_id,
                draft_id,
                _payload_str(payload, "approved_by"),
                publisher=self._publisher,
                now=stamp,
                tracer=self._tracer,
            )
        elif state is NegotiationState.SEND_LOGGED:
            record_send(
                self._client,
                self._deal_id,
                draft_id,
                publisher=self._publisher,
                now=stamp,
                tracer=self._tracer,
            )
        else:
            raise ValueError(f"replay never injects state {state.value!r} directly")
