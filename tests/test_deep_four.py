"""Deep-four offline finding tests (BUILD_PLAN D6-M4 offline path, scenario S7).

Each deep workstream (legal, finance, hr, ip_tech) produces at least one
finding from its seeded document, written through the evidence-gated
finding-create path, landing in its own workstream partition. The live path
(real Flash agent) is proved separately; both share the write path, so the
evidence gate applies identically.
"""

from __future__ import annotations

import re

import pytest
from google.cloud import firestore

from agents.fleet import DEEP_WORKSTREAM_DOCUMENTS, run_workstream_offline
from agents.tools.data_room_read import DatasetDocSource
from ingestion.parsing import LocalParser
from memory.findings import FindingsStore
from registry.models import Workstream

DEAL = "deal-falcon"
DEEP_FOUR = (Workstream.LEGAL, Workstream.FINANCE, Workstream.HR, Workstream.IP_TECH)


def _source_texts(doc_source: DatasetDocSource) -> dict[str, str]:
    texts: dict[str, str] = {}
    for name in DEEP_WORKSTREAM_DOCUMENTS.values():
        blob = doc_source.read(name)
        assert blob is not None
        parsed = LocalParser().parse(blob, name, DEAL)
        assert parsed.text is not None
        texts[name] = parsed.text
    return texts


def _partition_item(client: firestore.Client, ws: Workstream, finding_id: str) -> bool:
    snapshot = (
        client.collection("deals")
        .document(DEAL)
        .collection("workstreams")
        .document(ws.value)
        .collection("items")
        .document(finding_id)
        .get()
    )
    return bool(snapshot.exists)


class TestDeepFour:
    def test_each_workstream_produces_one_finding(self, firestore_client: firestore.Client) -> None:
        doc_source = DatasetDocSource()
        store = FindingsStore(firestore_client)
        for ws in DEEP_FOUR:
            finding_id = run_workstream_offline(firestore_client, DEAL, ws, doc_source=doc_source)
            findings = store.list_for_workstream(DEAL, ws)
            assert len(findings) == 1, f"{ws.value} produced {len(findings)} findings"
            assert findings[0].finding_id == finding_id

    def test_findings_land_in_their_own_partitions(
        self, firestore_client: firestore.Client
    ) -> None:
        doc_source = DatasetDocSource()
        created: dict[Workstream, str] = {}
        for ws in DEEP_FOUR:
            created[ws] = run_workstream_offline(firestore_client, DEAL, ws, doc_source=doc_source)
        for ws, finding_id in created.items():
            assert _partition_item(firestore_client, ws, finding_id), (
                f"{ws.value} finding missing from its own partition"
            )
            for other in DEEP_FOUR:
                if other is not ws:
                    assert not _partition_item(firestore_client, other, finding_id), (
                        f"{ws.value} finding leaked into {other.value} partition"
                    )

    def test_every_evidence_span_is_verbatim_in_its_source(
        self, firestore_client: firestore.Client
    ) -> None:
        doc_source = DatasetDocSource()
        texts = _source_texts(doc_source)
        store = FindingsStore(firestore_client)
        for ws in DEEP_FOUR:
            run_workstream_offline(firestore_client, DEAL, ws, doc_source=doc_source)
            for finding in store.list_for_workstream(DEAL, ws):
                source_text = texts[finding.evidence[0].document_id]
                assert finding.evidence[0].verbatim_span in source_text, (
                    f"{ws.value} evidence span is not verbatim in its source"
                )

    def test_finance_finding_carries_18_3(self, firestore_client: firestore.Client) -> None:
        run_workstream_offline(
            firestore_client, DEAL, Workstream.FINANCE, doc_source=DatasetDocSource()
        )
        finding = FindingsStore(firestore_client).list_for_workstream(DEAL, Workstream.FINANCE)[0]
        assert "18.3%" in finding.summary

    def test_legal_finding_cites_the_coc_clause(self, firestore_client: firestore.Client) -> None:
        run_workstream_offline(
            firestore_client, DEAL, Workstream.LEGAL, doc_source=DatasetDocSource()
        )
        finding = FindingsStore(firestore_client).list_for_workstream(DEAL, Workstream.LEGAL)[0]
        normalized = re.sub(r"\s+", " ", finding.evidence[0].verbatim_span)
        assert "ninety (90) days following a Change of Control" in normalized

    def test_ip_tech_finding_flags_titanbridge_eol(
        self, firestore_client: firestore.Client
    ) -> None:
        run_workstream_offline(
            firestore_client, DEAL, Workstream.IP_TECH, doc_source=DatasetDocSource()
        )
        finding = FindingsStore(firestore_client).list_for_workstream(DEAL, Workstream.IP_TECH)[0]
        assert "TitanBridge" in finding.evidence[0].verbatim_span

    def test_hr_finding_flags_whitfield_departure(self, firestore_client: firestore.Client) -> None:
        run_workstream_offline(firestore_client, DEAL, Workstream.HR, doc_source=DatasetDocSource())
        finding = FindingsStore(firestore_client).list_for_workstream(DEAL, Workstream.HR)[0]
        assert "Whitfield" in finding.evidence[0].verbatim_span

    def test_rerun_is_idempotent_via_duplicate_guard(
        self, firestore_client: firestore.Client
    ) -> None:
        doc_source = DatasetDocSource()
        run_workstream_offline(firestore_client, DEAL, Workstream.HR, doc_source=doc_source)
        with pytest.raises(RuntimeError, match="duplicate_finding"):
            run_workstream_offline(firestore_client, DEAL, Workstream.HR, doc_source=doc_source)
        assert len(FindingsStore(firestore_client).list_for_workstream(DEAL, Workstream.HR)) == 1
