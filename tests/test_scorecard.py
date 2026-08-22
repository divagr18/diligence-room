"""Red-team scorecard tests (BUILD_PLAN D12-M5, vision §13).

The scorecard aggregates one attack-ledger run into the Security Test Suite
board groups. Numbers stay honest: the 20-fixture ledger folds into 8/5/4/3
(total 20/20), and a fixture that evaded screening counts against the blocked
tally (7/8 stays 7/8 — never smoothed).
"""

from __future__ import annotations

from google.cloud import firestore

from redteam.runner import RedteamReport, RedteamRow
from redteam.scorecard import (
    DEFAULT_DEAL,
    GROUP_LABELS,
    GROUPS,
    SecurityScorecard,
    aggregate_scorecard,
    build_scorecard,
)


def _injection_row(path: str, *, blocked: bool) -> RedteamRow:
    return RedteamRow(
        path=path,
        attack_class="injection",
        expected_layer="sentinel_tripwire",
        expected_reason="ignore_instructions",
        actual_status="tripwired" if blocked else "routed",
        actual_layer="sentinel_tripwire" if blocked else None,
        reasons_seen=("ignore_instructions",) if blocked else (),
        blocked=blocked,
        passed=blocked,
    )


class TestBuildScorecard:
    def test_ledger_20_folds_into_board_groups(self, firestore_client: firestore.Client) -> None:
        scorecard = build_scorecard(firestore_client)
        assert scorecard.injection == (8, 8)
        assert scorecard.exfiltration == (5, 5)
        assert scorecard.cross_ws == (4, 4)
        assert scorecard.poisoning_cross_deal == (3, 3)
        assert scorecard.total == (20, 20)
        assert scorecard.groups == {
            "injection": (8, 8),
            "exfiltration": (5, 5),
            "cross_ws": (4, 4),
            "poisoning_cross_deal": (3, 3),
        }

    def test_default_deal_is_the_dashboard_deal(self) -> None:
        assert DEFAULT_DEAL == "deal-falcon"


class TestAggregateScorecard:
    def test_failed_row_counts_honestly(self) -> None:
        rows = tuple(
            _injection_row(f"injection/fixture_{index}.pdf", blocked=True) for index in range(7)
        )
        rows += (_injection_row("injection/rogue.pdf", blocked=False),)
        scorecard = aggregate_scorecard(RedteamReport(rows=rows, deal_id="deal-x"))
        assert scorecard.injection == (7, 8)
        assert scorecard.total == (7, 8)
        assert scorecard.groups == {"injection": (7, 8)}
        assert scorecard.exfiltration == (0, 0)

    def test_empty_report_is_all_zero(self) -> None:
        scorecard = aggregate_scorecard(RedteamReport(rows=(), deal_id="deal-x"))
        assert scorecard == SecurityScorecard()
        assert scorecard.groups == {}
        assert scorecard.total == (0, 0)


class TestGroupExports:
    def test_every_group_has_a_board_label(self) -> None:
        assert set(GROUP_LABELS) == set(GROUPS)
