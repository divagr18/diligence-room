"""Red-team runner (BUILD_PLAN D7-M4, vision §13).

Feeds every committed attack fixture through the full ingestion pipeline and
scores the outcome against ``redteam/expected.yaml``: one row per fixture, plus
the §13 Security Test Suite scorecard grouped by attack class. A fixture passes
only when it is blocked before routing, at the ledger-declared screening layer,
with the declared reason visible in the security event.

Each run scopes its document registrations under a run nonce so replays of the
suite never collapse into lineage suppression.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml
from google.cloud import firestore

from ingestion.classifier import FakeClassifier
from ingestion.pipeline import (
    STATUS_QUARANTINED,
    STATUS_TRIPWIRED,
    IngestContext,
    ingest_blob,
)
from ingestion.sentinel import FakeSentinel
from runtime.events import EventType, InMemoryPublisher

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_ATTACKS_ROOT = _REPO_ROOT / "redteam" / "attacks"
_DEFAULT_EXPECTED = _REPO_ROOT / "redteam" / "expected.yaml"
_DEFAULT_DEAL: Final[str] = "deal-redteam"

_GROUP_BY_CLASS: Final[Mapping[str, str]] = {
    "injection": "injection",
    "exfiltration": "exfiltration",
    "cross_ws": "cross_ws",
    "poisoning": "poisoning_cross_deal",
    "cross_deal": "poisoning_cross_deal",
}
_CANONICAL_GROUPS: Final[tuple[str, ...]] = (
    "injection",
    "exfiltration",
    "cross_ws",
    "poisoning_cross_deal",
)
_BOARD_LABELS: Final[Mapping[str, str]] = {
    "injection": "Prompt Injection",
    "exfiltration": "Exfiltration",
    "cross_ws": "Cross-Workstream Leak",
    "poisoning_cross_deal": "Tool Poisoning / Cross-Deal",
}
_BLOCKED_STATUSES: Final[frozenset[str]] = frozenset({STATUS_TRIPWIRED, STATUS_QUARANTINED})


@dataclass(frozen=True, slots=True)
class RedteamRow:
    """Result of one attack fixture run through the pipeline."""

    path: str
    attack_class: str
    expected_layer: str
    expected_reason: str
    actual_status: str
    actual_layer: str | None
    reasons_seen: tuple[str, ...]
    blocked: bool
    passed: bool


@dataclass(frozen=True, slots=True)
class RedteamReport:
    """All fixture rows for one run, plus derived totals."""

    rows: tuple[RedteamRow, ...]
    deal_id: str

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def blocked(self) -> int:
        return sum(1 for row in self.rows if row.blocked)

    @property
    def all_passed(self) -> bool:
        return all(row.passed for row in self.rows)

    @property
    def scorecard(self) -> dict[str, tuple[int, int]]:
        tallies: dict[str, list[int]] = {}
        for row in self.rows:
            group = _GROUP_BY_CLASS[row.attack_class]
            blocked_count, total = tallies.get(group, [0, 0])
            tallies[group] = [blocked_count + (1 if row.blocked else 0), total + 1]
        return {
            group: (tallies[group][0], tallies[group][1])
            for group in _CANONICAL_GROUPS
            if group in tallies
        }


def _reasons_from_security_events(result_events: object) -> tuple[str, ...]:
    reasons: list[str] = []
    events = result_events if isinstance(result_events, tuple) else ()
    for event in events:
        if event.type is not EventType.SECURITY_EVENT:
            continue
        for key in ("patterns", "reason_codes"):
            value = event.payload.get(key)
            if isinstance(value, list):
                reasons.extend(str(item) for item in value)
    return tuple(reasons)


def run_redteam(
    client: firestore.Client,
    *,
    deal_id: str = _DEFAULT_DEAL,
    run_id: str | None = None,
    attacks_root: Path = _DEFAULT_ATTACKS_ROOT,
    expected_path: Path = _DEFAULT_EXPECTED,
) -> RedteamReport:
    """Run every ledger fixture through the pipeline; score vs expected.yaml."""
    nonce = run_id if run_id is not None else uuid.uuid4().hex[:8]
    data = yaml.safe_load(expected_path.read_text(encoding="utf-8"))
    fixtures = data["fixtures"]
    assert isinstance(fixtures, list)
    publisher = InMemoryPublisher()
    rows: list[RedteamRow] = []
    for fixture in fixtures:
        relative = str(fixture["path"])
        blob = (attacks_root / relative).read_bytes()
        document_id = f"rt-{nonce}__{relative.replace('/', '_')}"
        context = IngestContext(
            client=client,
            publisher=publisher,
            sentinel=FakeSentinel(),
            classifier=FakeClassifier(),
        )
        result = ingest_blob(context, deal_id, document_id, blob)
        blocked = result.route is None and result.status in _BLOCKED_STATUSES
        if result.status == STATUS_TRIPWIRED:
            actual_layer: str | None = "sentinel_tripwire"
        elif result.status == STATUS_QUARANTINED:
            actual_layer = "model_armor"
        else:
            actual_layer = None
        reasons_seen = _reasons_from_security_events(result.events)
        expected_layer = str(fixture["layer"])
        expected_reason = str(fixture["reason"])
        passed = blocked and actual_layer == expected_layer and expected_reason in reasons_seen
        rows.append(
            RedteamRow(
                path=relative,
                attack_class=str(fixture["attack_class"]),
                expected_layer=expected_layer,
                expected_reason=expected_reason,
                actual_status=result.status,
                actual_layer=actual_layer,
                reasons_seen=reasons_seen,
                blocked=blocked,
                passed=passed,
            )
        )
    return RedteamReport(rows=tuple(rows), deal_id=deal_id)


def attack_class_of(document_id: str) -> str | None:
    """Recover the ledger attack class from a document id, if it is a fixture.

    Runs register documents as ``rt-{nonce}__{path}`` with ``/`` flattened to
    ``_``; documents outside the ledger (e.g. dataset files quarantined by the
    same store) yield ``None``.
    """
    flattened = document_id.split("__", 1)[-1]
    for attack_class in _GROUP_BY_CLASS:
        if flattened.startswith(f"{attack_class}_"):
            return attack_class
    return None


def render_report(report: RedteamReport) -> str:
    """Render fixture rows plus the §13 scorecard board."""
    lines = [
        f"RED-TEAM LEDGER - deal {report.deal_id}: {report.blocked}/{report.total} blocked",
        "",
    ]
    for row in report.rows:
        verdict = "PASS" if row.passed else "FAIL"
        layer = row.actual_layer if row.actual_layer is not None else "-"
        reasons = ",".join(row.reasons_seen) if row.reasons_seen else "-"
        lines.append(
            f"{row.path:<52} {row.attack_class:<14} {row.actual_status:<12} "
            f"{layer:<18} {verdict:<4} {reasons}"
        )
    lines.append("")
    lines.append("Security Test Suite")
    scorecard = report.scorecard
    for group in _CANONICAL_GROUPS:
        if group not in scorecard:
            continue
        blocked_count, total = scorecard[group]
        lines.append(f"{_BOARD_LABELS[group]:<28}{blocked_count}/{total} blocked")
    lines.append(f"{'TOTAL':<28}{report.blocked}/{report.total} blocked")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the red-team attack ledger through the ingestion pipeline."
    )
    parser.add_argument("--deal-id", default=_DEFAULT_DEAL)
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="run against real GCP Firestore instead of the emulator",
    )
    args = parser.parse_args(argv)

    def refuse(message: str) -> int:
        print(message, file=sys.stderr)
        sys.exit(1)

    emulator = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if not emulator and not args.confirm_live:
        return refuse(
            "Refusing: set FIRESTORE_EMULATOR_HOST for an offline run, or pass "
            "--confirm-live to target real GCP."
        )
    if emulator and args.confirm_live:
        return refuse("Refusing: FIRESTORE_EMULATOR_HOST is set; --confirm-live targets real GCP.")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    if args.confirm_live and not project:
        return refuse("Refusing: live run requires GOOGLE_CLOUD_PROJECT.")

    client = firestore.Client(project=project) if project else firestore.Client()
    report = run_redteam(client, deal_id=args.deal_id)
    print(render_report(report))
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
