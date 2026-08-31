"""Red-team scorecard aggregation (BUILD_PLAN D12-M5, vision §13).

Folds one ledger run (``redteam.runner.run_redteam``) into the Security view's
scorecard groups, using the runner's §13 grouping (`injection`, `exfiltration`,
`cross_ws`, `poisoning_cross_deal`). Numbers are reported as-is — a fixture
that evades screening counts against the blocked tally (7/8 stays 7/8, never
smoothed).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Final

import yaml
from google.cloud import firestore

from armor.quarantine import QuarantineRecord, QuarantineStore
from redteam.runner import (
    _BOARD_LABELS,
    _CANONICAL_GROUPS,
    _DEFAULT_EXPECTED,
    _GROUP_BY_CLASS,
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


# --------------------------------------------------------------------------
# Read-only scoring
# --------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _ledger() -> tuple[tuple[str, str, str], ...]:
    """The static attack ledger as ``(flattened_path, attack_class, layer)``.

    ``expected.yaml`` is checked in and never changes at runtime, so the totals
    a scorecard reports come from here rather than from whatever happens to be
    in Firestore.
    """
    data = yaml.safe_load(_DEFAULT_EXPECTED.read_text(encoding="utf-8"))
    return tuple(
        (str(f["path"]).replace("/", "_"), str(f["attack_class"]), str(f["layer"]))
        for f in data["fixtures"]
    )


def latest_run_id(records: Iterable[QuarantineRecord]) -> str | None:
    """The ``rt-{nonce}`` prefix of the most recently quarantined fixture."""
    newest: tuple[datetime, str] | None = None
    for record in records:
        if "__" not in record.document_id:
            continue
        prefix = record.document_id.split("__", 1)[0]
        if newest is None or record.ts > newest[0]:
            newest = (record.ts, prefix)
    return None if newest is None else newest[1]


def read_scorecard(
    client: firestore.Client, deal_id: str = DEFAULT_DEAL
) -> tuple[SecurityScorecard, list[QuarantineRecord]]:
    """Score the most recent red-team run from stored quarantine records.

    This is the request path's scorecard. ``build_scorecard`` re-runs the whole
    ledger through the ingestion pipeline, which writes quarantine records and
    takes over a minute; doing that on a GET made the Security view slower on
    every load, because each render left twenty more records behind for the
    next one to read.

    Totals still come from the ledger, so a fixture that evades screening is
    counted as not blocked rather than quietly dropped from the denominator.
    Returns the scorecard together with just this run's records, so the view
    shows one run instead of every run ever made against the deal.
    """
    records = QuarantineStore(client).list_quarantined(deal_id)
    run_id = latest_run_id(records)
    if run_id is None:
        return SecurityScorecard(), []
    this_run = [r for r in records if r.document_id.startswith(f"{run_id}__")]
    by_name = {r.document_id.split("__", 1)[1]: r for r in this_run}

    tallies: dict[str, list[int]] = {group: [0, 0] for group in _CANONICAL_GROUPS}
    for flattened, attack_class, expected_layer in _ledger():
        group = _GROUP_BY_CLASS[attack_class]
        tallies[group][1] += 1
        record = by_name.get(flattened)
        if record is not None and record.layer == expected_layer:
            tallies[group][0] += 1
    return (
        SecurityScorecard(
            injection=(tallies["injection"][0], tallies["injection"][1]),
            exfiltration=(tallies["exfiltration"][0], tallies["exfiltration"][1]),
            cross_ws=(tallies["cross_ws"][0], tallies["cross_ws"][1]),
            poisoning_cross_deal=(
                tallies["poisoning_cross_deal"][0],
                tallies["poisoning_cross_deal"][1],
            ),
        ),
        sorted(this_run, key=lambda r: r.ts),
    )
