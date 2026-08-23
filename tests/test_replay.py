"""Accelerated-clock replay engine tests (BUILD_PLAN D13-M2, vision §16).

The replay drives the **real** pipeline against the Firestore emulator: the
only mock anywhere in these tests is the pacing clock (``sleep`` is a no-op —
the accelerated clock compresses the 14-day timeline instead of spending it).
Ingestion, sentinel tripwire, Model Armor rules, the evidence-gated finding
path, coordinator synthesis, the registry, and the negotiation state machine
all run genuine.

Covered: one complete replay finishes <4 min wall-clock; two runs with the
same seed are deterministic (same run_id, same events_injected, byte-equal
finding sets); the run_id is stamped into the trace spans; every event type
left real side effects (quarantine, lineage chain, golden finding titles,
registry rollback, send-logged negotiation).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from google.cloud import firestore
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agents.negotiation.store import NegotiationState, NegotiationStore
from armor.quarantine import QuarantineStore
from evals.golden_set import GOLDEN_SET
from ingestion.lineage import get_record
from memory.findings import Finding, FindingSeverity, FindingsStore
from registry.models import Workstream
from registry.seed import SEED_MANIFESTS
from registry.store import AgentRegistryStore
from runtime.replay import ReplayConfig, ReplayReport, derive_run_id, run_replay

DEAL_ID = "deal-falcon"
SCENARIO_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "scenarios" / "project_falcon.json"
)
WALL_CLOCK_BUDGET_S = 240.0
EXPECTED_EVENTS = (
    49  # 19 uploads + 4 findings + 20 attacks + amendment/upgrade/rollback + 3 negotiation
)
EXPECTED_FINDINGS = 5  # four keystone findings + one coordinator synthesis


def _noop_sleep(_seconds: float) -> None:
    """Mocked accelerated clock: pacing is compressed, processing is real."""


def _fresh_client() -> firestore.Client:
    """One pristine deal namespace per replay run (emulator host is set by
    the session-scoped ``firestore_emulator`` fixture)."""
    return firestore.Client(project=f"replay-{uuid.uuid4().hex[:12]}")


def _run_replay(
    client: firestore.Client, exporter: InMemorySpanExporter | None = None
) -> ReplayReport:
    return run_replay(
        ReplayConfig(scenario_path=SCENARIO_PATH, speed=1000, client=client),
        sleep=_noop_sleep,
        span_exporter=exporter,
    )


def _all_findings(client: firestore.Client) -> list[Finding]:
    return [
        finding
        for workstream in Workstream
        for finding in FindingsStore(client).list_for_workstream(DEAL_ID, workstream)
    ]


@dataclass(frozen=True, slots=True)
class ReplayRun:
    client: firestore.Client
    exporter: InMemorySpanExporter
    report: ReplayReport
    wall_s: float


@pytest.fixture(scope="module")
def replay_run(firestore_emulator: str) -> ReplayRun:
    client = _fresh_client()
    exporter = InMemorySpanExporter()
    started = time.monotonic()
    report = _run_replay(client, exporter)
    return ReplayRun(client, exporter, report, time.monotonic() - started)


class TestReplayRun:
    def test_full_replay_finishes_under_four_minutes(self, replay_run: ReplayRun) -> None:
        assert replay_run.wall_s < WALL_CLOCK_BUDGET_S
        report = replay_run.report
        assert report.duration_s < WALL_CLOCK_BUDGET_S
        assert report.events_injected == EXPECTED_EVENTS
        assert report.findings_created == EXPECTED_FINDINGS
        assert report.run_id == derive_run_id(42)
        assert report.deterministic is True

    def test_run_id_is_stamped_into_trace_spans(self, replay_run: ReplayRun) -> None:
        spans = replay_run.exporter.get_finished_spans()
        assert spans
        stamped = [
            span
            for span in spans
            if span.attributes and span.attributes.get("replay.run_id") == replay_run.report.run_id
        ]
        assert stamped
        names = {span.name for span in spans}
        assert {"replay.run", "replay.event"} <= names
        # Genuine pipeline spans ran under the replay spans: one shared trace.
        assert {"ingestion.parse", "classifier.route", "armor.screen"} <= names
        assert len({span.context.trace_id for span in spans}) == 1

    def test_all_events_process_genuinely(self, replay_run: ReplayRun) -> None:
        client = replay_run.client

        # 20 attack fixtures quarantined by genuine screening layers.
        quarantined = QuarantineStore(client).list_quarantined(DEAL_ID)
        assert len(quarantined) == 20
        assert {record.layer for record in quarantined} == {"sentinel_tripwire", "model_armor"}

        # Amendment continues the vendor-agreement chain: update, not duplicate.
        amendment = get_record(client, DEAL_ID, "amendment_2030.pdf")
        vendor = get_record(client, DEAL_ID, "vendor_agreement_2027.pdf")
        assert amendment is not None and vendor is not None
        assert amendment.supersedes == "vendor_agreement_2027.pdf"
        assert amendment.version == 2
        assert vendor.version == 1

        # Four keystone findings carry the golden titles; synthesis is critical.
        findings = _all_findings(client)
        assert len(findings) == EXPECTED_FINDINGS
        titles = {finding.title for finding in findings}
        keystone_titles = {
            doc.expected_finding_titles[0] for doc in GOLDEN_SET if doc.expected_finding_titles
        }
        assert keystone_titles <= titles
        synthesis = [f for f in findings if f.severity is FindingSeverity.CRITICAL]
        assert len(synthesis) == 1
        assert len(synthesis[0].related_findings) == 4

        # Registry beat: legal upgraded to 2.5.0, then rolled back approved.
        legal_seed = next(m for m in SEED_MANIFESTS if m.agent_id == "legal")
        manifest = AgentRegistryStore(client).get_manifest("legal")
        assert manifest.version == legal_seed.version
        assert manifest.approved is True
        assert manifest.rollback_target == "2.5.0"

        # Negotiation lifecycle ends send-logged behind the human approval.
        legal_keystone = next(
            f
            for f in findings
            if f.workstream is Workstream.LEGAL and f.severity is FindingSeverity.HIGH
        )
        drafts = NegotiationStore(client).list_for_finding(DEAL_ID, legal_keystone.finding_id)
        assert len(drafts) == 1
        assert drafts[0].state is NegotiationState.SEND_LOGGED
        assert drafts[0].approved_by == "deal-lead"


class TestReplayDeterminism:
    def test_two_runs_with_same_seed_are_deterministic(self, firestore_emulator: str) -> None:
        reports: list[ReplayReport] = []
        finding_sets: list[list[tuple[str, str, str, str, float, str]]] = []
        for _ in range(2):
            client = _fresh_client()
            reports.append(_run_replay(client))
            finding_sets.append(
                sorted(
                    (
                        f.finding_id,
                        f.title,
                        f.severity.value,
                        f.workstream.value,
                        f.confidence,
                        f.status.value,
                    )
                    for f in _all_findings(client)
                )
            )
        assert reports[0].run_id == reports[1].run_id
        assert reports[0].events_injected == reports[1].events_injected == EXPECTED_EVENTS
        assert reports[0].findings_created == reports[1].findings_created == EXPECTED_FINDINGS
        assert finding_sets[0] == finding_sets[1]
        assert len(finding_sets[0]) == EXPECTED_FINDINGS


class TestReplayConfig:
    def test_config_rejects_non_positive_speed(self) -> None:
        with pytest.raises(ValueError, match="speed"):
            ReplayConfig(scenario_path=SCENARIO_PATH, speed=0)

    def test_run_id_derives_from_seed_alone(self) -> None:
        assert derive_run_id(42) == derive_run_id(42)
        assert derive_run_id(42) != derive_run_id(7)
