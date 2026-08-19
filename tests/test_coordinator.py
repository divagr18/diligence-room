"""Coordinator keystone tests (BUILD_PLAN D8-M3, vision §6).

The CRITICAL finding must emerge ONLY from multi-workstream synthesis. Remove
any single contributing deep workstream and the synthesis refuses; tamper with
an inherited evidence span and the synthesis refuses. The coordinator
aggregates the deep-four findings, inherits their verified evidence, and
escalates the result — it never fabricates a span.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from google.cloud import firestore

from agents.coordinator.synthesize import synthesize_critical
from agents.fleet import run_workstream_offline
from coordination.scoring import ScoringContext, score_finding
from memory.findings import (
    Evidence,
    Finding,
    FindingSeverity,
    FindingsStore,
    FindingStatus,
)
from registry.models import Workstream
from runtime.events import EventEnvelope, EventType, InMemoryPublisher

_DEAL = "deal-falcon"
_NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
_MERIDIAN = "Meridian Logistics, Inc."
_DEEP = (Workstream.LEGAL, Workstream.FINANCE, Workstream.HR, Workstream.IP_TECH)


def _seed_deep_four(client: firestore.Client) -> list[str]:
    return [run_workstream_offline(client, _DEAL, ws, now=_NOW) for ws in _DEEP]


def _all_findings(client: firestore.Client) -> list[Finding]:
    store = FindingsStore(client)
    out: list[Finding] = []
    for ws in Workstream:
        out.extend(store.list_for_workstream(_DEAL, ws))
    return out


class TestKeystoneSynthesis:
    def test_all_four_workstreams_yield_a_critical_finding(
        self, firestore_client: firestore.Client
    ) -> None:
        contributor_ids = _seed_deep_four(firestore_client)
        publisher = InMemoryPublisher()
        finding_id = synthesize_critical(firestore_client, _DEAL, publisher=publisher, now=_NOW)

        assert finding_id is not None
        finding = FindingsStore(firestore_client).get(_DEAL, finding_id)
        assert finding.severity is FindingSeverity.CRITICAL
        assert finding.affected_entities == (_MERIDIAN,)
        assert set(contributor_ids) <= set(finding.related_findings)

        # Evidence is inherited from the four contributors, nothing invented.
        store = FindingsStore(firestore_client)
        contributor_spans = {
            e.verbatim_span for cid in contributor_ids for e in store.get(_DEAL, cid).evidence
        }
        assert {e.verbatim_span for e in finding.evidence} == contributor_spans
        assert len(finding.evidence) == len(contributor_ids)

    def test_synthesis_escalates_and_logs_the_finding(
        self, firestore_client: firestore.Client
    ) -> None:
        _seed_deep_four(firestore_client)
        publisher = InMemoryPublisher()
        finding_id = synthesize_critical(firestore_client, _DEAL, publisher=publisher, now=_NOW)
        assert finding_id is not None

        types = {EventEnvelope.from_json(p).type for p in publisher.published}
        assert EventType.FINDING_CREATED in types
        assert EventType.FINDING_ESCALATED in types

        inbox = (
            firestore_client.collection("deals")
            .document(_DEAL)
            .collection("inbox")
            .document(finding_id)
            .get()
        )
        assert inbox.to_dict() is not None
        assert inbox.to_dict()["severity"] == FindingSeverity.CRITICAL.value

    def test_synthesis_scores_critical_under_red_flag_engine(
        self, firestore_client: firestore.Client
    ) -> None:
        _seed_deep_four(firestore_client)
        finding_id = synthesize_critical(firestore_client, _DEAL, now=_NOW)
        assert finding_id is not None
        finding = FindingsStore(firestore_client).get(_DEAL, finding_id)
        flag = score_finding(
            finding,
            ScoringContext(financial_exposure_pct=18.3, affected_workstreams=len(_DEEP)),
        )
        assert flag.level.value == FindingSeverity.CRITICAL.value


class TestRemovalProof:
    @pytest.mark.parametrize("dropped", _DEEP)
    def test_removing_any_single_workstream_refuses_synthesis(
        self, firestore_client: firestore.Client, dropped: Workstream
    ) -> None:
        for ws in _DEEP:
            if ws is not dropped:
                run_workstream_offline(firestore_client, _DEAL, ws, now=_NOW)

        assert synthesize_critical(firestore_client, _DEAL, now=_NOW) is None
        assert all(
            f.severity is not FindingSeverity.CRITICAL for f in _all_findings(firestore_client)
        )

    def test_no_findings_at_all_refuses_synthesis(self, firestore_client: firestore.Client) -> None:
        assert synthesize_critical(firestore_client, _DEAL, now=_NOW) is None


class TestIntegrityAndIdempotency:
    def test_tampered_evidence_span_refuses_synthesis(
        self, firestore_client: firestore.Client
    ) -> None:
        _seed_deep_four(firestore_client)
        store = FindingsStore(firestore_client)
        legal = store.list_for_workstream(_DEAL, Workstream.LEGAL)[0]
        tampered = Finding(
            finding_id=legal.finding_id,
            deal_id=_DEAL,
            workstream=Workstream.LEGAL,
            title=legal.title,
            summary=legal.summary,
            severity=legal.severity,
            confidence=legal.confidence,
            status=FindingStatus.OPEN,
            evidence=(
                Evidence(
                    verbatim_span="a fabricated span present in no document",
                    document_id="contract_meridian_logistics.pdf",
                ),
            ),
            owner=legal.owner,
            created_at=legal.created_at,
            updated_at=legal.updated_at,
            affected_entities=(_MERIDIAN,),
        )
        store.update(tampered)
        assert synthesize_critical(firestore_client, _DEAL, now=_NOW) is None

    def test_rerun_is_idempotent_and_does_not_duplicate(
        self, firestore_client: firestore.Client
    ) -> None:
        _seed_deep_four(firestore_client)
        first = synthesize_critical(firestore_client, _DEAL, now=_NOW)
        second = synthesize_critical(firestore_client, _DEAL, now=_NOW)
        assert first is not None
        assert first == second
        critical = [
            f for f in _all_findings(firestore_client) if f.severity is FindingSeverity.CRITICAL
        ]
        assert len(critical) == 1
