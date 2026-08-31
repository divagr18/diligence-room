"""Dashboard API tests (BUILD_PLAN D8-M4 data plane, pulled early for the
Day-11 web shell; vision §15 four views)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from google.cloud import firestore

from agents.tools.data_room_read import DatasetDocSource
from agents.tools.finding_create import make_finding_create
from dashboard.api.app import create_app
from dashboard.api.data import _COC_SPAN, _FIN_CUSTOMER_ROW
from identity.principals import principal_for
from ingestion.chunking import chunk
from ingestion.parsing import LocalParser
from memory.event_log import EventLog
from registry.models import Workstream
from runtime.events import EventType

_CLIENT = TestClient(create_app())

SEVERITIES = {"critical", "high", "medium", "low", "informational"}
WORKSTREAMS = {"legal", "finance", "hr", "ip_tech", "tax", "regulatory", "esg", "real_estate"}

_DEAL = "deal-falcon"


def _coc_span() -> str:
    path = DatasetDocSource().read("contract_meridian_logistics.pdf")
    assert path is not None
    doc = LocalParser().parse(path, "contract_meridian_logistics.pdf", _DEAL)
    return next(c.text for c in chunk(doc) if c.locator == "clause:11.3")


def _seed_finding(client: firestore.Client, *, confidence: float = 0.9) -> str:
    tool = make_finding_create(principal_for(Workstream.LEGAL, _DEAL), client, DatasetDocSource())
    span = _coc_span()
    payload = {
        "title": "Meridian Logistics change-of-control termination right",
        "summary": "Termination right within 90 days of a change of control.",
        "severity": "critical",
        "confidence": confidence,
        "evidence": [
            {
                "verbatim_span": span,
                "document_id": "contract_meridian_logistics.pdf",
                "category": "contracts",
                "chunk_ref": "clause:11.3",
            }
        ],
        "source_documents": ["contract_meridian_logistics.pdf"],
        "affected_entities": ["Meridian Logistics, Inc."],
        "questions": [],
    }
    result = tool(finding_json=json.dumps(payload))
    assert result["decision"] == "created", result
    return str(result["finding_id"])


class TestHealthAndDeal:
    def test_health_reports_deal(self) -> None:
        body = _CLIENT.get("/api/health").json()
        assert body == {"status": "ok", "deal": "deal-falcon"}

    def test_deal_bundle_shape(self) -> None:
        res = _CLIENT.get("/api/deal")
        assert res.status_code == 200
        body = res.json()
        summary = body["summary"]
        assert summary["name"] == "Project Falcon"
        assert summary["health"] == "HIGH RISK"
        assert summary["critical_findings"] >= 1
        assert len(body["workstreams"]) == 8
        assert {ws["workstream"] for ws in body["workstreams"]} == WORKSTREAMS
        assert all(0 <= ws["progress"] <= 100 for ws in body["workstreams"])
        assert body["inbox"], "critical findings must surface in the inbox"


class TestFindings:
    def test_findings_list_is_severity_consistent(self) -> None:
        res = _CLIENT.get("/api/findings")
        assert res.status_code == 200
        findings = res.json()
        assert len(findings) >= 10
        assert {f["severity"] for f in findings} <= SEVERITIES
        assert {f["workstream"] for f in findings} <= WORKSTREAMS
        assert all(0.0 <= f["confidence"] <= 1.0 for f in findings)

    def test_finding_detail_carries_evidence_and_trace(self) -> None:
        res = _CLIENT.get("/api/findings/SYN-001")
        assert res.status_code == 200
        detail = res.json()
        assert detail["severity"] == "critical"
        assert detail["evidence"], "detail must carry evidence spans"
        assert all(ev["verbatim_span"].strip() for ev in detail["evidence"])
        assert detail["trace"], "keystone finding must carry a trace"
        assert any(step["stage"] == "finding.escalated" for step in detail["trace"])

    def test_unknown_finding_returns_404(self) -> None:
        assert _CLIENT.get("/api/findings/NOPE-999").status_code == 404


class TestSecurity:
    def test_demo_bundle_when_no_client_is_wired(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
        body = TestClient(create_app()).get("/api/security").json()
        assert body["total_blocked"] == len(body["quarantined"]) == 10
        layers = {q["layer"] for q in body["quarantined"]}
        assert layers == {"sentinel_tripwire", "model_armor"}
        assert all(q["reason_codes"] for q in body["quarantined"])
        blocked = sum(g["blocked"] for g in body["scorecard"])
        total = sum(g["total"] for g in body["scorecard"])
        assert blocked == total == 10
        assert body["feed"], "security feed must not be empty"

    def test_live_bundle_with_explicit_client(self, firestore_client: firestore.Client) -> None:
        body = TestClient(create_app(client=firestore_client)).get("/api/security").json()
        assert body["total_blocked"] == 20
        assert len(body["quarantined"]) == 20
        assert {(g["group"], g["blocked"], g["total"]) for g in body["scorecard"]} == {
            ("Prompt Injection", 8, 8),
            ("Exfiltration", 5, 5),
            ("Cross-Workstream Leak", 4, 4),
            ("Tool Poisoning / Cross-Deal", 3, 3),
        }
        layers = {q["layer"] for q in body["quarantined"]}
        assert layers == {"sentinel_tripwire", "model_armor"}
        assert {q["attack_class"] for q in body["quarantined"]} == {
            "injection",
            "exfiltration",
            "cross_ws",
            "poisoning",
            "cross_deal",
        }

    def test_emulator_env_autowires_a_client(self, firestore_emulator: str) -> None:
        # conftest sets FIRESTORE_EMULATOR_HOST for the fixture's lifetime;
        # create_app() must build the emulator client itself.
        body = TestClient(create_app()).get("/api/security").json()
        assert body["total_blocked"] == 20
        assert len(body["quarantined"]) >= 20


class TestRegistry:
    def test_registry_lists_eight_approved_agents(self) -> None:
        agents = _CLIENT.get("/api/registry").json()
        assert len(agents) == 8
        assert {a["workstream"] for a in agents} == WORKSTREAMS
        assert all(a["approved"] for a in agents)
        assert all(a["deployment_status"] == "deployed" for a in agents)
        assert all(a["model_id"] == "gemini-3.5-flash" for a in agents)


class TestQuarantinedPayloads:
    """Quarantined red-team payloads are openable from the Security view."""

    _ID = "rt-11b260f6__injection_direct_a.pdf"

    def test_quarantined_payload_is_servable(self) -> None:
        res = _CLIENT.get(f"/api/documents/{self._ID}")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("application/pdf")

    def test_nested_fixture_path_resolves(self) -> None:
        """``injection/obfuscated/a.pdf`` flattens ambiguously; the index wins."""
        res = _CLIENT.get("/api/documents/rt-11b260f6__injection_obfuscated_a.pdf")
        assert res.status_code == 200

    def test_every_quarantined_document_opens(self) -> None:
        quarantined = _CLIENT.get("/api/security").json()["quarantined"]
        assert quarantined
        for item in quarantined:
            # The UI flattens the separator so the id stays one path segment.
            sent = item["document_id"].replace("/", "_")
            got = _CLIENT.get(f"/api/documents/{sent}").status_code
            assert got == 200, f"{item['document_id']} returned {got}"

    def test_traversal_through_the_fixture_prefix_fails_closed(self) -> None:
        assert _CLIENT.get("/api/documents/rt-x__../../pyproject.toml").status_code == 404
        assert _CLIENT.get("/api/documents/rt-x__..%2F..%2Fpyproject.toml").status_code == 404

    def test_unknown_fixture_is_404_not_500(self) -> None:
        assert _CLIENT.get("/api/documents/rt-x__nope.pdf").status_code == 404


class TestDocumentList:
    """GET /api/documents - the data-room listing behind the Documents tab."""

    def test_lists_every_data_room_document(self) -> None:
        docs = _CLIENT.get("/api/documents").json()
        ids = {d["document_id"] for d in docs}
        assert "contract_meridian_logistics.pdf" in ids
        assert "financials_fy27.xlsx" in ids
        # The plan describing the data room is not itself a document, and
        # neither is the .gitkeep that holds the directory in git.
        assert "DATASET_PLAN.md" not in ids
        assert not any(i.startswith(".") for i in ids)

    def test_literal_path_wins_over_the_document_id_route(self) -> None:
        """Registration order matters: /api/documents must not resolve as an id."""
        res = _CLIENT.get("/api/documents")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_routing_matches_the_ingestion_classifier(self) -> None:
        docs = {d["document_id"]: d for d in _CLIENT.get("/api/documents").json()}
        contract = docs["contract_meridian_logistics.pdf"]
        assert contract["workstream"] == "legal"
        assert contract["doc_type"] == "contract"
        assert 0.0 < contract["confidence"] <= 1.0

    def test_format_and_page_counts_are_real(self) -> None:
        docs = {d["document_id"]: d for d in _CLIENT.get("/api/documents").json()}
        contract = docs["contract_meridian_logistics.pdf"]
        assert contract["format"] == "native_pdf"
        assert contract["page_count"] == 2
        assert contract["size_bytes"] > 0
        assert len(contract["checksum"]) == 64
        assert docs["financials_fy27.xlsx"]["format"] == "xlsx"

    def test_every_row_carries_a_security_status(self) -> None:
        docs = _CLIENT.get("/api/documents").json()
        assert docs
        assert all(d["security_status"] in {"cleared", "quarantined"} for d in docs)

    def test_listed_documents_are_all_servable(self) -> None:
        for doc in _CLIENT.get("/api/documents").json():
            assert _CLIENT.get(f"/api/documents/{doc['document_id']}").status_code == 200


class TestDocuments:
    def test_serve_pdf_returns_pdf_media_type(self) -> None:
        res = _CLIENT.get("/api/documents/contract_meridian_logistics.pdf")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("application/pdf")

    def test_locate_pdf_evidence_span(self) -> None:
        res = _CLIENT.get(
            "/api/documents/contract_meridian_logistics.pdf/locate",
            params={"span": _COC_SPAN},
        )
        assert res.status_code == 200
        locator = res.json()
        assert locator["kind"] == "pdf"
        assert locator["page_count"] == 2
        assert locator["page"] is not None and 1 <= locator["page"] <= locator["page_count"]

    def test_locate_xlsx_evidence_span(self) -> None:
        res = _CLIENT.get(
            "/api/documents/financials_fy27.xlsx/locate",
            params={"span": _FIN_CUSTOMER_ROW},
        )
        assert res.status_code == 200
        locator = res.json()
        assert locator["kind"] == "xlsx"
        assert locator["sheet"] == "FY27 Projected Revenue"
        assert locator["row_index"] == 1
        assert locator["headers"]
        assert locator["rows"]
        located_row = locator["rows"][locator["row_index"]]
        assert "Meridian Logistics, Inc." in located_row
        assert "0.183" in located_row

    def test_xlsx_header_is_first_row(self) -> None:
        locator = _CLIENT.get(
            "/api/documents/financials_fy27.xlsx/locate",
            params={"span": _FIN_CUSTOMER_ROW},
        ).json()
        assert locator["rows"][0] == locator["headers"]

    def test_unknown_document_returns_404(self) -> None:
        assert _CLIENT.get("/api/documents/no_such_doc.pdf").status_code == 404
        assert (
            _CLIENT.get("/api/documents/no_such_doc.pdf/locate", params={"span": "x"}).status_code
            == 404
        )

    def test_path_traversal_is_rejected(self) -> None:
        # The resolver must never serve a file that escapes the data room.
        assert (
            _CLIENT.get(
                "/api/documents/%2e%2e%2f%2e%2e%2ftests%2ftest_dashboard_api.py"
            ).status_code
            == 404
        )

    def test_unresolvable_document_name_fails_closed(self) -> None:
        # Names the OS refuses to resolve (NUL bytes) must 404, never 500.
        assert _CLIENT.get("/api/documents/a%00b.pdf").status_code == 404
        assert (
            _CLIENT.get("/api/documents/a%00b.pdf/locate", params={"span": "x"}).status_code == 404
        )


class TestRoleFilter:
    _ALL_FINDING_IDS = {
        "SYN-001",
        "LEGAL-014",
        "FIN-007",
        "IP-009",
        "REG-005",
        "RE-004",
        "HR-003",
        "TAX-002",
        "ESG-001",
        "LEGAL-021",
        "IP-002",
    }

    def _finding_ids(self, role: str | None = None) -> set[str]:
        params = {"role": role} if role is not None else {}
        res = _CLIENT.get("/api/findings", params=params)
        assert res.status_code == 200
        return {f["finding_id"] for f in res.json()}

    def test_default_role_sees_everything(self) -> None:
        assert self._finding_ids() == self._ALL_FINDING_IDS

    def test_deal_lead_sees_everything(self) -> None:
        assert self._finding_ids("deal_lead") == self._ALL_FINDING_IDS

    def test_junior_legal_sees_only_legal_findings(self) -> None:
        assert self._finding_ids("junior_legal") == {"SYN-001", "LEGAL-014", "LEGAL-021"}

    def test_junior_legal_cannot_open_a_finance_finding(self) -> None:
        # Zero-trust: a hidden finding is indistinguishable from a missing one.
        res = _CLIENT.get("/api/findings/FIN-007", params={"role": "junior_legal"})
        assert res.status_code == 404

    def test_hr_analyst_sees_only_hr_findings(self) -> None:
        assert self._finding_ids("hr_analyst") == {"HR-003"}

    def test_outside_counsel_sees_only_approved_legal_materials(self) -> None:
        # SYN-001 is legal but still open -> not approved for external eyes.
        assert self._finding_ids("outside_counsel") == {"LEGAL-014", "LEGAL-021"}

    def test_inbox_is_role_filtered(self) -> None:
        def inbox(role: str) -> list[dict[str, object]]:
            res = _CLIENT.get("/api/deal", params={"role": role})
            assert res.status_code == 200
            body: dict[str, object] = res.json()
            entries = body["inbox"]
            assert isinstance(entries, list)
            return entries

        assert {e["finding_id"] for e in inbox("deal_lead")} == {"SYN-001", "LEGAL-014"}
        assert {e["finding_id"] for e in inbox("junior_legal")} == {"SYN-001", "LEGAL-014"}
        # Open escalations are not approved-for-external material; HR scope excludes legal.
        assert inbox("outside_counsel") == []
        assert inbox("hr_analyst") == []

    def test_unknown_role_is_rejected(self) -> None:
        assert _CLIENT.get("/api/findings", params={"role": "intern"}).status_code == 422


class TestFindingGraph:
    def test_synthesis_graph_carries_the_full_chain(self) -> None:
        detail = _CLIENT.get("/api/findings/SYN-001").json()
        graph = detail["graph"]
        assert graph is not None
        assert graph["finding_id"] == "SYN-001"
        kinds = {node["kind"] for node in graph["nodes"]}
        assert kinds == {"document", "agent", "gateway", "finding", "escalation"}
        node_ids = {node["node_id"] for node in graph["nodes"]}
        assert "finding:SYN-001" in node_ids
        for edge in graph["edges"]:
            assert edge["from_id"] in node_ids
            assert edge["to_id"] in node_ids

    def test_regular_findings_get_a_source_chain_graph(self) -> None:
        detail = _CLIENT.get("/api/findings/LEGAL-014").json()
        graph = detail["graph"]
        assert graph is not None
        kinds = {node["kind"] for node in graph["nodes"]}
        assert kinds == {"document", "agent", "finding"}
        documents = [node["label"] for node in graph["nodes"] if node["kind"] == "document"]
        assert documents == ["contract_meridian_logistics.pdf"]
        assert any(edge["to_id"] == "finding:LEGAL-014" for edge in graph["edges"])


class TestNegotiationEndpoints:
    """D12-M6 full spec over HTTP: draft(approve-gated) -> approve -> send,
    client-backed, 503 without a client, events persisted to the deal log."""

    def test_endpoints_return_503_without_a_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
        client = TestClient(create_app())
        assert (
            client.post(
                "/api/negotiation/drafts",
                json={"finding_id": "any", "kind": "clause_redline"},
            ).status_code
            == 503
        )
        assert client.get("/api/negotiation", params={"finding_id": "any"}).status_code == 503
        assert (
            client.post(
                "/api/negotiation/d/approve", json={"approver": "deal-lead@deal-falcon"}
            ).status_code
            == 503
        )
        assert client.post("/api/negotiation/d/send").status_code == 503

    def test_full_beat_draft_approve_send(self, firestore_client: firestore.Client) -> None:
        finding_id = _seed_finding(firestore_client, confidence=0.9)
        client = TestClient(create_app(client=firestore_client))

        res = client.post(
            "/api/negotiation/drafts",
            json={"finding_id": finding_id, "kind": "clause_redline"},
        )
        assert res.status_code == 200
        draft = res.json()
        assert draft["state"] == "pending_approval"
        assert draft["kind"] == "clause_redline"
        assert draft["finding_id"] == finding_id
        assert f"“{_coc_span()}”" in draft["body"], "redline body must quote the evidence span"
        assert "Meridian Logistics, Inc." in draft["body"]
        draft_id = draft["draft_id"]

        res = client.post(
            f"/api/negotiation/{draft_id}/approve",
            json={"approver": "deal-lead@deal-falcon"},
        )
        assert res.status_code == 200
        assert res.json()["state"] == "approved"
        assert res.json()["approved_by"] == "deal-lead@deal-falcon"

        res = client.post(f"/api/negotiation/{draft_id}/send")
        assert res.status_code == 200
        assert res.json()["state"] == "send_logged"

        rows = client.get("/api/negotiation", params={"finding_id": finding_id}).json()
        assert {row["draft_id"] for row in rows} == {draft_id}

        transitions = EventLog(firestore_client).list_for_type(
            _DEAL, EventType.NEGOTIATION_TRANSITION.value
        )
        assert len(transitions) == 4
        final = json.loads(transitions[-1].payload_json)
        assert final["to_state"] == "send_logged"
        assert final["draft_id"] == draft_id
        assert final["finding_id"] == finding_id
        assert final["kind"] == "clause_redline"

    def test_draft_creation_is_idempotent(self, firestore_client: firestore.Client) -> None:
        finding_id = _seed_finding(firestore_client, confidence=0.9)
        client = TestClient(create_app(client=firestore_client))
        payload = {"finding_id": finding_id, "kind": "seller_request"}
        first = client.post("/api/negotiation/drafts", json=payload)
        second = client.post("/api/negotiation/drafts", json=payload)
        assert first.status_code == second.status_code == 200
        assert first.json()["draft_id"] == second.json()["draft_id"]
        assert second.json()["state"] == "pending_approval"

    def test_low_confidence_finding_is_refused_409(
        self, firestore_client: firestore.Client
    ) -> None:
        finding_id = _seed_finding(firestore_client, confidence=0.5)
        client = TestClient(create_app(client=firestore_client))
        res = client.post(
            "/api/negotiation/drafts",
            json={"finding_id": finding_id, "kind": "clause_redline"},
        )
        assert res.status_code == 409
        assert "candidate threshold" in str(res.json()["detail"])

    def test_unknown_finding_returns_404(self, firestore_client: firestore.Client) -> None:
        client = TestClient(create_app(client=firestore_client))
        res = client.post(
            "/api/negotiation/drafts",
            json={"finding_id": "no-such-finding", "kind": "clause_redline"},
        )
        assert res.status_code == 404

    def test_invalid_kind_is_rejected_422(self, firestore_client: firestore.Client) -> None:
        client = TestClient(create_app(client=firestore_client))
        res = client.post(
            "/api/negotiation/drafts",
            json={"finding_id": "whatever", "kind": "counterparty_ultimatum"},
        )
        assert res.status_code == 422

    def test_invalid_transitions_are_conflicts(self, firestore_client: firestore.Client) -> None:
        finding_id = _seed_finding(firestore_client, confidence=0.9)
        client = TestClient(create_app(client=firestore_client))
        draft = client.post(
            "/api/negotiation/drafts",
            json={"finding_id": finding_id, "kind": "clarification_question"},
        ).json()
        draft_id = draft["draft_id"]
        assert client.post(f"/api/negotiation/{draft_id}/send").status_code == 409
        client.post(
            f"/api/negotiation/{draft_id}/approve", json={"approver": "deal-lead@deal-falcon"}
        )
        assert (
            client.post(
                f"/api/negotiation/{draft_id}/approve", json={"approver": "deal-lead@deal-falcon"}
            ).status_code
            == 409
        )

    def test_transitions_on_missing_draft_return_404(
        self, firestore_client: firestore.Client
    ) -> None:
        client = TestClient(create_app(client=firestore_client))
        assert (
            client.post(
                "/api/negotiation/no-such-draft/approve",
                json={"approver": "deal-lead@deal-falcon"},
            ).status_code
            == 404
        )
        assert client.post("/api/negotiation/no-such-draft/send").status_code == 404

    def test_approve_requires_an_approver(self, firestore_client: firestore.Client) -> None:
        client = TestClient(create_app(client=firestore_client))
        assert client.post("/api/negotiation/d/approve", json={"approver": ""}).status_code == 422
