"""Red-team scorecard aggregation (BUILD_PLAN D12-M5, vision §13).

Folds one ledger run (``redteam.runner.run_redteam``) into the Security view's
scorecard groups, using the runner's §13 grouping (`injection`, `exfiltration`,
`cross_ws`, `poisoning_cross_deal`). Numbers are reported as-is — a fixture
that evades screening counts against the blocked tally (7/8 stays 7/8, never
smoothed).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from google.cloud import firestore

from redteam.runner import (
    _BOARD_LABELS,
    _CANONICAL_GROUPS,
    RedteamReport,
    run_redteam,
)

DEFAULT_DEAL: Final[str] = "deal-falcon"
GROUPS: Final[tuple[str, ...]] = _CANONICAL_GROUPS
GROUP_LABELS: Final[Mapping[str, str]] = _BOARD_LABELS


@dataclass(frozen=True, slots=True)
class SecurityScorecard:
    """Blocked/total tallies per §13 group for one red-team run."""

    injection: tuple[int, int] = (0, 0)
    exfiltration: tuple[int, int] = (0, 0)
    cross_ws: tuple[int, int] = (0, 0)
    poisoning_cross_deal: tuple[int, int] = (0, 0)

    @property
    def groups(self) -> Mapping[str, tuple[int, int]]:
        """Non-empty group tallies in canonical board order."""
        tallies = {
            "injection": self.injection,
            "exfiltration": self.exfiltration,
            "cross_ws": self.cross_ws,
            "poisoning_cross_deal": self.poisoning_cross_deal,
        }
        return {group: tallies[group] for group in _CANONICAL_GROUPS if tallies[group][1] > 0}

    @property
    def total(self) -> tuple[int, int]:
        """``(blocked, total)`` across every group."""
        tallies = (self.injection, self.exfiltration, self.cross_ws, self.poisoning_cross_deal)
        return (sum(tally[0] for tally in tallies), sum(tally[1] for tally in tallies))


def aggregate_scorecard(report: RedteamReport) -> SecurityScorecard:
    """Fold one run's rows into §13 group tallies (honest counts, no smoothing)."""
    tallies = report.scorecard
    return SecurityScorecard(
        injection=tallies.get("injection", (0, 0)),
        exfiltration=tallies.get("exfiltration", (0, 0)),
        cross_ws=tallies.get("cross_ws", (0, 0)),
        poisoning_cross_deal=tallies.get("poisoning_cross_deal", (0, 0)),
    )


def build_scorecard(client: firestore.Client, deal_id: str = DEFAULT_DEAL) -> SecurityScorecard:
    """Run the attack ledger for ``deal_id`` and aggregate the §13 scorecard."""
    return aggregate_scorecard(run_redteam(client, deal_id=deal_id))
