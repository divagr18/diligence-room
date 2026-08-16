"""FindingsStore persistence tests (BUILD_PLAN D3-M6, vision §9 + §19.2).

Emulator-backed tests for the partition-scoped findings writer:
create/get/update round-trips, error guards, workstream-scoped listing,
and serialization helpers.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from google.cloud import firestore

from memory.findings import (
    DuplicateFindingError,
    Evidence,
    Finding,
    FindingNotFoundError,
    FindingSeverity,
    FindingsStore,
    FindingStatus,
    finding_from_doc,
    findings_to_doc,
)
from registry.models import Workstream

NOW = datetime(2026, 8, 15, 12, 0, 30, 123456, tzinfo=UTC)
UPDATED = datetime(2026, 8, 15, 14, 30, 0, 654321, tzinfo=UTC)

_EVIDENCE = Evidence(
    verbatim_span=(
        "may terminate this Agreement by written notice delivered "
        "within ninety (90) days following a Change of Control"
    ),
    document_id="contract_customer_x.pdf",
)


def _finding(
    finding_id: str = "LEGAL-001",
    deal_id: str = "deal-falcon",
    workstream: Workstream = Workstream.LEGAL,
    **overrides: object,
) -> Finding:
    base: dict[str, object] = {
        "finding_id": finding_id,
        "deal_id": deal_id,
        "workstream": workstream,
        "title": "Customer X change-of-control termination right",
        "summary": "Top customer agreement contains a CoC termination right.",
        "severity": FindingSeverity.HIGH,
        "confidence": 0.94,
        "status": FindingStatus.CANDIDATE,
        "evidence": (_EVIDENCE,),
        "source_documents": ("contract_customer_x.pdf",),
        "related_findings": (),
        "affected_entities": ("Customer X",),
        "questions": ("Is the CoC clause negotiable?",),
        "owner": "legal-agent@deal-falcon",
        "created_at": NOW,
        "updated_at": NOW,
    }
    base.update(overrides)
    return Finding(**base)  # type: ignore[arg-type]


class TestFindingsToDoc:
    def test_serializes_enums_to_value_strings(self) -> None:
        doc = findings_to_doc(_finding())
        assert doc["severity"] == "high"
        assert doc["status"] == "candidate"
        assert doc["workstream"] == "legal"

    def test_serializes_tuples_to_lists(self) -> None:
        doc = findings_to_doc(_finding())
        assert doc["source_documents"] == ["contract_customer_x.pdf"]
        assert doc["related_findings"] == []
        assert doc["affected_entities"] == ["Customer X"]
        assert doc["questions"] == ["Is the CoC clause negotiable?"]

    def test_serializes_evidence_to_list_of_dicts(self) -> None:
        doc = findings_to_doc(_finding())
        assert isinstance(doc["evidence"], list)
        assert len(doc["evidence"]) == 1
        ev = doc["evidence"][0]
        assert ev["verbatim_span"] == _EVIDENCE.verbatim_span
        assert ev["document_id"] == "contract_customer_x.pdf"
        assert ev["chunk_ref"] is None

    def test_audit_trace_id_none_stored(self) -> None:
        doc = findings_to_doc(_finding())
        assert doc["audit_trace_id"] is None

    def test_audit_trace_id_set_stored(self) -> None:
        doc = findings_to_doc(_finding(audit_trace_id="trace-abc"))
        assert doc["audit_trace_id"] == "trace-abc"

    def test_round_trip_full_equality(self) -> None:
        for trace_id in (None, "trace-xyz-789"):
            original = _finding(
                finding_id=f"f-{trace_id or 'none'}",
                audit_trace_id=trace_id,
                related_findings=("OTHER-001",),
                confidence=0.87,
            )
            doc = findings_to_doc(original)
            restored = finding_from_doc(doc)
            assert restored == original


class TestFindingFromDoc:
    def test_restores_tuples_from_lists(self) -> None:
        doc: dict[str, object] = {
            "finding_id": "FIN-001",
            "deal_id": "deal-falcon",
            "workstream": "finance",
            "title": "Revenue recognition gap",
            "summary": "ASC 606 compliance issue.",
            "severity": "medium",
            "confidence": 0.72,
            "status": "validated",
            "evidence": [
                {
                    "verbatim_span": "revenue is recognized upon delivery",
                    "document_id": "10k.pdf",
                    "chunk_ref": None,
                }
            ],
            "source_documents": ["10k.pdf"],
            "related_findings": ["LEGAL-001"],
            "affected_entities": [],
            "questions": [],
            "owner": "finance-agent@deal-falcon",
            "created_at": NOW,
            "updated_at": UPDATED,
            "audit_trace_id": None,
        }
        f = finding_from_doc(doc)
        assert isinstance(f.source_documents, tuple)
        assert isinstance(f.related_findings, tuple)
        assert isinstance(f.affected_entities, tuple)
        assert isinstance(f.questions, tuple)
        assert isinstance(f.evidence, tuple)

    def test_restores_enum_members(self) -> None:
        doc = findings_to_doc(_finding())
        f = finding_from_doc(doc)
        assert f.workstream is Workstream.LEGAL
        assert f.severity is FindingSeverity.HIGH
        assert f.status is FindingStatus.CANDIDATE

    def test_timestamps_preserved_at_microsecond(self) -> None:
        doc = findings_to_doc(_finding())
        f = finding_from_doc(doc)
        assert f.created_at == NOW
        assert f.updated_at == NOW


class TestFindingsStoreCreateGet:
    def test_create_then_get_full_equality(self, firestore_client: firestore.Client) -> None:
        store = FindingsStore(firestore_client)
        original = _finding()
        store.create(original)

        loaded = store.get("deal-falcon", "LEGAL-001")

        assert loaded == original
        assert loaded.title == original.title
        assert loaded.summary == original.summary
        assert loaded.severity is FindingSeverity.HIGH
        assert loaded.confidence == 0.94
        assert loaded.status is FindingStatus.CANDIDATE
        assert loaded.evidence[0].verbatim_span == _EVIDENCE.verbatim_span
        assert loaded.evidence[0].document_id == "contract_customer_x.pdf"
        assert loaded.source_documents == ("contract_customer_x.pdf",)
        assert loaded.related_findings == ()
        assert loaded.affected_entities == ("Customer X",)
        assert loaded.questions == ("Is the CoC clause negotiable?",)
        assert loaded.owner == "legal-agent@deal-falcon"
        assert loaded.audit_trace_id is None

    def test_create_with_audit_trace_id_round_trips(
        self, firestore_client: firestore.Client
    ) -> None:
        store = FindingsStore(firestore_client)
        original = _finding(audit_trace_id="trace-xyz-789")
        store.create(original)

        loaded = store.get("deal-falcon", "LEGAL-001")
        assert loaded.audit_trace_id == "trace-xyz-789"

    def test_timestamps_preserved_at_microsecond_through_firestore(
        self, firestore_client: firestore.Client
    ) -> None:
        store = FindingsStore(firestore_client)
        original = _finding()
        store.create(original)

        loaded = store.get("deal-falcon", "LEGAL-001")
        assert loaded.created_at == NOW
        assert loaded.updated_at == NOW

    def test_duplicate_create_raises_duplicate_finding_error(
        self, firestore_client: firestore.Client
    ) -> None:
        store = FindingsStore(firestore_client)
        store.create(_finding())
        with pytest.raises(DuplicateFindingError):
            store.create(_finding())


class TestFindingsStoreGetMissing:
    def test_get_unknown_raises_finding_not_found(self, firestore_client: firestore.Client) -> None:
        store = FindingsStore(firestore_client)
        with pytest.raises(FindingNotFoundError):
            store.get("deal-falcon", "NONEXISTENT")


class TestFindingsStoreUpdate:
    def test_update_unknown_raises_finding_not_found(
        self, firestore_client: firestore.Client
    ) -> None:
        store = FindingsStore(firestore_client)
        with pytest.raises(FindingNotFoundError):
            store.update(_finding(finding_id="NEVER-CREATED"))

    def test_update_mutates_status_and_confidence(self, firestore_client: firestore.Client) -> None:
        store = FindingsStore(firestore_client)
        original = _finding()
        store.create(original)

        updated = Finding(
            finding_id=original.finding_id,
            deal_id=original.deal_id,
            workstream=original.workstream,
            title=original.title,
            summary=original.summary,
            severity=original.severity,
            confidence=0.99,
            status=FindingStatus.VALIDATED,
            evidence=original.evidence,
            source_documents=original.source_documents,
            related_findings=original.related_findings,
            affected_entities=original.affected_entities,
            questions=original.questions,
            owner=original.owner,
            created_at=original.created_at,
            updated_at=UPDATED,
            audit_trace_id=original.audit_trace_id,
        )
        store.update(updated)

        loaded = store.get("deal-falcon", "LEGAL-001")
        assert loaded.status is FindingStatus.VALIDATED
        assert loaded.confidence == 0.99
        assert loaded.updated_at == UPDATED
        assert loaded.created_at == NOW


class TestListForWorkstream:
    def test_isolation_returns_only_matching_workstream(
        self, firestore_client: firestore.Client
    ) -> None:
        store = FindingsStore(firestore_client)
        store.create(_finding(finding_id="LEGAL-001"))
        store.create(
            _finding(
                finding_id="FIN-001",
                workstream=Workstream.FINANCE,
                owner="finance-agent@deal-falcon",
            )
        )

        legal = store.list_for_workstream("deal-falcon", Workstream.LEGAL)
        assert [f.finding_id for f in legal] == ["LEGAL-001"]

        finance = store.list_for_workstream("deal-falcon", Workstream.FINANCE)
        assert [f.finding_id for f in finance] == ["FIN-001"]

    def test_different_deal_same_workstream_disjoint(
        self, firestore_client: firestore.Client
    ) -> None:
        store = FindingsStore(firestore_client)
        store.create(_finding(finding_id="LEGAL-001", deal_id="deal-falcon"))
        store.create(_finding(finding_id="LEGAL-002", deal_id="deal-hawk"))

        falcon = store.list_for_workstream("deal-falcon", Workstream.LEGAL)
        assert [f.finding_id for f in falcon] == ["LEGAL-001"]

        hawk = store.list_for_workstream("deal-hawk", Workstream.LEGAL)
        assert [f.finding_id for f in hawk] == ["LEGAL-002"]

    def test_string_workstream_accepted(self, firestore_client: firestore.Client) -> None:
        store = FindingsStore(firestore_client)
        store.create(_finding())

        result = store.list_for_workstream("deal-falcon", "legal")
        assert [f.finding_id for f in result] == ["LEGAL-001"]

    def test_empty_workstream_returns_empty_list(self, firestore_client: firestore.Client) -> None:
        store = FindingsStore(firestore_client)
        result = store.list_for_workstream("deal-falcon", Workstream.ESG)
        assert result == []


class TestEmptyEvidenceGuard:
    def test_dataclass_rejects_empty_evidence(self) -> None:
        with pytest.raises(ValueError, match="evidence"):
            _finding(evidence=())
