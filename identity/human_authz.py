"""Human→agent-output authorization (BUILD_PLAN D8-M2, vision §7.4).

Even when an agent is permitted to process a document, its output may still be
filtered based on the requesting human's identity. Roles mirror vision §7.4:

    Deal Lead            -> every finding: any workstream, any status
                            (executive view of the whole fleet)
    Junior Legal Analyst -> legal findings in any status; valuation/finance
                            output is never visible to this role
    Outside Counsel      -> selected legal materials only: legal findings that
                            have been approved for external eyes
                            (validated / resolved)
    HR Analyst           -> HR workstream only
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Final, Protocol, TypeVar

from memory.findings import FindingStatus
from registry.models import Workstream


class Role(StrEnum):
    DEAL_LEAD = "deal_lead"
    JUNIOR_LEGAL = "junior_legal"
    OUTSIDE_COUNSEL = "outside_counsel"
    HR_ANALYST = "hr_analyst"


class Viewable(Protocol):
    """Anything carrying a workstream + status can be visibility-filtered."""

    @property
    def workstream(self) -> Workstream:
        """Workstream that produced the item."""

    @property
    def status(self) -> FindingStatus:
        """Lifecycle status of the item."""


_ViewableT = TypeVar("_ViewableT", bound=Viewable)


# None means "no workstream restriction" (deal lead sees everything).
_VISIBLE_WORKSTREAMS: Final[Mapping[Role, frozenset[Workstream] | None]] = {
    Role.DEAL_LEAD: None,
    Role.JUNIOR_LEGAL: frozenset({Workstream.LEGAL}),
    Role.OUTSIDE_COUNSEL: frozenset({Workstream.LEGAL}),
    Role.HR_ANALYST: frozenset({Workstream.HR}),
}

# Legal materials approved for eyes outside the deal team.
_EXTERNAL_STATUSES: Final[frozenset[FindingStatus]] = frozenset(
    {FindingStatus.VALIDATED, FindingStatus.RESOLVED}
)

# None means "no status restriction".
_STATUS_GATE: Final[Mapping[Role, frozenset[FindingStatus] | None]] = {
    Role.DEAL_LEAD: None,
    Role.JUNIOR_LEGAL: None,
    Role.OUTSIDE_COUNSEL: _EXTERNAL_STATUSES,
    Role.HR_ANALYST: None,
}


def can_view(role: Role, item: Viewable) -> bool:
    """Decide whether *role* may see *item* (workstream scope + status gate)."""
    workstreams = _VISIBLE_WORKSTREAMS[role]
    if workstreams is not None and item.workstream not in workstreams:
        return False
    statuses = _STATUS_GATE[role]
    return statuses is None or item.status in statuses


def filter_findings(items: Iterable[_ViewableT], role: Role) -> list[_ViewableT]:
    """Keep only the findings *role* may see, preserving input order."""
    return [item for item in items if can_view(role, item)]
