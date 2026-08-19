"""Red-flag scoring engine tests (BUILD_PLAN D8-M1, vision §10).

The scoring engine is deterministic and severity-loyal: without escalation
context (financial exposure, regulatory implications, multi-workstream blast
radius, unresolved duration, dependency impact) a finding keeps its own
severity as the red-flag level; escalation context can raise the level, but
never more than one step above the finding's severity. Vision §10 canonical
example: Legal HIGH + 18.3% exposure + 0.94 confidence + Legal and Finance
affected => CRITICAL — and Legal alone stays HIGH.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coordination.scoring import (
    RedFlag,
    RedFlagLevel,
    ScoringContext,
    score_finding,
)
from memory.findings import Evidence, Finding, FindingSeverity, FindingStatus
from registry.models import Workstream

_NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _finding(
    severity: FindingSeverity = FindingSeverity.HIGH,
    confidence: float = 0.9,
    evidence_count: int = 1,
) -> Finding:
    return Finding(
        finding_id="scoring-test",
        deal_id="deal-falcon",
        workstream=Workstream.LEGAL,
        title="Change-of-control termination right",
        summary="Section 11.3 grants either party a termination right.",
        severity=severity,
        confidence=confidence,
        status=FindingStatus.OPEN,
        evidence=tuple(
            Evidence(
                verbatim_span=f"span {i}",
                document_id="contract_meridian_logistics.pdf",
            )
            for i in range(evidence_count)
        ),
        owner="legal-agent@deal-falcon",
        created_at=_NOW,
        updated_at=_NOW,
    )


class TestVisionCanonicalExample:
    def test_legal_plus_finance_blast_radius_is_critical(self) -> None:
        flag = score_finding(
            _finding(severity=FindingSeverity.HIGH, confidence=0.94),
            ScoringContext(financial_exposure_pct=18.3, affected_workstreams=2),
        )
        assert flag.level is RedFlagLevel.CRITICAL
        assert flag.score >= 90.0

    def test_single_workstream_stays_high(self) -> None:
        flag = score_finding(
            _finding(severity=FindingSeverity.HIGH, confidence=0.94),
            ScoringContext(financial_exposure_pct=18.3, affected_workstreams=1),
        )
        assert flag.level is RedFlagLevel.HIGH


class TestSeverityLoyalty:
    @pytest.mark.parametrize("severity", list(FindingSeverity))
    def test_without_escalation_context_level_matches_severity(
        self, severity: FindingSeverity
    ) -> None:
        flag = score_finding(_finding(severity=severity, confidence=0.9))
        assert flag.level is RedFlagLevel(severity.value)

    def test_default_context_is_loyal_for_high(self) -> None:
        flag = score_finding(_finding())
        assert flag.level is RedFlagLevel.HIGH


class TestCeiling:
    def test_medium_severity_cannot_reach_critical(self) -> None:
        flag = score_finding(
            _finding(severity=FindingSeverity.MEDIUM, confidence=0.9, evidence_count=3),
            ScoringContext(
                financial_exposure_pct=45.0,
                regulatory_implicated=True,
                affected_workstreams=4,
                unresolved_days=12.0,
                dependency_impacted=True,
            ),
        )
        assert flag.level is RedFlagLevel.HIGH
        assert flag.score >= 90.0


class TestMonotonicity:
    def test_higher_confidence_never_lowers_score(self) -> None:
        ctx = ScoringContext(financial_exposure_pct=18.3, affected_workstreams=2)
        low = score_finding(_finding(confidence=0.5), ctx)
        high = score_finding(_finding(confidence=0.95), ctx)
        assert high.score >= low.score

    def test_more_exposure_never_lowers_score(self) -> None:
        less = score_finding(_finding(), ScoringContext(financial_exposure_pct=5.0))
        more = score_finding(_finding(), ScoringContext(financial_exposure_pct=18.3))
        assert more.score >= less.score

    def test_wider_blast_radius_never_lowers_score(self) -> None:
        narrow = score_finding(
            _finding(),
            ScoringContext(financial_exposure_pct=10.0, affected_workstreams=1),
        )
        wide = score_finding(
            _finding(),
            ScoringContext(financial_exposure_pct=10.0, affected_workstreams=4),
        )
        assert wide.score >= narrow.score

    def test_longer_unresolved_duration_never_lowers_score(self) -> None:
        fresh = score_finding(_finding(), ScoringContext(financial_exposure_pct=10.0))
        stale = score_finding(
            _finding(),
            ScoringContext(financial_exposure_pct=10.0, unresolved_days=14.0),
        )
        assert stale.score >= fresh.score


class TestDeterminism:
    def test_same_input_twice_is_identical(self) -> None:
        ctx = ScoringContext(
            financial_exposure_pct=18.3,
            affected_workstreams=2,
            regulatory_implicated=True,
        )
        first = score_finding(_finding(), ctx)
        second = score_finding(_finding(), ctx)
        assert first == second
        assert isinstance(first, RedFlag)

    def test_rationale_names_severity_and_level(self) -> None:
        flag = score_finding(
            _finding(severity=FindingSeverity.HIGH, confidence=0.94),
            ScoringContext(financial_exposure_pct=18.3, affected_workstreams=2),
        )
        assert "high" in flag.rationale
        assert flag.level.value in flag.rationale


class TestEvidenceQuality:
    def test_more_verified_evidence_raises_score_with_cap(self) -> None:
        ctx = ScoringContext(financial_exposure_pct=18.3, affected_workstreams=2)
        one = score_finding(_finding(evidence_count=1), ctx)
        three = score_finding(_finding(evidence_count=3), ctx)
        five = score_finding(_finding(evidence_count=5), ctx)
        assert three.score > one.score
        assert five.score == three.score


class TestValidation:
    def test_negative_exposure_rejected(self) -> None:
        with pytest.raises(ValueError, match="financial_exposure"):
            ScoringContext(financial_exposure_pct=-1.0)

    def test_zero_workstreams_rejected(self) -> None:
        with pytest.raises(ValueError, match="workstreams"):
            ScoringContext(affected_workstreams=0)

    def test_negative_duration_rejected(self) -> None:
        with pytest.raises(ValueError, match="unresolved"):
            ScoringContext(unresolved_days=-0.5)
