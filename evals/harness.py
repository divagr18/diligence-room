"""Shadow eval harness — candidate-vs-baseline diff (BUILD_PLAN D12-M2).

Runs the four deep workstreams over ``DEEP_WORKSTREAM_DOCUMENTS`` through the
same evidence-gated ``finding_create`` path the live fleet uses
(``agents.fleet.run_workstream_offline``), then diffs the ``FindingsStore``
results against ``GOLDEN_SET`` strict-exact (plan §11): title + severity +
affected_entities.

- ``missing``    — golden docs whose pinned finding is absent (the pinned
  title is not present, or is present with different affected entities)
- ``downgraded`` — pinned findings that surfaced below their pinned severity
- ``new``        — findings with titles no golden doc pins
- ``passed``     — no pinned finding missing or downgraded (a regression per
  plan §1; extra titles are reported but do not gate)

Deterministic by construction: the caller supplies an offline emulator
client, the run stamps findings with a fixed ``HARNESS_NOW``, results are
title-sorted before diffing, and no network or live LLM call is made
(doctrine §1).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, TypeAlias

from google.cloud import firestore

from agents.fleet import (
    DEEP_WORKSTREAM_DOCUMENTS,
    WorkstreamFact,
    extract_fact,
    run_workstream_offline,
)
from evals.golden_set import GOLDEN_SET, GoldenDoc
from ingestion.models import ParsedDoc
from memory.findings import Finding, FindingSeverity, FindingsStore
from registry.models import Workstream

Extractor: TypeAlias = Callable[[Workstream, ParsedDoc], WorkstreamFact]

#: Fixed stamp for harness findings so reruns diff identically.
HARNESS_NOW: Final = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)

_SEVERITY_RANK: Final[Mapping[FindingSeverity, int]] = {
    severity: rank for rank, severity in enumerate(FindingSeverity)
}


@dataclass(frozen=True, slots=True)
class HarnessReport:
    """Candidate-vs-golden diff; ``passed`` gates on missing + downgraded."""

    missing: tuple[GoldenDoc, ...]
    downgraded: tuple[Finding, ...]
    new: tuple[Finding, ...]
    passed: bool


def diff_against_golden(findings: Sequence[Finding]) -> HarnessReport:
    """Diff produced findings against ``GOLDEN_SET`` strict-exact.

    A pinned finding matches only on exact title AND exact affected_entities;
    a match below its pinned severity is downgraded, an absent or
    entity-divergent pin is missing, and any unpinned title is new.
    """
    pinned_titles = {title for doc in GOLDEN_SET for title in doc.expected_finding_titles}
    missing: list[GoldenDoc] = []
    downgraded: list[Finding] = []
    for doc in GOLDEN_SET:
        if not doc.expected_finding_titles:
            continue
        pinned_severity = doc.expected_severity
        doc_missing = False
        for title in doc.expected_finding_titles:
            matches = [
                finding
                for finding in findings
                if finding.title == title and finding.affected_entities == doc.expected_entities
            ]
            if not matches:
                doc_missing = True
                continue
            if pinned_severity is not None:
                downgraded.extend(
                    finding
                    for finding in matches
                    if _SEVERITY_RANK[finding.severity] < _SEVERITY_RANK[pinned_severity]
                )
        if doc_missing:
            missing.append(doc)
    return HarnessReport(
        missing=tuple(missing),
        downgraded=tuple(downgraded),
        new=tuple(finding for finding in findings if finding.title not in pinned_titles),
        passed=not missing and not downgraded,
    )


def run_harness(
    client: firestore.Client,
    deal_id: str,
    extractor: Extractor | None = None,
    *,
    now: datetime = HARNESS_NOW,
) -> HarnessReport:
    """Run the four deep workstreams as *extractor* and diff against the golden set.

    ``extractor=None`` runs the baseline fleet producers; any candidate
    extractor swaps in through the identical ``finding_create`` write path.
    The client must target the offline emulator — the harness never makes a
    network or live LLM call.
    """
    extract = extractor if extractor is not None else extract_fact
    for workstream in DEEP_WORKSTREAM_DOCUMENTS:
        run_workstream_offline(client, deal_id, workstream, extractor=extract, now=now)
    store = FindingsStore(client)
    findings = sorted(
        (
            finding
            for workstream in DEEP_WORKSTREAM_DOCUMENTS
            for finding in store.list_for_workstream(deal_id, workstream)
        ),
        key=lambda finding: finding.title,
    )
    return diff_against_golden(findings)
