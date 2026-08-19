"""Human→agent-output authorization tests (BUILD_PLAN D8-M2, vision §7.4).

Even when an agent is permitted to process a document, its output may still be
filtered based on the requesting human's identity:

    Deal Lead            -> all findings, any workstream, any status
    Junior Legal Analyst -> legal findings only; never valuation/finance output
    Outside Counsel      -> selected legal materials only (legal findings
                            approved for external eyes: validated / resolved)
    HR Analyst           -> HR workstream only
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from identity.human_authz import Role, can_view, filter_findings
from memory.findings import Evidence, Finding, FindingSeverity, FindingStatus
from registry.models import Workstream

_NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)

_WORKSTREAMS = list(Workstream)
_STATUSES = list(FindingStatus)
_NON_LEGAL_WORKSTREAMS = [ws for ws in Workstream if ws is not Workstream.LEGAL]


def _finding(
    workstream: Workstream,
    status: FindingStatus,
    finding_id: str,
) -> Finding:
    return Finding(
        finding_id=finding_id,
        deal_id="deal-falcon",
        workstream=workstream,
        title=f"{workstream.value} finding {finding_id}",
        summary=f"Summary for {finding_id}.",
        severity=FindingSeverity.HIGH,
        confidence=0.9,
        status=status,
        evidence=(
            Evidence(
                verbatim_span="quoted span",
                document_id="contract_meridian_logistics.pdf",
            ),
        ),
        owner=f"{workstream.value}-agent@deal-falcon",
        created_at=_NOW,
        updated_at=_NOW,
    )


class TestRoleContract:
    def test_roles_match_the_vision_s74_matrix(self) -> None:
        assert Role.DEAL_LEAD.value == "deal_lead"
        assert Role.JUNIOR_LEGAL.value == "junior_legal"
        assert Role.OUTSIDE_COUNSEL.value == "outside_counsel"
        assert Role.HR_ANALYST.value == "hr_analyst"
        assert len(list(Role)) == 4

    def test_unknown_role_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="intern"):
            Role("intern")


class TestDealLead:
    @pytest.mark.parametrize("workstream", _WORKSTREAMS)
    @pytest.mark.parametrize("status", _STATUSES)
    def test_sees_every_workstream_and_status(
        self, workstream: Workstream, status: FindingStatus
    ) -> None:
        assert can_view(Role.DEAL_LEAD, _finding(workstream, status, "F-001"))


class TestJuniorLegal:
    @pytest.mark.parametrize("status", _STATUSES)
    def test_sees_legal_findings_in_any_status(self, status: FindingStatus) -> None:
        assert can_view(Role.JUNIOR_LEGAL, _finding(Workstream.LEGAL, status, "LEGAL-001"))

    @pytest.mark.parametrize("workstream", _NON_LEGAL_WORKSTREAMS)
    def test_never_sees_valuation_or_other_workstream_output(self, workstream: Workstream) -> None:
        # Vision §7.4: "Junior Legal Analyst -> Legal findings; no valuation model."
        # Finance owns valuation, so finance output is denied along with the rest.
        assert not can_view(Role.JUNIOR_LEGAL, _finding(workstream, FindingStatus.OPEN, "X-001"))


class TestOutsideCounsel:
    @pytest.mark.parametrize("status", [FindingStatus.VALIDATED, FindingStatus.RESOLVED])
    def test_sees_legal_materials_approved_for_external_eyes(self, status: FindingStatus) -> None:
        assert can_view(Role.OUTSIDE_COUNSEL, _finding(Workstream.LEGAL, status, "LEGAL-001"))

    @pytest.mark.parametrize(
        "status",
        [FindingStatus.OPEN, FindingStatus.CANDIDATE, FindingStatus.DISMISSED],
    )
    def test_unapproved_legal_material_is_hidden(self, status: FindingStatus) -> None:
        assert not can_view(Role.OUTSIDE_COUNSEL, _finding(Workstream.LEGAL, status, "LEGAL-001"))

    @pytest.mark.parametrize("workstream", _NON_LEGAL_WORKSTREAMS)
    def test_non_legal_workstreams_are_hidden(self, workstream: Workstream) -> None:
        assert not can_view(
            Role.OUTSIDE_COUNSEL, _finding(workstream, FindingStatus.VALIDATED, "X-001")
        )


class TestHrAnalyst:
    @pytest.mark.parametrize("status", _STATUSES)
    def test_sees_hr_findings_in_any_status(self, status: FindingStatus) -> None:
        assert can_view(Role.HR_ANALYST, _finding(Workstream.HR, status, "HR-001"))

    @pytest.mark.parametrize("workstream", _NON_LEGAL_WORKSTREAMS)
    def test_only_hr_is_visible(self, workstream: Workstream) -> None:
        expected = workstream is Workstream.HR
        assert (
            can_view(Role.HR_ANALYST, _finding(workstream, FindingStatus.OPEN, "X-001")) is expected
        )


class TestFilterFindings:
    def _mixed_fleet(self) -> list[Finding]:
        return [
            _finding(Workstream.FINANCE, FindingStatus.OPEN, "FIN-001"),
            _finding(Workstream.LEGAL, FindingStatus.VALIDATED, "LEGAL-014"),
            _finding(Workstream.HR, FindingStatus.OPEN, "HR-001"),
            _finding(Workstream.LEGAL, FindingStatus.RESOLVED, "LEGAL-021"),
            _finding(Workstream.LEGAL, FindingStatus.OPEN, "SYN-001"),
            _finding(Workstream.IP_TECH, FindingStatus.CANDIDATE, "IP-001"),
        ]

    def test_filter_preserves_order_and_applies_the_matrix(self) -> None:
        fleet = self._mixed_fleet()

        def seen(role: Role) -> list[str]:
            return [f.finding_id for f in filter_findings(fleet, role)]

        assert seen(Role.DEAL_LEAD) == [
            "FIN-001",
            "LEGAL-014",
            "HR-001",
            "LEGAL-021",
            "SYN-001",
            "IP-001",
        ]
        assert seen(Role.JUNIOR_LEGAL) == ["LEGAL-014", "LEGAL-021", "SYN-001"]
        assert seen(Role.OUTSIDE_COUNSEL) == ["LEGAL-014", "LEGAL-021"]
        assert seen(Role.HR_ANALYST) == ["HR-001"]

    def test_empty_fleet_stays_empty(self) -> None:
        assert filter_findings([], Role.DEAL_LEAD) == []


class _DtoItem:
    """Minimal workstream+status payload (e.g. an API row, not a stored finding)."""

    def __init__(self, workstream: Workstream, status: FindingStatus) -> None:
        self.workstream = workstream
        self.status = status


class TestViewableProtocol:
    def test_filters_any_workstream_status_payload_not_just_stored_findings(self) -> None:
        items = [
            _DtoItem(Workstream.LEGAL, FindingStatus.VALIDATED),
            _DtoItem(Workstream.HR, FindingStatus.OPEN),
            _DtoItem(Workstream.LEGAL, FindingStatus.OPEN),
        ]
        assert filter_findings(items, Role.JUNIOR_LEGAL) == [items[0], items[2]]
        assert filter_findings(items, Role.OUTSIDE_COUNSEL) == [items[0]]
