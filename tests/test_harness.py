"""Shadow-harness tests (BUILD_PLAN D12-M2).

The baseline fleet passes the golden diff; the Legal v2.5 RED candidate fails
with exactly one missing pinned doc (the CoC contract) while the weakened
finding surfaces as an unpinned extra; a synthetic severity downgrade is
reported as downgraded, and an upgrade is not a regression. Adjacent surface:
``tests/test_golden_set.py`` stays green against the same corpus.
"""

from __future__ import annotations

from dataclasses import replace

from google.cloud import firestore

from agents.fleet import DEEP_WORKSTREAM_DOCUMENTS, WorkstreamFact, extract_fact
from evals.golden_set import golden_doc
from evals.harness import Extractor, run_harness
from evals.legal_v25 import legal_v25_extract_fact
from ingestion.models import ParsedDoc
from memory.findings import FindingSeverity, FindingsStore
from registry.models import Workstream

DEAL = "deal-harness"
COC_DOC_ID = "contract_meridian_logistics.pdf"


def _with_finance_severity(severity: FindingSeverity) -> Extractor:
    """Synthetic candidate: baseline everywhere, finance re-severitized."""

    def extract(workstream: Workstream, parsed: ParsedDoc) -> WorkstreamFact:
        fact = extract_fact(workstream, parsed)
        if workstream is Workstream.FINANCE:
            return replace(fact, severity=severity.value)
        return fact

    return extract


class TestBaselineRun:
    def test_baseline_fleet_passes_the_golden_diff(
        self, firestore_client: firestore.Client
    ) -> None:
        report = run_harness(firestore_client, DEAL)
        assert report.passed is True
        assert report.missing == ()
        assert report.downgraded == ()
        assert report.new == ()

    def test_baseline_writes_one_pinned_finding_per_deep_workstream(
        self, firestore_client: firestore.Client
    ) -> None:
        run_harness(firestore_client, DEAL)
        store = FindingsStore(firestore_client)
        for workstream, doc_id in DEEP_WORKSTREAM_DOCUMENTS.items():
            findings = store.list_for_workstream(DEAL, workstream)
            assert len(findings) == 1, f"{workstream.value} produced {len(findings)} findings"
            golden = golden_doc(doc_id)
            assert findings[0].title in golden.expected_finding_titles
            assert findings[0].severity is golden.expected_severity
            assert findings[0].affected_entities == golden.expected_entities


class TestBrokenLegalCandidate:
    def test_legal_v25_reports_the_coc_pin_missing(
        self, firestore_client: firestore.Client
    ) -> None:
        report = run_harness(firestore_client, DEAL, extractor=legal_v25_extract_fact)
        assert report.passed is False
        assert [doc.doc_id for doc in report.missing] == [COC_DOC_ID]
        assert report.downgraded == ()

    def test_legal_v25_weakened_finding_surfaces_as_unpinned_extra(
        self, firestore_client: firestore.Client
    ) -> None:
        report = run_harness(firestore_client, DEAL, extractor=legal_v25_extract_fact)
        pinned_title = golden_doc(COC_DOC_ID).expected_finding_titles[0]
        assert len(report.new) == 1
        weakened = report.new[0]
        assert weakened.workstream is Workstream.LEGAL
        assert weakened.title != pinned_title
        assert all(finding.title != pinned_title for finding in report.new)


class TestSeverityDiff:
    def test_severity_downgrade_is_reported_and_fails(
        self, firestore_client: firestore.Client
    ) -> None:
        report = run_harness(
            firestore_client, DEAL, extractor=_with_finance_severity(FindingSeverity.LOW)
        )
        assert report.passed is False
        assert report.missing == ()
        assert report.new == ()
        assert len(report.downgraded) == 1
        downgraded = report.downgraded[0]
        assert downgraded.title == golden_doc("financials_fy27.xlsx").expected_finding_titles[0]
        assert downgraded.severity is FindingSeverity.LOW

    def test_severity_upgrade_is_not_a_regression(self, firestore_client: firestore.Client) -> None:
        report = run_harness(
            firestore_client, DEAL, extractor=_with_finance_severity(FindingSeverity.HIGH)
        )
        assert report.passed is True
        assert report.downgraded == ()
